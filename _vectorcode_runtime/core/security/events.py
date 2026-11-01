
__all__ = [
    "Alert",
    "Incident",
    "LogEvent",
    "SecurityEvent",
]


import datetime
from typing import Any
from pydantic import BaseModel, Field


class SecurityEvent(BaseModel):
    event_type: str
    source: str
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    target: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    severity: float = 0.0
    correlation_id: str | None = None


class LogEvent(BaseModel):
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    service: str
    correlation_id: str | None = None
    level: str = "INFO"
    message: str
    module: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class Alert(BaseModel):
    id: str
    rule_name: str
    severity: int
    target: str = ""
    message: str
    status: str = "NEW"
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    resolved_at: datetime.datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class Incident(BaseModel):
    id: str
    playbook_name: str
    triggered_by: str
    steps: list[dict] = Field(default_factory=list)
    status: str = "PENDING"
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    resolved_at: datetime.datetime | None = None
