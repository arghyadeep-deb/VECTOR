from __future__ import annotations

import asyncio
import datetime
import time
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

from core.config import CONFIG
from core.city.agent_base import AgentBase
from .detector import EmergencyDetector, EmergencyEvent

_system_instance: EmergencyResponseSystem | None = None
from .classifier import SeverityClassifier, ScoredEmergency
from .runbook import RunbookExecutor
from .escalation import EscalationManager
from .log import EmergencyLog, EmergencyLogEntry

def set_instance(instance: EmergencyResponseSystem | None) -> None:
    global _system_instance
    _system_instance = instance

async def _emit(domain: str, signal_name: str, value: Any, source: str = "external", context: dict[str, Any] | None = None) -> EmergencyEvent | None:
    if _system_instance is not None:
        return await _system_instance.emit_signal(domain, signal_name, value, source, context)
    logger.warning("[VECTOR][emergency] signal {}:{} from {} DROPPED — EmergencyResponseSystem not started", domain, signal_name, source)
    return None

class EmergencyResponseSystem(AgentBase):
    def __init__(self, test_mode: bool = False):
        super().__init__(
            agent_id=f"emergency_response_{int(time.time())}",
            name="emergency_response",
            district="emergency",
        )
        self.capabilities = ["CRITICAL", "detect_anomaly", "escalate_emergency", "health", "runbook"]
        self._config = CONFIG.get("emergency", {})
        self._detector = EmergencyDetector()
        self._classifier = SeverityClassifier()
        self._runbook = RunbookExecutor()
        self._escalation = EscalationManager(test_mode=test_mode)
        self._log = EmergencyLog()
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self._running = True
        set_instance(self)
        for domain in ("health", "security", "system", "network", "disk", "battery"):
            queue = self._detector.subscribe_signal(domain)
            self._tasks.append(asyncio.create_task(
                self._process_queue(domain, queue),
                name=f"emergency-{domain}",
            ))
        logger.info("[EmergencyResponseSystem] started — monitoring {} domains", len(self._tasks))

    async def stop(self) -> None:
        self._running = False
        set_instance(None)
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("[EmergencyResponseSystem] stopped")

    async def emit_signal(self, domain: str, signal_name: str, value: Any, source: str = "external", context: dict[str, Any] | None = None) -> EmergencyEvent | None:
        return await self._detector.process_signal(domain, signal_name, value, source, context or {})

    async def _process_queue(self, domain: str, queue: asyncio.Queue[EmergencyEvent]) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                await self._process_event(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[EmergencyResponseSystem] process_queue error: {}", e)

    async def _process_event(self, event: EmergencyEvent) -> None:
        scored = self._classifier.classify(event)

        actions = await self._runbook.execute(scored)

        escalation_results = await self._escalation.escalate(scored, actions)

        entry = self._build_entry(event, scored, actions, escalation_results)
        self._log.append(entry)

    @staticmethod
    def _outcome(scored: ScoredEmergency, escalation_results) -> str:
        if scored.severity not in ("CRITICAL", "HIGH"):
            return "logged"
        if any(r.get("status") == "ok" and r.get("action") != "log_only" for r in escalation_results or []):
            return "escalated"
        return "escalation_failed"

    def _build_entry(self, event: EmergencyEvent, scored: ScoredEmergency, actions, escalation_results) -> EmergencyLogEntry:
        return EmergencyLogEntry(
            event_id=event.event_id,
            severity=scored.severity,
            domain=event.domain,
            signal_name=event.signal_name,
            detected_at=event.detected_at,
            classified_at=scored.classified_at,
            severity_score=scored.severity_score,
            actions_taken=[{"name": a.name, "success": a.success} for a in actions] if actions else [],
            escalation_path=[r.get("action", "") for r in escalation_results],
            acknowledged=False,
            resolved=False,
            duration_seconds=None,
            outcome=self._outcome(scored, escalation_results),
        )

    async def run(self, task: dict) -> dict:
        """Direct chat/API dispatch entry point (2026-07-30 audit fix).

        Before this, EmergencyResponseSystem had no run() override, so a
        governor.dispatch() call would silently hit AgentBase's no-op stub
        (returns status:"ok" without doing anything) -- worse than the prior
        "no_agents" failure because it LOOKED successful. This is deliberately
        separate from the signal-driven start()/emit_signal() path the
        background monitors use (health/security/system/network/disk/battery
        domains keep running continuously regardless); this method lets the
        owner directly report or query an emergency through chat."""
        self.last_active = datetime.datetime.utcnow().isoformat()
        task_type = task.get("type", "")
        params = task.get("params", {}) or {}
        query = params.get("query") or task.get("content") or ""

        if task_type in ("escalate_emergency", "classify_emergency"):
            event = EmergencyEvent(
                event_id=f"chat_{int(time.time() * 1000)}",
                domain=params.get("domain", "user_reported"),
                signal_name="chat_report",
                raw_message=query,
                detected_at=time.time(),
                source="chat",
            )
            scored = self._classifier.classify(event)
            result = {
                "status": "ok",
                "agent": self.name,
                "severity": scored.severity,
                "severity_score": scored.severity_score,
            }
            if task_type == "escalate_emergency" and scored.severity in ("CRITICAL", "HIGH"):
                actions = await self._runbook.execute(scored)
                escalation_results = await self._escalation.escalate(scored, actions)
                entry = self._build_entry(event, scored, actions, escalation_results)
                self._log.append(entry)
                result["actions_taken"] = [a.name for a in actions] if actions else []
                result["escalated"] = self._outcome(scored, escalation_results) == "escalated"
            else:
                result["note"] = (
                    "Classified only — severity below the escalation threshold "
                    "(or this was a status/classification check, not a request "
                    "to actually escalate)."
                )
            return result

        if task_type == "runbook":
            return {"status": "ok", "agent": self.name, "recent_log": self._log.summary(days=1)}

        if task_type == "detect_anomaly":
            return {
                "status": "ok",
                "agent": self.name,
                "note": "Anomaly detection runs continuously in the background "
                        "across health/security/system/network/disk/battery "
                        "domains — this is a status check, not an on-demand scan.",
                **self.get_state(),
            }

        # "emergency" / "emergency_alert" / anything else -> honest status report
        return {"status": "ok", "agent": self.name, **self.get_state()}

    def acknowledge(self, event_id: str) -> None:
        self._escalation.acknowledge(event_id)
        self._classifier.mark_acknowledged(event_id)

    def get_health(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "tasks_active": len(self._tasks),
            "detector_rules": len(self._detector.get_rules()),
        }

    def get_state(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "tasks": len(self._tasks),
            "escalation_paused": self._escalation._paused if hasattr(self._escalation, "_paused") else False,
            "log_summary": self._log.summary(days=1),
        }

    def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.name,
            "district": self.district,
            "hp": self.health_points,
            "status": self.get_status(),
            "running": self._running,
            "tasks_active": len(self._tasks),
            "channels_reachable": True,
        }

    def fallback_chain(self) -> list[str]:
        return ["local_rules", "emergency_contacts", "llm_triage"]
