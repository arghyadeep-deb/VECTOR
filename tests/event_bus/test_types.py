
import time
import pytest

from core.event_bus.types import EventType, Event, generate_correlation_id


class TestEventType:

    def test_enum_values(self):
        assert EventType.TASK_SCHEDULED.value == "task_scheduled"
        assert EventType.TASK_COMPLETED.value == "task_completed"
        assert EventType.TASK_FAILED.value == "task_failed"
        assert EventType.AGENT_STATE_CHANGED.value == "agent_state_changed"
        assert EventType.DECISION_MADE.value == "decision_made"
        assert EventType.MEMORY_STORED.value == "memory_stored"
        assert EventType.MEMORY_RETRIEVED.value == "memory_retrieved"
        assert EventType.VOICE_INPUT.value == "voice_input"
        assert EventType.VOICE_OUTPUT.value == "voice_output"
        assert EventType.HEALTH_ALERT.value == "health_alert"
        assert EventType.SYSTEM_ERROR.value == "system_error"
        assert EventType.CONFIG_CHANGED.value == "config_changed"
        assert EventType.USER_INTERACTION.value == "user_interaction"
        assert EventType.RESEARCH_COMPLETE.value == "research_complete"
        assert EventType.EMERGENCY_SIGNAL.value == "emergency_signal"

    def test_total_event_types(self):
        # 28 base types + 3 collections record events (RECORD_CREATED/UPDATED/DELETED)
        assert len(EventType) == 31


class TestEvent:

    def test_create_minimal(self):
        event = Event(event_type=EventType.HEALTH_ALERT)
        assert event.event_type == EventType.HEALTH_ALERT
        assert event.data == {}
        assert event.source == ""
        assert event.correlation_id is not None
        assert isinstance(event.timestamp, float)
        assert event.timestamp > 0

    def test_create_with_all_fields(self):
        now = time.time()
        corr_id = generate_correlation_id()
        event = Event(
            event_type=EventType.DECISION_MADE,
            data={"action": "test", "score": 0.9},
            source="test_service",
            correlation_id=corr_id,
            timestamp=now,
        )
        assert event.event_type == EventType.DECISION_MADE
        assert event.data == {"action": "test", "score": 0.9}
        assert event.source == "test_service"
        assert event.correlation_id == corr_id
        assert event.timestamp == now

    def test_default_correlation_id(self):
        event1 = Event(event_type=EventType.TASK_SCHEDULED)
        event2 = Event(event_type=EventType.TASK_SCHEDULED)
        assert event1.correlation_id != event2.correlation_id

    def test_default_timestamp_is_recent(self):
        before = time.time()
        event = Event(event_type=EventType.SYSTEM_ERROR)
        after = time.time()
        assert before <= event.timestamp <= after

    def test_event_repr(self):
        event = Event(event_type=EventType.USER_INTERACTION, data={"msg": "hello"})
        assert "USER_INTERACTION" in repr(event) or "Event" in repr(event)


class TestCorrelationId:

    def test_generate_correlation_id(self):
        cid = generate_correlation_id()
        assert isinstance(cid, str)
        assert len(cid) == 32

    def test_unique_ids(self):
        ids = {generate_correlation_id() for _ in range(100)}
        assert len(ids) == 100
