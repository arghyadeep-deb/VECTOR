from __future__ import annotations

import asyncio
import time
from typing import Any

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
    return None


class EmergencyResponseSystem(AgentBase):
    def __init__(self, test_mode: bool = False):
        super().__init__(
            agent_id=f"emergency_response_{int(time.time())}",
            name="emergency_response",
            district="emergency",
        )
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
            outcome="escalated" if scored.severity in ("CRITICAL", "HIGH") else "logged",
        )

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
