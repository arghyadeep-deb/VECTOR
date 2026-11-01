from __future__ import annotations

__all__ = [
    "AcpTodoState",
    "Todo",
    "TodoArgs",
]


from typing import cast

try:
    from acp.helpers import SessionUpdate
    from acp.schema import AgentPlanUpdate, PlanEntry, PlanEntryPriority, PlanEntryStatus
except (ImportError, AttributeError):
    pass  # acp protocol package not installed

from core.coding_assistant import VIBE_ROOT
from core.coding_assistant.acp.tools.base import AcpToolState, BaseAcpTool
from core.coding_assistant.core.tools.builtins.todo import (
    Todo as CoreTodoTool,
    TodoArgs,
    TodoPriority,
    TodoResult,
    TodoState,
    TodoStatus,
)
from core.coding_assistant.core.types import ToolCallEvent, ToolResultEvent

TodoArgs = TodoArgs


class AcpTodoState(TodoState, AcpToolState):
    pass


class Todo(CoreTodoTool, BaseAcpTool[AcpTodoState]):
    state: AcpTodoState
    prompt_path = VIBE_ROOT / "core" / "tools" / "builtins" / "prompts" / "todo.md"

    @classmethod
    def _get_tool_state_class(cls) -> type[AcpTodoState]:
        return AcpTodoState

    @classmethod
    def tool_call_session_update(cls, event: ToolCallEvent) -> SessionUpdate | None:
        return None

    @classmethod
    def tool_result_session_update(cls, event: ToolResultEvent) -> SessionUpdate | None:
        result = cast(TodoResult, event.result)
        todos = [todo for todo in result.todos if todo.status != TodoStatus.CANCELLED]
        matched_status: dict[TodoStatus, PlanEntryStatus] = {
            TodoStatus.PENDING: "pending",
            TodoStatus.IN_PROGRESS: "in_progress",
            TodoStatus.COMPLETED: "completed",
        }
        matched_priority: dict[TodoPriority, PlanEntryPriority] = {
            TodoPriority.LOW: "low",
            TodoPriority.MEDIUM: "medium",
            TodoPriority.HIGH: "high",
        }

        update = AgentPlanUpdate(
            session_update="plan",
            entries=[
                PlanEntry(
                    content=todo.content,
                    status=matched_status[todo.status],
                    priority=matched_priority[todo.priority],
                )
                for todo in todos
            ],
        )
        return update
