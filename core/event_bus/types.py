from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class EventType(str, Enum):
    TASK_SCHEDULED = "task_scheduled"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    AGENT_STATE_CHANGED = "agent_state_changed"
    DECISION_MADE = "decision_made"
    MEMORY_STORED = "memory_stored"
    MEMORY_RETRIEVED = "memory_retrieved"
    VOICE_INPUT = "voice_input"
    VOICE_OUTPUT = "voice_output"
    HEALTH_ALERT = "health_alert"
    SYSTEM_ERROR = "system_error"
    CONFIG_CHANGED = "config_changed"
    USER_INTERACTION = "user_interaction"
    RESEARCH_COMPLETE = "research_complete"
    EMERGENCY_SIGNAL = "emergency_signal"
    SECURITY_ALERT = "security_alert"
    CONTENT_READY = "content_ready"
    CONTENT_REVIEWED = "content_reviewed"
    DESIGN_COMPLETE = "design_complete"
    MARKETING_PUBLISHED = "marketing_published"
    ANALYTICS_READY = "analytics_ready"
    CODING_COMPLETE = "coding_complete"
    UPLOAD_COMPLETE = "upload_complete"


@dataclass
class Event:
    event_type: EventType
    data: dict = field(default_factory=dict)
    source: str = ""
    correlation_id: str = field(default_factory=lambda: generate_correlation_id())
    timestamp: float = field(default_factory=time.time)


def generate_correlation_id() -> str:
    return uuid.uuid4().hex
