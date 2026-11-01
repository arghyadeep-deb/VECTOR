from __future__ import annotations

import sys
from pathlib import Path

import asyncio
import datetime
import uuid
from typing import Any

from loguru import logger

from core.config import CONFIG
from core.runtime_paths import data_path
from core.city.agent_base import AgentBase
from districts.security.log_aggregator import LogAggregator, LogEvent
from districts.security.detection_rules import DetectionRules, RuleMatch
from districts.security.incident_playbook_runner import IncidentPlaybookRunner, Incident


class SIEMPipeline(AgentBase):
    """Security Information and Event Management pipeline.

    Connects LogAggregator → DetectionRules → IncidentPlaybookRunner.
    Loguru sink wires all VECTOR log output into the aggregator automatically.
    """

    def __init__(
        self,
        db_path: str | None = None,
        rules_dir: str | None = None,
        playbooks_dir: str | None = None,
        incidents_db_path: str | None = None,
    ) -> None:
        super().__init__(str(uuid.uuid4()), "SIEMPipeline", "security")
        self.capabilities = ["alerts", "process_event", "process_event_async", "security", "siem", "source", "stats", "threat"]
        self.log_aggregator = LogAggregator(db_path=db_path)
        self.detection_rules = DetectionRules(rules_dir=rules_dir)
        self.playbook_runner = IncidentPlaybookRunner(
            playbooks_dir=playbooks_dir,
            db_path=incidents_db_path
            or str((Path(db_path).parent if db_path else data_path("security")) / "incidents.db"),
        )
        self._alerts: list[dict] = []
        self._sink_id: int | None = None
        logger.info(
            "[VECTOR][siem] pipeline ready — {} rules, {} playbooks",
            len(self.detection_rules._rules),
            len(self.playbook_runner._playbooks),
        )

    def wire_loguru_sink(self) -> None:
        """Add the LogAggregator as a loguru sink (WARNING+ only, to reduce noise)."""
        if self._sink_id is not None:
            return
        sink = self.log_aggregator.make_sink()
        self._sink_id = logger.add(sink, level="WARNING", colorize=False)
        logger.info("[VECTOR][siem] loguru sink wired (WARNING+ forwarded to aggregator)")

    def unwire_loguru_sink(self) -> None:
        if self._sink_id is not None:
            logger.remove(self._sink_id)
            self._sink_id = None

    # ------------------------------------------------------------------
    # Synchronous processing (no playbook execution)
    # ------------------------------------------------------------------

    def process_event(self, event: dict) -> list[dict]:
        """Ingest event → evaluate rules → return triggered alerts.

        Does NOT execute playbooks (use async_process_event for that).
        Stores the event in the log aggregator synchronously.
        """
        log_event = LogEvent(
            service=event.get("source", "siem"),
            level=event.get("level", "INFO").upper(),
            message=event.get("message", ""),
            extra={k: v for k, v in event.items() if k not in ("source", "level", "message")},
        )
        self.log_aggregator._store_event(log_event)

        matches = self.detection_rules.evaluate(event)
        triggered: list[dict] = []

        for match in matches:
            playbook_ids = self._parse_playbook_ids(match.suggested_action)
            alert = {
                "alert_id": str(uuid.uuid4()),
                "rule_name": match.rule_name,
                "severity": match.severity,
                "evidence": match.evidence,
                "suggested_action": match.suggested_action,
                "playbook_ids": playbook_ids,
                "triggered_at": match.triggered_at,
                "incident_ids": [],
            }
            self._alerts.append(alert)
            triggered.append(alert)
            logger.warning(
                "[VECTOR][siem] ALERT rule='{}' sev={} playbooks={}",
                match.rule_name, match.severity, playbook_ids,
            )

        return triggered

    # ------------------------------------------------------------------
    # Async processing (includes playbook execution)
    # ------------------------------------------------------------------

    async def async_process_event(self, event: dict) -> list[dict]:
        """Full async pipeline: ingest → detect → execute playbooks."""
        triggered = self.process_event(event)

        for alert in triggered:
            for pb_id in alert["playbook_ids"]:
                pb = self.playbook_runner._playbooks.get(pb_id)
                if pb is None:
                    logger.warning("[VECTOR][siem] playbook '{}' not found", pb_id)
                    continue
                try:
                    incident = await self.playbook_runner.execute_playbook(
                        pb, alert["evidence"], alert["alert_id"]
                    )
                    alert["incident_ids"].append(incident.id)
                    logger.info(
                        "[VECTOR][siem] playbook '{}' executed — incident={} status={}",
                        pb_id, incident.id[:8], incident.status,
                    )
                except Exception as e:
                    logger.error("[VECTOR][siem] playbook '{}' failed: {}", pb_id, e)

        return triggered

    # ------------------------------------------------------------------
    # Async loop (continuous processing from aggregator queue)
    # ------------------------------------------------------------------

    async def run_pipeline_loop(self) -> None:
        """Continuously drain the aggregator queue → detection → playbooks."""
        logger.info("[VECTOR][siem] pipeline loop started")
        while True:
            try:
                event = await asyncio.wait_for(
                    self.log_aggregator._queue.get(), timeout=1.0
                )
                self.log_aggregator._store_event(event)
                event_dict = event.model_dump()
                event_dict["source"] = event.service
                await self.async_process_event(event_dict)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("[VECTOR][siem] pipeline loop error: {}", e)

    # ------------------------------------------------------------------
    # Stats and query helpers
    # ------------------------------------------------------------------

    def get_alerts(self, limit: int = 50) -> list[dict]:
        return self._alerts[-limit:]

    def get_stats(self) -> dict:
        log_stats = self.log_aggregator.get_stats()
        return {
            "log_stats": log_stats,
            "rules_loaded": len(self.detection_rules._rules),
            "playbooks_loaded": len(self.playbook_runner._playbooks),
            "alerts_total": len(self._alerts),
            "alerts_by_severity": self._severity_breakdown(),
        }

    def _severity_breakdown(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in self._alerts:
            sev = str(a.get("severity", "?"))
            counts[sev] = counts.get(sev, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_playbook_ids(suggested_action: str) -> list[str]:
        ids = []
        for part in suggested_action.split(", "):
            part = part.strip()
            if part.startswith("playbook:"):
                ids.append(part[len("playbook:"):])
        return ids

    async def run(self, task: dict | None = None) -> dict:
        task = task or {}
        task_type = task.get("type") or "stats"
        params = task.get("params") or {}
        supported = ["alerts", "process_event", "process_event_async", "stats"]

        if task_type in ("stats", "get_stats"):
            return {"status": "ok", **self.get_stats()}
        if task_type in ("alerts", "get_alerts"):
            return {"status": "ok", "alerts": self.get_alerts(**params)}
        if task_type == "process_event":
            return {"status": "ok", "triggered": self.process_event(params.get("event", params))}
        if task_type == "process_event_async":
            return {"status": "ok", "triggered": await self.async_process_event(params.get("event", params))}

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "give me a summary of recent SIEM activity and any triggered
        # alerts" previously hit the bare "unhandled type" error stub.
        # Route it to the same get_stats() this agent already treats as its
        # safe, argument-free DEFAULT when task_type is entirely absent (see
        # task_type = task.get("type") or "stats" above) — read-only, never
        # ingests a fabricated event or executes a playbook from free text.
        query = (
            params.get("query") or params.get("content")
            or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            # get_stats() already folds in alerts_total/alerts_by_severity,
            # so it answers both a "summary" and an "any alerts?" question
            # with one real, read-only call.
            return {"status": "ok", **self.get_stats()}

        return {
            "status": "error",
            "error": f"unhandled type: {task_type}",
            "supported": supported,
        }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile
    import os

    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test_logs.db")
    inc_path = os.path.join(tmp_dir, "test_incidents.db")

    pipeline = SIEMPipeline(db_path=db_path, incidents_db_path=inc_path)

    # Test pattern rule — log clearing (T1070, severity 9)
    alerts = pipeline.process_event({
        "source": "log_aggregator",
        "level": "WARNING",
        "message": "wevtutil cl Security",
    })
    print(f"Log clearing test — alerts: {len(alerts)}")
    for a in alerts:
        print(f"  ALERT: {a['rule_name']} sev={a['severity']} playbooks={a['playbook_ids']}")

    # Test threshold rule — high CPU (T1496)
    alerts2 = pipeline.process_event({
        "source": "system_monitor",
        "level": "WARNING",
        "message": "cpu usage spike",
        "cpu_percent": 97.5,
    })
    print(f"High CPU test — alerts: {len(alerts2)}")

    stats = pipeline.get_stats()
    print(f"Stats: {stats['alerts_total']} total alerts, {stats['rules_loaded']} rules, {stats['playbooks_loaded']} playbooks")

    # Cleanup
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("siem_pipeline.py OK")
