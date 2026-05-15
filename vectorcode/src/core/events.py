"""Core events shim — re-exports from vc_core.events."""
from vectorcode.src.vc_core.events import (
    EventBus, Event, EventType,
    AGENT_TICK_START, AGENT_TICK_END, AGENT_TICK_ERROR,
    AGENT_TURN_START, AGENT_TURN_END,
    AGENT_MESSAGE_RECEIVED, AGENT_LEARNING_STARTED, AGENT_LEARNING_COMPLETED,
    AGENT_BUDGET_EXCEEDED, AGENT_STALL_DETECTED, AGENT_CHECKPOINT_SAVED,
    CHANNEL_MESSAGE_RECEIVED, CHANNEL_MESSAGE_SENT,
    CAPABILITY_DENIED, BATCH_START, BATCH_END,
    A2A_TASK_RECEIVED, A2A_TASK_COMPLETED,
)

def get_event_bus():
    from vectorcode.src.vc_core.events import EventBus
    return EventBus()
