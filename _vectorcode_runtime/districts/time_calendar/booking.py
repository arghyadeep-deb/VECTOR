"""Small VECTOR-native booking and availability contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

__all__ = [
    "AvailabilityWindow",
    "BookingRequest",
    "BookingStatus",
    "CalendarEvent",
    "has_conflict",
    "requires_owner_approval",
]


class BookingStatus(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


@dataclass(frozen=True)
class AvailabilityWindow:
    start: datetime
    end: datetime
    timezone_name: str = "Asia/Calcutta"
    label: str = "available"

    def contains(self, start: datetime, end: datetime) -> bool:
        return self.start <= start and end <= self.end


@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    start: datetime
    end: datetime
    title: str
    source: str = "vector"


@dataclass(frozen=True)
class BookingRequest:
    request_id: str
    requester: str
    start: datetime
    end: datetime
    title: str
    status: BookingStatus = BookingStatus.REQUESTED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def has_conflict(request: BookingRequest, events: list[CalendarEvent]) -> bool:
    return any(request.start < event.end and request.end > event.start for event in events)


def requires_owner_approval(request: BookingRequest) -> bool:
    return request.status == BookingStatus.REQUESTED
