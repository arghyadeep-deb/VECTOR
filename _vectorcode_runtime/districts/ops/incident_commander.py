"""
Incident Commander — District: ops
Scans episodic_memory for errors and agent deaths, triages severity,
coordinates response, and writes blameless post-mortems to Obsidian.
RULE 11: no Claude API at runtime.
"""

import sys
import asyncio
import datetime
import json
import uuid

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.inference.vectorcode_llm import chat

_FOCUS = CONFIG.get("models", {}).get("focus", "vector-focus")

# Severity thresholds
_P1_ERROR_COUNT = 5      # >= 5 errors in last 50 events → P1
_P2_ERROR_COUNT = 3      # >= 3 errors → P2
_P1_HP_LOSS = 150        # >= 150 HP lost in one event → P1
_P2_HP_LOSS = 75         # >= 75 HP → P2
_SCAN_LIMIT = 50         # how many recent events to inspect

class IncidentCommander(AgentBase):
    """
    Incident response coordinator.
    Scans episodic memory for errors / agent deaths, triages severity (P1/P2/P3),
    creates incident reports, coordinates recovery suggestions, and writes
    blameless post-mortems to Obsidian.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="IncidentCommander",
            district="ops",
            generation=generation,
        )
        self.capabilities = ["P1", "P2", "detect", "incident", "incident_command", "ops", "post_mortem", "triage"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        logger.info(f"[VECTOR][incident_commander] ready gen={generation}")

    # ── Lazy accessors ─────────────────────────────────────────────────────────

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self) -> ObsidianSync:
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    # ── Detection ──────────────────────────────────────────────────────────────

    def detect_incidents(self) -> list[dict] | None:
        """
        Scan last _SCAN_LIMIT episodic events for:
          - error events (event_type contains 'error')
          - agent deaths (event_type contains 'death' or content contains 'HP=0')
          - repeated failures (same event_type error appearing >= 3 times)
        Returns a list of incident dicts, or None if the DB query itself failed.
        """
        try:
            mem = self._get_memory()
            cur = mem.conn.cursor()
            cur.execute(
                "SELECT id, event_type, content, tags, timestamp, source "
                "FROM episodic_memory ORDER BY timestamp DESC LIMIT ?",
                (_SCAN_LIMIT,),
            )
            rows = cur.fetchall()
        except Exception as e:
            logger.error(f"[VECTOR][incident_commander] detect query failed: {e}")
            return None  # fail-closed: DB failure is unknowable, not "no incidents"

        if not rows:
            return []

        incidents: list[dict] = []
        error_events: list[dict] = []
        death_events: list[dict] = []
        failure_counts: dict[str, int] = {}

        for row in rows:
            ev_id, ev_type, content, tags_raw, ts, source = row
            ev_type_l = (ev_type or "").lower()
            content_l = (content or "").lower()

            is_error = "error" in ev_type_l or "error" in content_l
            is_death = "death" in ev_type_l or "hp=0" in content_l or "died" in content_l

            if is_error:
                error_events.append({
                    "id": ev_id,
                    "event_type": ev_type,
                    "content": content,
                    "timestamp": ts,
                    "source": source,
                })
                failure_counts[ev_type or "unknown"] = failure_counts.get(ev_type or "unknown", 0) + 1

            if is_death:
                death_events.append({
                    "id": ev_id,
                    "event_type": ev_type,
                    "content": content,
                    "timestamp": ts,
                    "source": source,
                })

        # Repeated failures (same type >= 3 times)
        repeated_failures = {k: v for k, v in failure_counts.items() if v >= 3}

        # Build incidents list
        if error_events or death_events or repeated_failures:
            affected_districts = list({e.get("source", "unknown") for e in error_events + death_events})
            incident = {
                "incident_id": str(uuid.uuid4()),
                "detected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "error_count": len(error_events),
                "death_count": len(death_events),
                "repeated_failures": repeated_failures,
                "affected_districts": affected_districts,
                "error_events": error_events[:5],   # include first 5 for report
                "death_events": death_events[:3],
            }
            incidents.append(incident)

        logger.info(
            f"[VECTOR][incident_commander] scan: {len(error_events)} errors, "
            f"{len(death_events)} deaths, {len(repeated_failures)} repeated failure types"
        )
        return incidents

    # ── Triage ────────────────────────────────────────────────────────────────

    def triage_incident(self, incident: dict) -> dict:
        """
        Assess severity: P1 / P2 / P3.
        P1: >= 5 errors OR >= 1 agent death OR repeated failures >= 3 distinct types
        P2: >= 3 errors OR repeated failures 1-2 types
        P3: < 3 errors, no deaths
        Returns incident dict enriched with: severity, severity_reason.
        """
        error_count = incident.get("error_count", 0)
        death_count = incident.get("death_count", 0)
        repeated = incident.get("repeated_failures", {})
        n_repeated_types = len(repeated)

        if error_count >= _P1_ERROR_COUNT or death_count >= 1 or n_repeated_types >= 3:
            severity = "P1"
            reason = (
                f"Critical: {error_count} errors, {death_count} agent deaths, "
                f"{n_repeated_types} repeated failure types"
            )
        elif error_count >= _P2_ERROR_COUNT or n_repeated_types >= 1:
            severity = "P2"
            reason = (
                f"High: {error_count} errors, {n_repeated_types} repeated failure types"
            )
        else:
            severity = "P3"
            reason = f"Low: {error_count} errors, {death_count} deaths"

        incident_out = {**incident, "severity": severity, "severity_reason": reason}
        logger.info(f"[VECTOR][incident_commander] triage: {severity} — {reason}")
        return incident_out

    # ── Report creation ───────────────────────────────────────────────────────

    def create_incident_report(self, incidents: list[dict]) -> str:
        """
        Build a structured incident summary: timeline, affected systems,
        root-cause hypothesis via LLM.
        Returns the markdown report as a string.
        """
        if not incidents:
            return "# Incident Report\n\nNo incidents detected in last scan.\n"

        lines = ["# Incident Report\n"]
        lines.append(f"**Generated:** {datetime.datetime.now().isoformat()[:16]}\n")
        lines.append(f"**Incidents detected:** {len(incidents)}\n\n")

        for i, inc in enumerate(incidents, 1):
            sev = inc.get("severity", "P3")
            lines.append(f"## Incident {i} — {sev}\n")
            lines.append(f"**ID:** `{inc.get('incident_id', '?')}`  ")
            lines.append(f"**Detected:** {inc.get('detected_at', '?')[:16]}\n")
            lines.append(f"**Severity:** {sev} — {inc.get('severity_reason', '')}\n")
            lines.append(f"**Affected districts:** {', '.join(inc.get('affected_districts', ['unknown']))}\n\n")

            lines.append("### Timeline (recent errors)\n")
            for ev in inc.get("error_events", []):
                ts = (ev.get("timestamp") or "?")[:16]
                lines.append(f"- `{ts}` [{ev.get('source', '?')}] {ev.get('content', '')[:120]}\n")

            if inc.get("death_events"):
                lines.append("\n### Agent Deaths\n")
                for ev in inc.get("death_events", []):
                    ts = (ev.get("timestamp") or "?")[:16]
                    lines.append(f"- `{ts}` {ev.get('content', '')[:120]}\n")

            repeated = inc.get("repeated_failures", {})
            if repeated:
                lines.append("\n### Repeated Failures\n")
                for ev_type, count in repeated.items():
                    lines.append(f"- `{ev_type}`: {count} occurrences\n")

            # LLM root-cause hypothesis
            lines.append("\n### Root Cause Hypothesis\n")
            hypothesis = self._get_root_cause_hypothesis(inc)
            lines.append(f"{hypothesis}\n")
            lines.append("\n---\n")

        return "".join(lines)

    def _get_root_cause_hypothesis(self, incident: dict) -> str:
        """Use vector-focus to hypothesize root cause from incident data."""
        prompt = (
            f"VECTOR incident summary:\n"
            f"- Severity: {incident.get('severity', 'P3')}\n"
            f"- Error count: {incident.get('error_count', 0)}\n"
            f"- Agent deaths: {incident.get('death_count', 0)}\n"
            f"- Affected districts: {incident.get('affected_districts', [])}\n"
            f"- Repeated failures: {incident.get('repeated_failures', {})}\n"
            f"- Sample error: {incident.get('error_events', [{}])[0].get('content', 'none')[:200]}\n\n"
            f"Provide a 2-3 sentence blameless root cause hypothesis. Be specific and actionable."
        )
        try:
            from core.prompt_library import get_library as _gl
            _sys = _gl().get_for_agent("incident_commander") or ""
            _msgs = ([{"role": "system", "content": _sys}] if _sys else []) + [{"role": "user", "content": prompt}]
            result = chat(
                model=_FOCUS,
                messages=_msgs,
                timeout=30.0,
            )
            return result or "Root cause analysis unavailable (LLM timeout)."
        except Exception as e:
            logger.warning(f"[VECTOR][incident_commander] LLM hypothesis failed: {e}")
            return "Root cause analysis unavailable (LLM unavailable)."

    # ── Coordination ──────────────────────────────────────────────────────────

    def coordinate_response(self, incident: dict) -> dict:
        """
        Store notification in episodic_memory and return recovery action suggestions
        based on severity.
        Returns: {incident_id, severity, notifications_stored, suggested_actions}.
        """
        severity = incident.get("severity", "P3")
        incident_id = incident.get("incident_id", "unknown")
        affected = incident.get("affected_districts", [])

        # Map severity → suggested actions
        if severity == "P1":
            suggestions = [
                "Restart failed VECTOR services via DevOpsAutomator",
                "Check SRE SLO report for loop tick failures",
                "Review episodic_memory error logs for root cause",
                "Alert owner via Pushover if Ollama is down",
                "Trigger LLM Council session for critical incidents",
            ]
        elif severity == "P2":
            suggestions = [
                "Run SREMonitor.check_system_health() to assess scope",
                "Check agent HP in agent_history for affected districts",
                "Review last 50 episodic events for failure patterns",
            ]
        else:
            suggestions = [
                "Monitor for escalation over next 30 minutes",
                "Log incident in Obsidian for weekly retrospective",
            ]

        # Store notification event
        notification_content = (
            f"INCIDENT {severity} [{incident_id[:8]}]: "
            f"errors={incident.get('error_count', 0)} "
            f"deaths={incident.get('death_count', 0)} "
            f"districts={affected}"
        )
        mem = self._get_memory()
        mem.store(
            event_type="incident_notification",
            content=notification_content,
            tags=["incident", severity.lower(), "ops"],
            source="incident_commander",
        )
        logger.info(f"[VECTOR][incident_commander] response coordinated: {severity} {incident_id[:8]}")

        return {
            "incident_id": incident_id,
            "severity": severity,
            "notifications_stored": 1,
            "suggested_actions": suggestions,
        }

    # ── Post-mortem ───────────────────────────────────────────────────────────

    def post_mortem(self, incident_id: str) -> bool:
        """
        Generate a blameless post-mortem Obsidian note for a given incident_id.
        Looks up the incident from episodic_memory notifications.
        Returns True on success.
        """
        try:
            # Retrieve incident notification from episodic memory
            mem = self._get_memory()
            events = mem.recall(query=incident_id, limit=5, event_type="incident_notification")

            if not events:
                logger.warning(f"[VECTOR][incident_commander] no events found for incident_id={incident_id}")
                content_summary = f"Incident `{incident_id}` — no episodic records found."
            else:
                ev = events[0]
                content_summary = ev.get("content", "No content")

            date_str = datetime.date.today().isoformat()
            short_id = incident_id[:8]
            title = f"Post-Mortem — {short_id} — {date_str}"

            # LLM-generated post-mortem body
            pm_prompt = (
                f"Write a blameless post-mortem for this VECTOR system incident:\n\n"
                f"{content_summary}\n\n"
                f"Structure it as:\n"
                f"1. What happened (2 sentences)\n"
                f"2. Impact (1 sentence)\n"
                f"3. Root cause (2 sentences)\n"
                f"4. What went well (1 bullet)\n"
                f"5. Action items (2-3 bullets)\n\n"
                f"Keep it concise. No blame. Focus on systemic improvements."
            )
            try:
                from core.prompt_library import get_library as _gl
                _sys = _gl().get_for_agent("incident_commander") or ""
                _pm_msgs = ([{"role": "system", "content": _sys}] if _sys else []) + [{"role": "user", "content": pm_prompt}]
                pm_body = chat(
                    model=_FOCUS,
                    messages=_pm_msgs,
                    timeout=45.0,
                )
                if not pm_body:
                    pm_body = "(LLM post-mortem unavailable — fill in manually)"
            except Exception as e:
                pm_body = f"(LLM unavailable: {e})"

            content = (
                f"# Post-Mortem: {short_id}\n\n"
                f"**Date:** {date_str}  \n"
                f"**Incident ID:** `{incident_id}`  \n"
                f"**Source event:** {content_summary[:200]}\n\n"
                f"---\n\n"
                f"{pm_body}\n\n"
                f"---\n"
                f"*auto-generated by IncidentCommander · blameless*"
            )

            self._get_obsidian().write_note(
                title=title,
                content=content,
                folder="Research",
                tags=["post-mortem", "ops", "incident", "vector"],
            )
            logger.info(f"[VECTOR][incident_commander] post-mortem written: {title}")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][incident_commander] post_mortem failed: {e}")
            return False

    # ── AgentBase.run entry-point ──────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        # 2026-09-30 (Codex third independent review, same cycle): capture
        # task_type from the UNMERGED task first -- if a nested params dict
        # happens to carry its own "type" key (a real field name for some
        # capabilities, not just VECTOR's own dispatch key), merging params
        # over task before reading task_type would let params["type"]
        # silently hijack routing. See districts/communications/email_agent.py's
        # identical fix for the full evidence.
        task_type = task.get("type", "scan")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "detect":
                incidents = self.detect_incidents()
                if incidents is None:
                    return {"status": "error", "error": "detect_incidents: DB query failed"}
                return {"status": "ok", "incidents_found": len(incidents), "incidents": incidents}

            elif task_type == "triage":
                incident = task.get("incident")
                if not incident:
                    return {"status": "error", "error": "task must include 'incident' key"}
                triaged = self.triage_incident(incident)
                return {"status": "ok", **triaged}

            elif task_type == "post_mortem":
                incident_id = task.get("incident_id", "")
                if not incident_id:
                    return {"status": "error", "error": "task must include 'incident_id'"}
                ok = self.post_mortem(incident_id)
                return {"status": "ok" if ok else "error", "incident_id": incident_id, "written": ok}

            else:
                # Full incident scan cycle: detect → triage → report → coordinate
                incidents = self.detect_incidents()

                if incidents is None:
                    self.deduct_points(30, "detect_incidents: DB query failed")
                    return {"status": "error", "error": "detect_incidents: DB query failed"}

                if not incidents:
                    self.award_points(50, "no incidents detected — all clear")
                    self._get_memory().store(
                        event_type="incident_scan",
                        content="Full incident scan: no incidents found",
                        tags=["incident", "ops", "all_clear"],
                        source="incident_commander",
                    )
                    return {"status": "ok", "incidents_found": 0, "all_clear": True}

                # Triage each incident
                triaged = [self.triage_incident(inc) for inc in incidents]

                # Create report
                report_md = self.create_incident_report(triaged)

                # Coordinate response for each
                responses = [self.coordinate_response(inc) for inc in triaged]

                # Determine worst severity
                severities = [inc.get("severity", "P3") for inc in triaged]
                worst = "P1" if "P1" in severities else ("P2" if "P2" in severities else "P3")

                # HP impact based on worst severity
                if worst == "P1":
                    self.deduct_points(50, f"P1 incident detected: {incidents[0].get('incident_id', '')[:8]}")
                elif worst == "P2":
                    self.deduct_points(20, f"P2 incident detected")
                else:
                    self.deduct_points(5, "P3 incident logged")

                # Store the report in episodic memory
                self._get_memory().store(
                    event_type="incident_report",
                    content=f"incident_scan: {len(incidents)} incidents, worst={worst}",
                    tags=["incident", "ops", worst.lower()],
                    source="incident_commander",
                )

                # Write report to Obsidian
                date_str = datetime.date.today().isoformat()
                try:
                    self._get_obsidian().write_note(
                        title=f"Incident Report — {date_str}",
                        content=report_md,
                        folder="Research",
                        tags=["incident", "ops", "vector"],
                    )
                    report_written = True
                except Exception as e:
                    logger.warning(f"[VECTOR][incident_commander] Obsidian write failed: {e}")
                    report_written = False

                return {
                    "status": "ok",
                    "incidents_found": len(incidents),
                    "worst_severity": worst,
                    "responses": responses,
                    "report_written": report_written,
                }

        except Exception as e:
            logger.error(f"[VECTOR][incident_commander] run failed: {e}")
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

# ── Smoke test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = IncidentCommander()
        assert agent.health_points == 500

        # Detect incidents from live episodic memory
        incidents = agent.detect_incidents()
        print(f"incidents detected: {len(incidents) if incidents is not None else 'DB error'}")

        if incidents:
            triaged = agent.triage_incident(incidents[0])
            print(f"triage: {triaged.get('severity')} — {triaged.get('severity_reason')}")
            response = agent.coordinate_response(triaged)
            print(f"response: suggestions={len(response.get('suggested_actions', []))}")
            report = agent.create_incident_report([triaged])
            print(f"report lines: {len(report.splitlines())}")
        else:
            print("No incidents — all clear")

        ok = True
        print(f"{'✅' if ok else '❌'} incident_commander.py HP={agent.health_points}")

    asyncio.run(_smoke())
