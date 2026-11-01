"""
Module: agents/pattern_detective/habit_finder.py
District: pattern_detective | Focus: Analyze screen time, find habits from memory
"""

import sys
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime, collections
from typing import Optional


class HabitFinder(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="HabitFinder",
            district="pattern_detective",
            generation=1
        )
        self.capabilities = ["habit", "pattern", "pattern_detective"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.habit_patterns = {}
        logger.info("[VECTOR][pattern_detective] HabitFinder ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
            district=self.district,
            sensitive=True,
            allow_cloud=False,  # habit/behavioural data about the owner: local Ollama only
        )

    _OWN_SOURCES = frozenset({"BehaviorAnalyst", "HabitFinder"})

    @staticmethod
    def _to_float(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def analyze_screen_time(self, data: list[dict]) -> dict:
        data = [d for d in (data or []) if isinstance(d, dict)]
        logger.info("[VECTOR][pattern_detective] Analyzing screen time: {} records", len(data))
        self.add_lesson({"action": "analyze_screen_time", "records": len(data)})

        if not data:
            # Empty/failed pull: not "0 min/day, peak at noon, healthy usage".
            return {"status": "no_data", "total_records": 0, "days_tracked": 0, "insights": ""}

        daily_totals = collections.defaultdict(int)
        app_usage = collections.defaultdict(int)
        hourly_totals = collections.defaultdict(int)

        for entry in data:
            date = entry.get("date", "")
            app = entry.get("app", "unknown")
            duration = self._to_float(entry.get("duration_minutes", 0))
            hour = entry.get("hour")

            if date:
                daily_totals[date] += duration
            app_usage[app] += duration
            if hour is not None:
                # A missing hour used to be counted as 12:00, fabricating a
                # noon peak.
                hourly_totals[hour] += duration

        avg_daily = round(sum(daily_totals.values()) / max(len(daily_totals), 1), 1)
        top_apps = sorted(app_usage.items(), key=lambda x: x[1], reverse=True)[:5]

        peak_hour = max(hourly_totals, key=hourly_totals.get) if hourly_totals else None

        analysis = {
            "total_records": len(data),
            "days_tracked": len(daily_totals),
            "average_daily_minutes": avg_daily,
            "total_minutes": sum(daily_totals.values()),
            "top_apps": [{"app": a, "minutes": m} for a, m in top_apps],
            "peak_hour": peak_hour,
            "hourly_breakdown": dict(hourly_totals),
        }

        prompt = f"Analyze this screen time data and identify patterns:\n{json.dumps(analysis, indent=2)}\nProvide: 1) Habit pattern identification, 2) Recommendations for healthy usage, 3) Red flags if any."
        insights = self._call_ollama(prompt)
        if not (insights or "").strip():
            logger.warning("[VECTOR][pattern_detective] Screen-time analysis: LLM returned nothing")
            analysis["status"] = "error"
            analysis["error"] = "llm_unavailable"
            analysis["insights"] = ""
            return analysis
        analysis["status"] = "ok"
        analysis["insights"] = insights

        self.memory.store(
            event_type="screen_time_analyzed",
            content=f"Analyzed {len(data)} screen time records, avg {avg_daily} min/day",
            tags=["pattern", "screen_time", "habits"],
            context=analysis,
            source="HabitFinder"
        )

        return analysis

    def find_habits(self, episodic_events: list[dict]) -> dict:
        episodic_events = [e for e in (episodic_events or []) if isinstance(e, dict)]
        logger.info("[VECTOR][pattern_detective] Finding habits from {} events", len(episodic_events))
        self.add_lesson({"action": "find_habits", "events": len(episodic_events)})

        if not episodic_events:
            # Nothing to analyse is "no data", not "no habits found".
            return {"status": "no_data", "total_events": 0, "recurring_patterns": {},
                    "frequent_actions": [], "patterns_found": 0}

        time_patterns = collections.defaultdict(list)
        action_patterns = collections.defaultdict(int)
        bad_timestamps = 0

        for event in episodic_events:
            event_type = event.get("event_type", "")
            timestamp = event.get("timestamp", "")
            timestamp = event.get("timestamp") or ""

            if timestamp:
                try:
                    dt = datetime.datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                    hour_key = f"{dt.hour:02d}:00"
                    day_key = dt.strftime("%A")
                    time_patterns[f"hourly_{hour_key}"].append(event)
                    time_patterns[f"weekly_{day_key}"].append(event)
                except ValueError:
                    bad_timestamps += 1

            if event_type:
                action_patterns[event_type] += 1

        if bad_timestamps:
            logger.warning("[VECTOR][pattern_detective] {} event(s) had unparseable timestamps; excluded from time patterns", bad_timestamps)

        recurring = {}
        for pattern_key, events in time_patterns.items():
            if len(events) >= 3:
                recurring[pattern_key] = {
                    "count": len(events),
                    "percentage": round(len(events) / len(episodic_events) * 100, 2),
                    "examples": [(e.get("content") or "")[:100] for e in events[:3]],
                }

        frequent_actions = [{"action": a, "count": c} for a, c in sorted(action_patterns.items(), key=lambda x: x[1], reverse=True)[:10]]

        result = {
            "status": "ok",
            "total_events": len(episodic_events),
            "recurring_patterns": recurring,
            "frequent_actions": frequent_actions,
            "patterns_found": len(recurring),
        }

        self.habit_patterns = recurring

        self.memory.store(
            event_type="habits_found",
            content=f"Found {len(recurring)} recurring patterns from {len(episodic_events)} events",
            tags=["pattern", "habits", "detection"],
            context=result,
            source="HabitFinder"
        )

        logger.info("[VECTOR][pattern_detective] Found {} habits", len(recurring))
        return result

    def generate_habit_report(self) -> dict:
        logger.info("[VECTOR][pattern_detective] Generating habit analysis report")
        self.add_lesson({"action": "generate_habit_report"})

        patterns = self.habit_patterns
        if not patterns:
            # Exclude this district's own derived events (they would otherwise
            # be "discovered" as the owner's habits).
            events = [e for e in (self.memory.recall("", limit=50) or [])
                      if e.get("source") not in self._OWN_SOURCES]
            if events:
                self.find_habits(events)
            patterns = self.habit_patterns

        if not patterns:
            # No patterns (no events, or none recurring): do not ask the LLM to
            # write a "comprehensive habit report" about nothing.
            return {"status": "no_data", "patterns_analyzed": 0, "habit_report": ""}

        prompt = f"""Generate a comprehensive habit analysis report based on these detected patterns:
{json.dumps({k: {kk: str(vv)[:200] for kk, vv in v.items()} for k, v in list(patterns.items())[:10]}, indent=2)}
Include: 1) Summary of key habits, 2) Pattern strength analysis, 3) Behavioral insights, 4) Habit improvement recommendations, 5) Risk indicators."""
        report = self._call_ollama(prompt)
        if not (report or "").strip():
            logger.warning("[VECTOR][pattern_detective] Habit report: LLM returned nothing")
            return {"status": "error", "error": "llm_unavailable",
                    "patterns_analyzed": len(patterns), "habit_report": ""}

        result = {
            "status": "ok",
            "patterns_analyzed": len(patterns),
            "habit_report": report,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="habit_report_generated",
            content=f"Generated habit report with {len(patterns)} patterns",
            tags=["pattern", "report", "habits"],
            context=result,
            source="HabitFinder"
        )

        return result


    async def run(self, task: dict) -> dict:
        result = self.generate_habit_report()
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = HabitFinder()
    assert agent.district == "pattern_detective"

    screen_data = [
        {"date": "2026-05-01", "app": "Chrome", "duration_minutes": 120, "hour": 14},
        {"date": "2026-05-01", "app": "VSCode", "duration_minutes": 180, "hour": 15},
        {"date": "2026-05-02", "app": "Chrome", "duration_minutes": 90, "hour": 14},
        {"date": "2026-05-02", "app": "Slack", "duration_minutes": 30, "hour": 10},
    ]
    analysis = agent.analyze_screen_time(screen_data)
    assert "average_daily_minutes" in analysis
    assert analysis["average_daily_minutes"] > 0

    events = [
        {"event_type": "coding", "timestamp": "2026-05-01T14:00:00Z", "content": "Started coding session"},
        {"event_type": "coding", "timestamp": "2026-05-02T14:30:00Z", "content": "Continued coding"},
        {"event_type": "coding", "timestamp": "2026-05-03T14:15:00Z", "content": "More coding"},
        {"event_type": "reading", "timestamp": "2026-05-01T20:00:00Z", "content": "Read book"},
    ]
    habits = agent.find_habits(events)
    assert "recurring_patterns" in habits

    report = agent.generate_habit_report()
    assert "habit_report" in report

    print("✅ habit_finder.py OK")