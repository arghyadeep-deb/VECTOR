from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

from core.config import CONFIG
from .classifier import ScoredEmergency

_ESCALATION_TIERS = {
    "CRITICAL": [
        ("auto_runbook", 0),
        ("pushover_emergency", 30),
        ("escalate", 120),
    ],
    "HIGH": [
        ("auto_runbook", 0),
        ("pushover_high", 60),
    ],
    "MEDIUM": [
        ("pushover_normal", 0),
    ],
    "LOW": [
        ("log_only", 0),
    ],
}

_ACCELERATION_FACTOR = 0.5
_ACCELERATION_WINDOW = 3600
# Alert-storm guard: max real Telegram sends per rolling window.
_PUSH_MAX_PER_WINDOW = 20
_PUSH_WINDOW_SEC = 600.0

@dataclass
class EscalationState:
    tier_started_at: dict[str, float] = field(default_factory=dict)
    escalation_log: list[dict[str, Any]] = field(default_factory=list)

class EscalationManager:
    def __init__(self, test_mode: bool = False):
        self._acknowledged: set[str] = set()
        self._feedback_callbacks: list[callable] = []
        self._paused: bool = False
        self._state = EscalationState()
        self._last_domain_times: dict[str, float] = {}
        self._test_mode = test_mode
        self._push_times: deque[float] = deque()

    def pause(self) -> None:
        self._paused = True
        logger.info("[Escalation] paused")

    def resume(self) -> None:
        self._paused = False
        logger.info("[Escalation] resumed")

    async def escalate(self, emergency: ScoredEmergency, runbook_actions: list | None = None) -> list[dict[str, Any]]:
        if self._paused:
            return [{"action": "paused", "status": "skipped"}]

        if emergency.event.event_id in self._acknowledged:
            return [{"action": "already_acknowledged", "status": "skipped"}]

        tier_steps = _ESCALATION_TIERS.get(emergency.severity, [("log_only", 0)])
        results = []
        last_step_time = time.time()

        acceleration = self._should_accelerate(emergency.event.domain)
        factor = _ACCELERATION_FACTOR if acceleration else 1.0

        if acceleration:
            logger.info("[Escalation] accelerating {} (same-domain within 1h)", emergency.event.domain)

        for step_name, delay_sec in tier_steps:
            effective_delay = delay_sec * factor
            wait = effective_delay - (time.time() - last_step_time) if step_name != tier_steps[0][0] else 0
            if wait > 0 and not self._test_mode:
                await asyncio.sleep(wait)
            if emergency.event.event_id in self._acknowledged:
                results.append({"action": "acknowledged_during_escalation", "status": "stopped"})
                break
            result = await self._execute_step(step_name, emergency, runbook_actions)
            result["tier_delay_sec"] = delay_sec
            results.append(result)
            last_step_time = time.time()

        self._last_domain_times[emergency.event.domain] = time.time()
        self._state.escalation_log.append({
            "event_id": emergency.event.event_id,
            "severity": emergency.severity,
            "domain": emergency.event.domain,
            "timestamp": time.time(),
            "steps": len(results),
            "accelerated": acceleration,
        })

        logger.info("[Escalation] {} → {} steps executed (accelerated={})", emergency.event.signal_name, len(results), acceleration)
        return results

    def _should_accelerate(self, domain: str) -> bool:
        last = self._last_domain_times.get(domain)
        if last is None:
            return False
        return (time.time() - last) < _ACCELERATION_WINDOW

    async def _execute_step(self, step: str, emergency: ScoredEmergency, runbook_actions: list | None = None) -> dict:
        handlers = {
            "auto_runbook": self._step_runbook,
            "pushover_emergency": self._step_pushover,
            "pushover_high": self._step_pushover,
            "pushover_normal": self._step_pushover,
            "escalate": self._step_escalate,
            "log_only": self._step_log,
        }
        handler = handlers.get(step, self._step_log)
        return await handler(step, emergency, runbook_actions)

    async def _step_runbook(self, step: str, emergency: ScoredEmergency, runbook_actions: list | None = None) -> dict:
        if runbook_actions:
            failed = [a for a in runbook_actions if getattr(a, "success", True) is False]
            if failed:
                logger.warning("[VECTOR][escalation] runbook for {}: {}/{} actions failed", emergency.event.signal_name, len(failed), len(runbook_actions))
                return {"action": "runbook_executed", "steps": len(runbook_actions), "failed_steps": len(failed), "status": "failed"}
            return {"action": "runbook_executed", "steps": len(runbook_actions), "status": "ok"}
        return {"action": "runbook_executed", "status": "no_actions"}

    async def _step_pushover(self, step: str, emergency: ScoredEmergency, runbook_actions: list | None = None) -> dict:
        # Sends via Telegram now (2026-10-30, owner decision — Pushover is a
        # paid service). Step names/action-string format/config flag name
        # ("pushover_enabled") kept as-is — they're just identifiers, tests
        # and other code reference them literally, and renaming is pure
        # churn with no functional benefit.
        priority = 2 if "emergency" in step else 1 if "high" in step else 0
        if self._test_mode:
            # Never hit the live notification API during tests.
            return {"action": f"pushover_{step}", "status": "ok", "message": "test_mode: notification skipped"}
        if not CONFIG.get("emergency", {}).get("pushover_enabled", True):
            return {"action": f"pushover_{step}", "status": "skipped", "reason": "pushover disabled in config"}
        try:
            telegram_token = CONFIG.get("telegram_bot_token", "") or CONFIG.get("api_keys", {}).get("telegram_bot_token", "")
            telegram_chat_id = CONFIG.get("telegram_chat_id", "") or CONFIG.get("api_keys", {}).get("telegram_chat_id", "")
            if not telegram_token or not telegram_chat_id:
                # No credentials configured — don't POST to the live API (would hang/fail).
                return {"action": f"pushover_{step}", "status": "skipped", "reason": "no credentials"}
            now = time.monotonic()
            while self._push_times and now - self._push_times[0] > _PUSH_WINDOW_SEC:
                self._push_times.popleft()
            if len(self._push_times) >= _PUSH_MAX_PER_WINDOW:
                logger.warning("[VECTOR][escalation] telegram rate limit hit ({} per {}s) — suppressing {}", _PUSH_MAX_PER_WINDOW, _PUSH_WINDOW_SEC, emergency.event.signal_name)
                return {"action": f"pushover_{step}", "status": "rate_limited"}
            self._push_times.append(now)
            from core.notify import send_telegram
            title = f"[{emergency.severity}] {emergency.event.domain.upper()} Emergency"
            ok = await send_telegram(f"{title}\n{emergency.event.raw_message}", priority=priority)
            return {"action": f"pushover_{step}", "status": "ok" if ok else "failed"}
        except Exception as e:
            return {"action": f"pushover_{step}", "status": "error", "error": str(e)}

    async def _step_escalate(self, step: str, emergency: ScoredEmergency, runbook_actions: list | None = None) -> dict:
        logger.warning("[Escalation] ESCALATING {} — no auto-resolution possible", emergency.event.signal_name)
        if self._test_mode:
            return {"action": "escalate", "status": "ok", "message": "test_mode: audio alert skipped"}
        try:
            import winsound
            for _ in range(5):
                try:
                    winsound.Beep(1500, 500)
                    await asyncio.sleep(0.3)
                except Exception:
                    import subprocess
                    (await asyncio.to_thread(subprocess.run, ["powershell", "-c", "[console]::beep(1500,500)"], capture_output=True, timeout=3))
                    await asyncio.sleep(0.3)
            return {"action": "escalate", "status": "ok", "message": "User alerted via audio"}
        except Exception as e:
            return {"action": "escalate", "status": "error", "error": str(e)}

    async def _step_log(self, step: str, emergency: ScoredEmergency, runbook_actions: list | None = None) -> dict:
        logger.info("[Escalation] {} logged (severity={})", emergency.event.signal_name, emergency.severity)
        return {"action": "log_only", "status": "ok"}

    def acknowledge(self, event_id: str) -> None:
        self._acknowledged.add(event_id)
        logger.info("[Escalation] {} acknowledged by user", event_id)

    def get_state(self) -> EscalationState:
        return self._state
