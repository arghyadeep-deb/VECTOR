from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from .detector import EmergencyEvent


@dataclass
class ScoredEmergency:
    event: EmergencyEvent
    severity: str = "LOW"
    severity_score: float = 0.0
    context_modifiers: list[str] = field(default_factory=list)
    recommendation: str = "monitor"
    classified_at: float = 0.0
    confidence: float = 1.0
    escalation_path: str = "auto"


_SEVERITY_BANDS = [
    ("CRITICAL", 0.90),
    ("HIGH", 0.70),
    ("MEDIUM", 0.45),
    ("LOW", 0.0),
]

_DOMAIN_BASE_SCORES = {
    "health": 0.60,
    "security": 0.75,
    "system": 0.40,
    "network": 0.30,
    "disk": 0.35,
    "battery": 0.25,
}

_SEVERITY_MODIFIERS = {
    "night_risk": 1.3,
    "work_hours": 0.8,
    "acknowledged_recently": 0.5,
    "asleep": 1.5,
}

_ESCALATION_PATHS = {
    ("CRITICAL", "health"): "auto",
    ("CRITICAL", "security"): "pushover",
    ("CRITICAL", "system"): "auto",
    ("HIGH", "system"): "auto",
    ("HIGH", "health"): "pushover",
    ("HIGH", "security"): "pushover",
}


class SeverityClassifier:
    def __init__(self):
        self._event_history: list[ScoredEmergency] = []
        self._compound_window = 60.0
        self._acknowledged_ids: set[str] = set()

    def classify(self, event: EmergencyEvent) -> ScoredEmergency:
        base = _DOMAIN_BASE_SCORES.get(event.domain, 0.3)

        compound_override = self._check_compound(event)
        if compound_override is not None:
            scored = ScoredEmergency(
                event=event,
                severity="CRITICAL",
                severity_score=1.0,
                context_modifiers=[f"compound: {compound_override}"],
                recommendation=self._get_recommendation("CRITICAL", event.domain),
                classified_at=time.time(),
                confidence=0.95,
                escalation_path="auto",
            )
            self._event_history.append(scored)
            if len(self._event_history) > 100:
                self._event_history.pop(0)
            logger.info("[Classifier] {} compound override → CRITICAL (score=1.00)", event.signal_name)
            return scored

        modifiers = self._get_modifiers(event)
        adjusted = base
        for val, _ in modifiers:
            if val >= 1.0:
                adjusted *= val
            else:
                adjusted += val
        if not modifiers:
            adjusted = base

        recurrence = self._get_recurrence(event)
        adjusted *= recurrence

        final_score = min(1.0, max(0.0, adjusted))
        # A rule that explicitly declares a severity must not be dampened below it
        # (e.g. heart_rate_stopped during work hours scored LOW -> log only).
        final_score = max(final_score, min(1.0, getattr(event, "severity_floor", 0.0) or 0.0))

        confidence = min(1.0, 0.5 + final_score * 0.5)

        severity = "LOW"
        for name, threshold in _SEVERITY_BANDS:
            if final_score >= threshold:
                severity = name
                break

        escalation_path = _ESCALATION_PATHS.get((severity, event.domain), "manual")

        scored = ScoredEmergency(
            event=event,
            severity=severity,
            severity_score=final_score,
            context_modifiers=[desc for _, desc in modifiers],
            recommendation=self._get_recommendation(severity, event.domain),
            classified_at=time.time(),
            confidence=confidence,
            escalation_path=escalation_path,
        )

        self._event_history.append(scored)
        if len(self._event_history) > 100:
            self._event_history.pop(0)

        logger.info("[Classifier] {} → {} (score={:.2f}, conf={:.2f})", event.signal_name, severity, final_score, confidence)
        return scored

    def _check_compound(self, event: EmergencyEvent) -> str | None:
        now = time.time()
        if event.signal_name == "disk_full":
            for prev in self._event_history:
                if now - prev.event.detected_at < self._compound_window:
                    if prev.event.signal_name == "high_ram":
                        return "disk_full + high_ram"
        if event.signal_name == "high_ram":
            for prev in self._event_history:
                if now - prev.event.detected_at < self._compound_window:
                    if prev.event.signal_name == "disk_full":
                        return "high_ram + disk_full"
        if event.signal_name == "gpu_temp_high":
            for prev in self._event_history:
                if now - prev.event.detected_at < self._compound_window:
                    if prev.event.signal_name == "high_cpu":
                        return "gpu_overheat + high_cpu"
        return None

    def _get_modifiers(self, event: EmergencyEvent) -> list[tuple[float, str]]:
        modifiers: list[tuple[float, str]] = []
        now = time.time()

        for prev in self._event_history:
            if now - prev.event.detected_at < self._compound_window:
                if prev.event.domain == event.domain:
                    if prev.severity in ("CRITICAL", "HIGH"):
                        modifiers.append((0.15, f"compound: recent {prev.event.signal_name}"))

        hour = time.localtime().tm_hour
        if hour < 6 or hour >= 23:
            modifiers.append((_SEVERITY_MODIFIERS["night_risk"] - 1.0, "time_of_day: late night"))
        elif 9 <= hour <= 17:
            modifiers.append((_SEVERITY_MODIFIERS["work_hours"] - 1.0, "time_of_day: work hours"))

        if event.event_id in self._acknowledged_ids:
            modifiers.append((_SEVERITY_MODIFIERS["acknowledged_recently"] - 1.0, "acknowledged_recently"))

        return modifiers

    def _get_recurrence(self, event: EmergencyEvent) -> float:
        now = time.time()
        hour_ago = now - 3600
        count = sum(
            1 for s in self._event_history
            if s.event.domain == event.domain and s.event.detected_at >= hour_ago
        )
        if count >= 5:
            return 1.5
        if count >= 3:
            return 1.2
        if count >= 1:
            return 1.0
        return 1.0

    def mark_acknowledged(self, event_id: str) -> None:
        self._acknowledged_ids.add(event_id)

    @staticmethod
    def _get_recommendation(severity: str, domain: str) -> str:
        recs = {
            ("CRITICAL", "health"): "immediate_escalation",
            ("CRITICAL", "security"): "containment_and_escalation",
            ("CRITICAL", "system"): "automated_recovery",
            ("HIGH", "health"): "user_notification",
            ("HIGH", "security"): "user_alert",
            ("HIGH", "system"): "automated_fix",
        }
        return recs.get((severity, domain), "monitor")
