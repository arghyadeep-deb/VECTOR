from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger


@dataclass
class EmergencyEvent:
    event_id: str = ""
    domain: str = ""
    signal_name: str = ""
    raw_value: Any = None
    raw_message: str = ""
    detected_at: float = 0.0
    source: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    # Explicit per-rule severity floor (0.0 = rule did not declare one). Lets a
    # rule such as heart_rate_stopped (1.0) keep its severity regardless of the
    # classifier's time-of-day dampening.
    severity_floor: float = 0.0


class EmergencyDetector:
    def __init__(self):
        self._rules: list[dict[str, Any]] = []
        self._debounce: dict[str, float] = {}
        self._dedup_windows: dict[str, float] = {}
        self._handlers: list[Callable[[EmergencyEvent], None]] = []
        self._queues: dict[str, asyncio.Queue[EmergencyEvent]] = {}
        self._batch_window = 10.0
        self._event_buffer: list[EmergencyEvent] = []
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        self.add_rule("health", "heart_rate_stopped", lambda v: v == 0, "Heart rate stopped", severity_score=1.0, dedup_window=120.0)
        self.add_rule("health", "heart_rate_critical", lambda v: v is not None and v < 40, "Heart rate critically low", dedup_window=60.0)
        self.add_rule("health", "heart_rate_high", lambda v: v is not None and v > 140, "Heart rate abnormally high", dedup_window=60.0)
        self.add_rule("health", "no_movement", lambda v: v is not None and v > 300, "No movement detected for 5+ minutes", dedup_window=300.0)

        self.add_rule("security", "intrusion_detected", lambda v: v is True, "Intrusion alert from security guard", dedup_window=300.0)
        self.add_rule("security", "suspicious_process", lambda v: v, "Suspicious process detected", dedup_window=120.0)

        self.add_rule("system", "high_cpu", lambda v: v is not None and v > 90, "CPU usage above 90%", dedup_window=30.0)
        self.add_rule("system", "high_ram", lambda v: v is not None and v > 90, "RAM usage above 90%", dedup_window=30.0)
        self.add_rule("system", "disk_full", lambda v: v is not None and v > 95, "Disk usage above 95%", dedup_window=60.0)
        self.add_rule("system", "gpu_temp_high", lambda v: v is not None and v > 85, "GPU temperature above 85C", dedup_window=60.0)
        self.add_rule("system", "process_crash", lambda v: v, "Critical process crashed", dedup_window=30.0)
        self.add_rule("system", "oom_detected", lambda v: v, "Out of memory event detected", dedup_window=30.0)

        self.add_rule("network", "internet_down", lambda v: v is True, "Internet connection lost", dedup_window=60.0)
        self.add_rule("network", "vpn_dropped", lambda v: v is True, "VPN connection dropped", dedup_window=60.0)
        self.add_rule("network", "phone_disconnected", lambda v: v is True, "Phone node disconnected", dedup_window=120.0)

        self.add_rule("disk", "disk_critical", lambda v: v is not None and v > 95, "Disk usage critical", dedup_window=60.0)
        self.add_rule("disk", "disk_warning", lambda v: v is not None and v > 85, "Disk usage warning", dedup_window=120.0)

        self.add_rule("battery", "battery_critical", lambda v: v is not None and v < 10, "Battery level critical", dedup_window=60.0)
        self.add_rule("battery", "battery_low", lambda v: v is not None and v < 20, "Battery level low", dedup_window=120.0)

    def add_rule(self, domain: str, signal_name: str, check_fn: Callable, message: str, severity_score: float | None = None, dedup_window: float = 60.0) -> None:
        self._rules.append({
            "domain": domain,
            "signal_name": signal_name,
            "check": check_fn,
            "message": message,
            "severity_score": 0.7 if severity_score is None else severity_score,
            "severity_explicit": severity_score is not None,
            "dedup_window": dedup_window,
        })
        self._dedup_windows[signal_name] = dedup_window

    def on_event(self, handler: Callable[[EmergencyEvent], None]) -> None:
        self._handlers.append(handler)

    def subscribe_signal(self, domain: str) -> asyncio.Queue[EmergencyEvent]:
        if domain not in self._queues:
            self._queues[domain] = asyncio.Queue()
        return self._queues[domain]

    async def process_signal(self, domain: str, signal_name: str, value: Any, source: str = "emergency_detector", context: dict[str, Any] | None = None) -> EmergencyEvent | None:
        now = time.time()
        dedup_key = f"{domain}:{signal_name}:{source}"

        window = self._dedup_windows.get(signal_name, 60.0)
        if dedup_key in self._debounce:
            if now - self._debounce[dedup_key] < window:
                return None

        for rule in self._rules:
            if rule["domain"] == domain and rule["signal_name"] == signal_name:
                try:
                    triggered = rule["check"](value)
                    if triggered:
                        self._debounce[dedup_key] = now
                        event = EmergencyEvent(
                            event_id=str(uuid.uuid4())[:8],
                            domain=domain,
                            signal_name=signal_name,
                            raw_value=value,
                            raw_message=rule["message"],
                            detected_at=now,
                            source=source,
                            context=context or {},
                            severity_floor=rule["severity_score"] if rule.get("severity_explicit") else 0.0,
                        )

                        self._event_buffer.append(event)
                        self._flush_buffer()

                        for handler in self._handlers:
                            try:
                                handler(event)
                            except Exception as e:
                                logger.error("[EmergencyDetector] handler error: {}", e)

                        queue = self._queues.get(domain)
                        if queue is not None:
                            await queue.put(event)

                        logger.warning("[EmergencyDetector] {}: {} (value={}, source={})", domain, rule["message"], value, source)
                        return event
                except Exception as e:
                    logger.warning("[EmergencyDetector] rule check failed for {}:{} (value={!r}): {}", domain, signal_name, value, e)
        return None

    def _flush_buffer(self) -> None:
        now = time.time()
        cutoff = now - self._batch_window
        self._event_buffer = [e for e in self._event_buffer if e.detected_at >= cutoff]

    def get_rules(self) -> list[dict[str, Any]]:
        return list(self._rules)

    def process_heart_rate(self, bpm: int | None) -> EmergencyEvent | None:
        import asyncio
        if bpm == 0:
            return asyncio.run(self.process_signal("health", "heart_rate_stopped", bpm))
        if bpm is not None and bpm < 40:
            return asyncio.run(self.process_signal("health", "heart_rate_critical", bpm))
        if bpm is not None and bpm > 140:
            return asyncio.run(self.process_signal("health", "heart_rate_high", bpm))
        return None

    def process_system_metrics(self, cpu: float | None, ram: float | None, disk: float | None, gpu_temp: float | None) -> list[EmergencyEvent]:
        events = []
        for signal, val in [("high_cpu", cpu), ("high_ram", ram), ("disk_full", disk), ("gpu_temp_high", gpu_temp)]:
            if val is not None:
                import asyncio
                ev = asyncio.run(self.process_signal("system", signal, val))
                if ev:
                    events.append(ev)
        return events
