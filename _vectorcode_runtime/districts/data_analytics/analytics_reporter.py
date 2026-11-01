import sys
import uuid
import json
import asyncio
import datetime
import re
from collections import defaultdict

# Task outcome is encoded as "...status=<word>" in governor_dispatch/task
# event content — the real success signal (see compute_activity_metrics).
_STATUS_RE = re.compile(r"status=(\w+)")

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory, get_temp_cursor
from core.memory.obsidian_sync import ObsidianSync

_FOCUS = CONFIG["models"]["focus"]
_CHAIRMAN = CONFIG["models"]["chairman"]


def _ascii_bar(value: float, max_value: float, width: int = 20) -> str:
    """Render a simple ASCII bar chart segment."""
    if max_value <= 0:
        return "[" + " " * width + "]"
    filled = int(round((value / max_value) * width))
    filled = max(0, min(filled, width))
    return "[" + "#" * filled + " " * (width - filled) + "]"


class AnalyticsReporter(AgentBase):
    """
    Transforms VECTOR's own episodic data into actionable weekly insights.
    Mines event logs, computes metrics, detects anomalies, generates an LLM-written
    brief, and publishes a structured Obsidian report with ASCII charts.
    RULE 11: local models only — never Claude API at runtime.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="AnalyticsReporter",
            district="data_analytics",
            generation=generation,
        )
        self.capabilities = ["analytics", "data_analytics", "error", "governor_dispatch", "ok", "report"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        # Set by mine_episodic_data(): the error string of the last failed pull
        # (None when it succeeded). A failed pull returns [] -- identical to a
        # genuinely quiet week -- so run() consults this to avoid publishing an
        # "all quiet" report built from a DB error.
        self.last_mine_error: str | None = None
        logger.info(f"[VECTOR][analytics_reporter] ready gen={generation}")

    # ── Data mining ──────────────────────────────────────────────────────────────

    def mine_episodic_data(self, days: int = 7) -> list[dict]:
        """Fetch last N days of episodic events and return them as a list of dicts."""
        self.last_mine_error = None
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=days)
        ).isoformat()
        try:
            with get_temp_cursor() as cur:
                cur.execute(
                    "SELECT event_type, content, tags, timestamp, source "
                    "FROM episodic_memory WHERE timestamp > ? ORDER BY timestamp ASC",
                    (cutoff,),
                )
                rows = cur.fetchall()
            events = []
            for row in rows:
                events.append(
                    {
                        "event_type": row[0],
                        "content": row[1],
                        "tags": json.loads(row[2]) if row[2] else [],
                        "timestamp": row[3],
                        "source": row[4],
                    }
                )
            logger.info(
                f"[VECTOR][analytics_reporter] mined {len(events)} events over {days}d"
            )
            return events
        except Exception as e:
            logger.error(f"[VECTOR][analytics_reporter] mine_episodic_data failed: {e}")
            self.last_mine_error = str(e)
            return []

    # ── Metrics ───────────────────────────────────────────────────────────────────

    def compute_activity_metrics(self, events: list[dict] | None = None) -> dict:
        """
        Compute:
          - event counts by event_type
          - event counts by source (district)
          - event counts by hour-of-day
          - task success rate (event_type 'task_completed' vs 'task_failed')
          - most active districts (top 5 sources)
          - peak hours (top 3)
        """
        if events is None:
            events = self.mine_episodic_data(days=7)

        by_type: dict[str, int] = defaultdict(int)
        by_district: dict[str, int] = defaultdict(int)
        by_hour: dict[int, int] = defaultdict(int)
        total = len(events)

        # Real task-outcome signal lives in the `status=` field inside
        # governor_dispatch / task event content ("...district=marketing
        # status=ok"). VECTOR never emits literal task_completed/task_failed
        # event TYPES — there are 0 of them in a 50k-event DB — so the old
        # `by_type.get("task_completed")` computation reported success_rate=0.0%
        # in EVERY weekly analytics report, forever (2026-07-17 browser dogfood
        # spotted "success_rate=0.0%" alongside 49k events). Parse status
        # instead; a real run is ~70% ok.
        completed = failed = 0
        for ev in events:
            by_type[ev["event_type"]] += 1
            by_district[ev["source"]] += 1
            try:
                ts = datetime.datetime.fromisoformat(ev["timestamp"])
                by_hour[ts.hour] += 1
            except Exception as ts_err:
                logger.debug("[VECTOR][analytics_reporter] unparseable timestamp {!r}: {}", ev.get("timestamp"), ts_err)

            if ev["event_type"] in ("governor_dispatch", "task"):
                m = _STATUS_RE.search(ev.get("content") or "")
                if m:
                    status = m.group(1).lower()
                    if status in ("ok", "completed", "success", "executed", "done"):
                        completed += 1
                    elif status in ("error", "failed", "no_agents", "blocked", "denied"):
                        failed += 1
                    # status=None / pending / unknown → not counted either way

        # Back-compat: honour explicit task_completed/task_failed event types
        # too, in case they're ever emitted.
        completed += by_type.get("task_completed", 0)
        failed += by_type.get("task_failed", 0)
        attempts = completed + failed
        success_rate = completed / attempts if attempts > 0 else 0.0

        top_districts = sorted(by_district.items(), key=lambda x: x[1], reverse=True)[:5]
        peak_hours = sorted(by_hour.items(), key=lambda x: x[1], reverse=True)[:3]

        # HP distribution from agent_history
        hp_data: dict[str, int] = {}
        try:
            with get_temp_cursor() as cur:
                cur.execute(
                    "SELECT agent_name, final_hp FROM agent_history "
                    "ORDER BY died_at DESC LIMIT 20"
                )
                for row in cur.fetchall():
                    hp_data[row[0]] = row[1]
        except Exception as e:
            logger.warning(f"[VECTOR][analytics_reporter] hp query failed: {e}")

        metrics = {
            "total_events": total,
            "by_type": dict(by_type),
            "by_district": dict(by_district),
            "by_hour": dict(by_hour),
            "task_success_rate": round(success_rate, 3),
            "tasks_completed": completed,
            "tasks_failed": failed,
            "most_active_districts": top_districts,
            "peak_hours": peak_hours,
            "agent_hp_snapshot": hp_data,
        }
        logger.info(
            f"[VECTOR][analytics_reporter] metrics: total={total} "
            f"success_rate={success_rate:.1%} top_district={top_districts[0] if top_districts else 'none'}"
        )
        return metrics

    # ── Anomaly detection ─────────────────────────────────────────────────────────

    def detect_anomalies(self, events: list[dict] | None = None) -> list[dict]:
        """
        Detect unusual spikes (>2x rolling daily average) in error or failure events,
        and flag any district that has seen no activity in the last 7 days.
        """
        if events is None:
            events = self.mine_episodic_data(days=7)

        # Bucket error/failure events by date
        error_types = {"task_failed", "fatigue_detected", "error", "critical", "anomaly"}
        daily_errors: dict[str, int] = defaultdict(int)

        for ev in events:
            if ev["event_type"] in error_types or "error" in ev["event_type"].lower():
                try:
                    date_str = ev["timestamp"][:10]
                    daily_errors[date_str] += 1
                except Exception as ts_err:
                    logger.debug("[VECTOR][analytics_reporter] unusable timestamp {!r}: {}", ev.get("timestamp"), ts_err)

        anomalies = []
        if daily_errors:
            avg = sum(daily_errors.values()) / len(daily_errors)
            for date, count in sorted(daily_errors.items()):
                if count > 2 * avg and avg > 0:
                    anomalies.append(
                        {
                            "date": date,
                            "error_count": count,
                            "avg_daily_errors": round(avg, 2),
                            "ratio": round(count / avg, 2),
                            "severity": "high" if count > 4 * avg else "medium",
                        }
                    )

        # Districts with zero activity
        active_districts = {ev["source"] for ev in events}
        known_districts = {
            "git_bot", "code_reviewer", "threat_scout", "node_guard",
            "sleep_tracker", "fatigue_monitor", "budget_analyst", "news_aggregator",
            "analytics_reporter", "performance_benchmarker",
        }
        silent = known_districts - active_districts
        for d in silent:
            anomalies.append(
                {"district": d, "issue": "no_activity_7d", "severity": "low"}
            )

        logger.info(
            f"[VECTOR][analytics_reporter] anomalies found: {len(anomalies)}"
        )
        return anomalies

    # ── LLM brief ─────────────────────────────────────────────────────────────────

    def generate_weekly_brief(self, metrics: dict, anomalies: list[dict]) -> str:
        """
        Use ollama_safe to synthesize a 3-bullet executive brief for Arghyadeep.
        Falls back to a structured plain-text summary if the LLM is unavailable.
        """
        try:
            from core.inference.vectorcode_llm import chat
            from core.loop.context_engine import ContextEngine

            hydration = ContextEngine().session_hydration_prompt()
            prompt = (
                f"You are VECTOR's analytics module. Write exactly 3 short bullet points "
                f"(max 2 sentences each) summarising this week's activity for Arghyadeep.\n\n"
                f"Metrics: {json.dumps(metrics, default=str)}\n"
                f"Anomalies: {json.dumps(anomalies, default=str)}\n\n"
                f"Be blunt, specific, and actionable. No fluff."
            )
            from core.prompt_library import get_library as _gl
            _lib = _gl().get_for_agent("analytics_reporter") or ""
            _ar_sys = (hydration + "\n\n" + _lib).strip() if _lib else hydration
            response = chat(
                model=_CHAIRMAN,
                messages=[
                    {"role": "system", "content": _ar_sys},
                    {"role": "user", "content": prompt},
                ],
                timeout=60.0,
            )
            if response:
                logger.info(
                    "[VECTOR][analytics_reporter] LLM brief generated"
                )
                return response.strip()
        except Exception as e:
            logger.warning(
                f"[VECTOR][analytics_reporter] LLM brief failed, using fallback: {e}"
            )

        # Fallback: structured plain text
        top = metrics.get("most_active_districts", [])
        top_str = top[0][0] if top else "unknown"
        return (
            f"- {metrics.get('total_events', 0)} events recorded this week; "
            f"task success rate {self._fmt_success_rate(metrics)}.\n"
            f"- Most active district: {top_str}. "
            f"{len(anomalies)} anomaly/anomalies detected.\n"
            f"- Review failed tasks and silent districts to improve reliability."
        )

    @staticmethod
    def _fmt_success_rate(metrics: dict) -> str:
        """'n/a' when no task outcomes were observed (0 attempts is not 0.0%)."""
        attempts = metrics.get("tasks_completed", 0) + metrics.get("tasks_failed", 0)
        if attempts == 0:
            return "n/a (no task outcomes recorded)"
        return f"{metrics.get('task_success_rate', 0):.1%}"

    # ── Obsidian report ───────────────────────────────────────────────────────────

    def write_analytics_report(
        self, metrics: dict, anomalies: list[dict], brief: str
    ) -> bool:
        """
        Writes a structured Obsidian note to Daily/ with ASCII bar charts.
        Stores a summary key in semantic_memory for trend tracking.
        """
        today = datetime.date.today().isoformat()
        title = f"VECTOR Analytics — {today}"

        # Build ASCII charts
        max_by_type = max(metrics.get("by_type", {1: 1}).values(), default=1)
        chart_types = ""
        for evt, cnt in sorted(
            metrics.get("by_type", {}).items(), key=lambda x: x[1], reverse=True
        )[:10]:
            bar = _ascii_bar(cnt, max_by_type)
            chart_types += f"  {evt:<30} {bar} {cnt}\n"

        max_by_hour = max(metrics.get("by_hour", {0: 1}).values(), default=1)
        chart_hours = ""
        for hour in range(24):
            cnt = metrics.get("by_hour", {}).get(hour, 0)
            bar = _ascii_bar(cnt, max_by_hour, width=12)
            chart_hours += f"  {hour:02d}:00  {bar} {cnt}\n"

        anomaly_md = ""
        for a in anomalies:
            if "date" in a:
                anomaly_md += (
                    f"  - {a['date']}: {a['error_count']} errors "
                    f"({a['ratio']}x avg) [{a['severity']}]\n"
                )
            elif "district" in a:
                anomaly_md += f"  - {a['district']}: {a['issue']} [{a['severity']}]\n"

        anomaly_section = anomaly_md or "  None detected.\n"
        content = (
            f"## Executive Brief\n\n{brief}\n\n"
            f"## Summary\n\n"
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| Total Events | {metrics.get('total_events', 0)} |\n"
            f"| Task Success Rate | {self._fmt_success_rate(metrics)} |\n"
            f"| Tasks Completed | {metrics.get('tasks_completed', 0)} |\n"
            f"| Tasks Failed | {metrics.get('tasks_failed', 0)} |\n"
            f"| Anomalies Detected | {len(anomalies)} |\n\n"
            f"## Activity by Event Type\n\n```\n{chart_types}```\n\n"
            f"## Activity by Hour of Day\n\n```\n{chart_hours}```\n\n"
            f"## Anomalies\n\n{anomaly_section}"
        )

        try:
            self._obsidian.write_note(
                title=title,
                content=content,
                folder="Daily",
                tags=["analytics", "weekly-brief", "vector"],
                overwrite=True,
            )
            logger.info(
                f"[VECTOR][analytics_reporter] report written: Daily/{title}.md"
            )

            # Store summary in semantic_memory for trend tracking
            summary_value = json.dumps(
                {
                    "date": today,
                    "total_events": metrics.get("total_events", 0),
                    "success_rate": metrics.get("task_success_rate", 0),
                    "anomaly_count": len(anomalies),
                },
                default=str,
            )
            self._memory.remember(
                f"analytics_report:{today}",
                summary_value,
                category="analytics",
                confidence=0.95,
            )
            return True
        except Exception as e:
            logger.error(
                f"[VECTOR][analytics_reporter] write_analytics_report failed: {e}"
            )
            return False

    # ── Full cycle ────────────────────────────────────────────────────────────────

    # 2026-07-30 audit fix: run() used to execute the same full weekly-report
    # cycle for ANY task_type, regardless of what was actually asked — so
    # requests misrouted here from other districts (pattern_detective,
    # predictive_analytics, coding/security mixups) got back an identical
    # canned report that looked like a confident, on-topic answer but
    # wasn't. classify_chat_intent's district-disambiguation hints (see
    # governor.py) now reduce how often that misroute happens in the first
    # place, but this is the honest backstop for when it still does.
    _OWN_TASK_TYPES = frozenset({
        "weekly_analytics", "analytics", "reporting", "anomaly_detection",
        "analytics_report", "system_analytics",
    })

    async def run(self, task: dict) -> dict:
        """Full analytics cycle: mine → metrics → anomalies → brief → report."""
        self.last_active = datetime.datetime.now(datetime.timezone.utc).isoformat()
        task_type = task.get("type", "weekly_analytics")

        if task_type not in self._OWN_TASK_TYPES:
            logger.warning(
                f"[VECTOR][analytics_reporter] got task_type={task_type!r}, "
                f"which isn't one of this agent's own capabilities "
                f"({sorted(self._OWN_TASK_TYPES)}) — likely a misroute from "
                f"another district. Refusing honestly instead of returning "
                f"the canned weekly-analytics report."
            )
            return {
                "status": "error",
                "task": task_type,
                "response": (
                    "That doesn't look like a request for VECTOR's own "
                    "internal usage analytics (which is what this district "
                    "actually does) — it may have been routed here by "
                    "mistake."
                ),
                "hp": self.health_points,
            }

        try:
            try:
                days = int((task.get("params") or {}).get("days", 7))
            except (TypeError, ValueError):
                days = 7
            days = max(1, min(days, 365))
            events = self.mine_episodic_data(days=days)
            if self.last_mine_error is not None:
                # Do not publish a report (and a "no anomalies / 0 events"
                # baseline) built from a failed DB pull.
                self.deduct_points(10, "event mining failed")
                return {
                    "status": "error",
                    "task": task_type,
                    "error": f"event mining failed: {self.last_mine_error}",
                    "hp": self.health_points,
                }
            metrics = self.compute_activity_metrics(events)
            anomalies = self.detect_anomalies(events)
            brief = self.generate_weekly_brief(metrics, anomalies)
            success = self.write_analytics_report(metrics, anomalies, brief)

            if success:
                self._memory.store(
                    event_type="analytics_report_generated",
                    content=(
                        f"Weekly analytics: {metrics.get('total_events', 0)} events, "
                        f"success_rate={self._fmt_success_rate(metrics)}, "
                        f"anomalies={len(anomalies)}"
                    ),
                    tags=["analytics", "report", task_type],
                    source="analytics_reporter",
                )
                self.award_points(30, "analytics report generated")
                return {
                    "status": "ok",
                    "task": task_type,
                    "total_events": metrics.get("total_events", 0),
                    "success_rate": metrics.get("task_success_rate", 0),
                    "anomaly_count": len(anomalies),
                    "hp": self.health_points,
                }
            else:
                self.deduct_points(10, "report write failed")
                return {"status": "error", "task": task_type, "hp": self.health_points}

        except Exception as e:
            logger.error(f"[VECTOR][analytics_reporter] run failed: {e}")
            self.deduct_points(15, f"run exception: {e}")
            return {"status": "error", "error": str(e), "hp": self.health_points}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = AnalyticsReporter()
        assert agent.health_points == 500

        # Mine data (may be empty in a fresh DB — that is fine)
        events = agent.mine_episodic_data(days=7)
        metrics = agent.compute_activity_metrics(events)
        assert "total_events" in metrics
        assert "task_success_rate" in metrics

        anomalies = agent.detect_anomalies(events)
        assert isinstance(anomalies, list)

        brief = agent.generate_weekly_brief(metrics, anomalies)
        assert isinstance(brief, str) and len(brief) > 0

        result = await agent.run({"type": "weekly_analytics", "params": {"days": 7}})
        assert result["status"] in ("ok", "error")  # error is fine if vault path absent
        print(
            f"OK analytics_reporter.py HP={agent.health_points} "
            f"events={metrics['total_events']} anomalies={len(anomalies)}"
        )

    asyncio.run(_smoke())
