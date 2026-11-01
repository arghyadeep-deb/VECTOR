from __future__ import annotations

__all__ = [
    "HealthAnomaly",
    "HealthRecommendation",
    "MetricTrend",
    "WearableMetrics",
]


from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WearableMetrics(BaseModel):
    heart_rate: float | None = None
    hrv: float | None = None
    resting_heart_rate: float | None = None
    sleep_hours: float | None = None
    sleep_quality: str | None = None
    sleep_stages: dict | None = None
    steps: int | None = None
    active_calories: float | None = None
    exercise_minutes: float | None = None
    spo2: float | None = None
    stress_level: float | None = None
    skin_temperature: float | None = None
    respiratory_rate: float | None = None
    timestamp: datetime | None = None

    class Config:
        extra = "allow"


class MetricTrend(BaseModel):
    metric_name: str
    direction: str = "stable"
    change_pct: float = 0.0
    avg: float = 0.0
    min: float = 0.0
    max: float = 0.0
    std_dev: float = 0.0
    baseline_7d_mean: float = 0.0
    baseline_7d_std: float = 0.0
    baseline_30d_mean: float = 0.0
    baseline_30d_std: float = 0.0
    delta_7d_pct: float = 0.0
    delta_30d_pct: float = 0.0
    stability: str = "stable"


class HealthAnomaly(BaseModel):
    metric_name: str
    expected: float = 0.0
    actual: float = 0.0
    deviation: float = 0.0
    severity: int = Field(default=5, ge=1, le=10)
    detected_at: str = ""
    trend_direction: str = "stable"
    probable_causes: list[str] = Field(default_factory=list)


class HealthRecommendation(BaseModel):
    type: str = "general"
    title: str = ""
    description: str = ""
    priority: int = Field(default=3, ge=1, le=5)
    metric_source: str = ""
    actionable: bool = True
