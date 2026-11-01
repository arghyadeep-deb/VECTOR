from __future__ import annotations

import datetime
import asyncio
import time
from collections import defaultdict
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

from core.config import CONFIG
from districts.health.metrics_store import MetricsStore

class HealthEmergencyDetector:
    def __init__(self, store: MetricsStore | None = None) -> None:
        self._store = store or MetricsStore()
        self._integration: Any = None
        self._duration_tracker: dict[str, dict[str, Any]] = defaultdict(dict)
        self._try_integrate_emergency_detector()

    def _try_integrate_emergency_detector(self) -> None:
        try:
            from districts.emergency.detector import EmergencyDetector
            self._integration = EmergencyDetector()
            logger.info("[VECTOR][health_emergency] integrated with EmergencyDetector")
        except Exception as exc:
            logger.debug(f"[VECTOR][health_emergency] no EmergencyDetector integration: {exc}")

    def _run_or_schedule(self, coro: Any, label: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(coro)
            except Exception as exc:
                logger.warning(f"[VECTOR][health_emergency] {label} failed: {exc}")
            return

        try:
            loop.create_task(coro)
        except Exception as exc:
            logger.warning(f"[VECTOR][health_emergency] {label} schedule failed: {exc}")

    def _signal_external(self, metric: str, value: float) -> None:
        try:
            from districts.emergency.main import _emit
            self._run_or_schedule(
                _emit("health", metric, value, "health_emergency_detector"),
                "emergency emit",
            )
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)
        if self._integration is not None:
            try:
                self._run_or_schedule(
                    self._integration.process_signal("health", metric, value),
                    "detector signal",
                )
            except Exception as exc:
                logger.warning(f"[VECTOR][health_emergency] signal failed: {exc}")

    def _send_pushover(self, title: str, message: str) -> None:
        # Sends via Telegram now (2026-10-30, owner decision — Pushover is a
        # paid service). Method name/config flag ("pushover_enabled") kept
        # as-is — just identifiers, renaming is pure churn.
        if not CONFIG.get("health", {}).get("pushover_enabled", True):
            return
        try:
            from core.notify import send_telegram
            self._run_or_schedule(send_telegram(f"{title}\n{message}", priority=1), "telegram send")
        except Exception as exc:
            logger.warning(f"[VECTOR][health_emergency] telegram send failed: {exc}")

    def _check_duration(self, key: str, active: bool, sustain_minutes: int = 5) -> bool:
        now = time.time()
        if active:
            if key not in self._duration_tracker:
                self._duration_tracker[key] = {"start": now, "alerted": False}
                return False
            elapsed = now - self._duration_tracker[key]["start"]
            if elapsed >= sustain_minutes * 60 and not self._duration_tracker[key]["alerted"]:
                self._duration_tracker[key]["alerted"] = True
                return True
            return False
        else:
            self._duration_tracker.pop(key, None)
            return False

    def check(self, metrics: dict[str, Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        now_str = datetime.datetime.now().isoformat(timespec="seconds")

        hr = metrics.get("heart_rate")
        hrv_val = metrics.get("hrv")
        spo2 = metrics.get("spo2")
        stress = metrics.get("stress_level")
        steps = metrics.get("steps")
        resp_rate = metrics.get("respiratory_rate")
        movement = metrics.get("movement_detected")

        events.extend(self._rule_sustained_high_hr(hr, now_str))
        events.extend(self._rule_sustained_low_hr(hr, now_str))
        events.extend(self._rule_high_stress_sustained(stress, now_str))
        events.extend(self._rule_low_spo2(spo2, now_str))
        events.extend(self._rule_no_movement_long(movement, now_str))
        events.extend(self._rule_sleep_apnea_pattern(resp_rate, now_str))
        events.extend(self._rule_hrv_crash(hrv_val, now_str))

        for ev in events:
            self._signal_external(ev["event_type"], ev.get("value", 0.0))
            self._store.store_emergency_event(ev)
            if ev.get("severity", 5) >= 7:
                self._send_pushover(f"Health Alert: {ev['event_type']}", ev.get("message", ""))

        return events

    def _rule_sustained_high_hr(self, hr: float | None, now: str) -> list[dict[str, Any]]:
        if hr is None:
            return []
        sustained = self._check_duration("high_hr", hr > 120, sustain_minutes=5)
        if sustained:
            return [{
                "event_type": "sustained_high_hr", "value": hr, "threshold": ">120 bpm for 5min",
                "severity": 7, "message": f"Sustained high heart rate: {hr} bpm for >5min",
                "detected_at": now, "id": None,
            }]
        if hr > 140:
            return [{
                "event_type": "sustained_high_hr", "value": hr, "threshold": ">140 bpm",
                "severity": 8, "message": f"Critically high heart rate: {hr} bpm",
                "detected_at": now, "id": None,
            }]
        return []

    def _rule_sustained_low_hr(self, hr: float | None, now: str) -> list[dict[str, Any]]:
        if hr is None:
            return []
        sustained = self._check_duration("low_hr", hr < 45, sustain_minutes=3)
        if sustained:
            return [{
                "event_type": "sustained_low_hr", "value": hr, "threshold": "<45 bpm for 3min",
                "severity": 9, "message": f"Sustained low heart rate: {hr} bpm for >3min",
                "detected_at": now, "id": None,
            }]
        if hr < 40:
            return [{
                "event_type": "sustained_low_hr", "value": hr, "threshold": "<40 bpm",
                "severity": 10, "message": f"Critically low heart rate: {hr} bpm",
                "detected_at": now, "id": None,
            }]
        return []

    def _rule_high_stress_sustained(self, stress: float | None, now: str) -> list[dict[str, Any]]:
        if stress is None:
            return []
        sustained = self._check_duration("high_stress", stress > 0.7, sustain_minutes=30)
        if sustained:
            return [{
                "event_type": "high_stress_sustained", "value": stress, "threshold": ">0.7 for 30min",
                "severity": 6, "message": f"Sustained high stress: {stress:.2f} for >30min",
                "detected_at": now, "id": None,
            }]
        return []

    def _rule_low_spo2(self, spo2: float | None, now: str) -> list[dict[str, Any]]:
        if spo2 is None:
            return []
        sustained = self._check_duration("low_spo2", spo2 < 92, sustain_minutes=2)
        if sustained:
            return [{
                "event_type": "low_spo2", "value": spo2, "threshold": "<92% for 2min",
                "severity": 9, "message": f"Low blood oxygen: {spo2}% SpO2 for >2min",
                "detected_at": now, "id": None,
            }]
        if spo2 < 88:
            return [{
                "event_type": "low_spo2", "value": spo2, "threshold": "<88%",
                "severity": 10, "message": f"Critical blood oxygen: {spo2}% SpO2",
                "detected_at": now, "id": None,
            }]
        return []

    def _rule_no_movement_long(self, movement: bool | float | None, now: str) -> list[dict[str, Any]]:
        if movement is None:
            return []
        no_movement = movement is False or (isinstance(movement, (int, float)) and movement == 0)
        sustained = self._check_duration("no_movement", no_movement, sustain_minutes=120)
        if sustained:
            return [{
                "event_type": "no_movement_long", "value": 0.0, "threshold": "no movement >2h",
                "severity": 5, "message": "No movement detected for over 2 hours",
                "detected_at": now, "id": None,
            }]
        return []

    def _rule_sleep_apnea_pattern(self, resp_rate: float | None, now: str) -> list[dict[str, Any]]:
        if resp_rate is None:
            return []
        sustained = self._check_duration("sleep_apnea", resp_rate < 8, sustain_minutes=10)
        if sustained:
            return [{
                "event_type": "sleep_apnea_pattern", "value": resp_rate, "threshold": "<8 breaths/min for 10min",
                "severity": 8, "message": f"Respiratory rate critically low: {resp_rate}/min — possible apnea pattern",
                "detected_at": now, "id": None,
            }]
        return []

    def _rule_hrv_crash(self, hrv: float | None, now: str) -> list[dict[str, Any]]:
        if hrv is None:
            return []
        sustained = self._check_duration("hrv_crash", hrv < 15, sustain_minutes=10)
        if sustained:
            return [{
                "event_type": "hrv_crash", "value": hrv, "threshold": "<15ms for 10min",
                "severity": 7, "message": f"HRV critically low: {hrv}ms — possible overtraining or illness",
                "detected_at": now, "id": None,
            }]
        return []

    def check_heart_rate_only(self, hr: float) -> list[dict[str, Any]]:
        return self._rule_sustained_high_hr(hr, datetime.datetime.now().isoformat(timespec="seconds")) + self._rule_sustained_low_hr(hr, datetime.datetime.now().isoformat(timespec="seconds"))

    def check_oxygen_only(self, spo2: float) -> list[dict[str, Any]]:
        return self._rule_low_spo2(spo2, datetime.datetime.now().isoformat(timespec="seconds"))
