"""Core events shim — re-exports from vc_core.events."""
from vectorcode.src.vc_core.events import EventBus, Event, EventType, get_event_bus

# EventType enum members exposed as module-level aliases for backwards compat
AGENT_TICK_START          = EventType.AGENT_TICK_START
AGENT_TICK_END            = EventType.AGENT_TICK_END
AGENT_TICK_ERROR          = EventType.AGENT_TICK_ERROR
AGENT_TURN_START          = EventType.AGENT_TURN_START
AGENT_TURN_END            = EventType.AGENT_TURN_END
AGENT_MESSAGE_RECEIVED    = EventType.AGENT_MESSAGE_RECEIVED
AGENT_LEARNING_STARTED    = EventType.AGENT_LEARNING_STARTED
AGENT_LEARNING_COMPLETED  = EventType.AGENT_LEARNING_COMPLETED
AGENT_BUDGET_EXCEEDED     = EventType.AGENT_BUDGET_EXCEEDED
AGENT_STALL_DETECTED      = EventType.AGENT_STALL_DETECTED
AGENT_CHECKPOINT_SAVED    = EventType.AGENT_CHECKPOINT_SAVED
CHANNEL_MESSAGE_RECEIVED  = EventType.CHANNEL_MESSAGE_RECEIVED
CHANNEL_MESSAGE_SENT      = EventType.CHANNEL_MESSAGE_SENT
CAPABILITY_DENIED         = EventType.CAPABILITY_DENIED
BATCH_START               = EventType.BATCH_START
BATCH_END                 = EventType.BATCH_END
A2A_TASK_RECEIVED         = EventType.A2A_TASK_RECEIVED
A2A_TASK_COMPLETED        = EventType.A2A_TASK_COMPLETED
