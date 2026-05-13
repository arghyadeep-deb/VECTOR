# Ported from GitHub/NousResearch_hermes-agent/repo/tools/todo_tool.py
"""Structured TODO list management."""
import json
import threading
from typing import Any, List, Optional

from .registry import registry

_todos: List[dict] = []
_todos_lock = threading.Lock()
_next_id = 1


def todo_add(task: str, priority: str = "medium", context: Any = None) -> str:
    global _next_id
    with _todos_lock:
        item = {"id": _next_id, "task": task, "priority": priority, "done": False}
        _todos.append(item)
        _next_id += 1
    return json.dumps({"success": True, "id": item["id"], "task": task})


def todo_list_all(context: Any = None) -> str:
    with _todos_lock:
        return json.dumps({"todos": list(_todos)})


def todo_complete(id: int, context: Any = None) -> str:
    with _todos_lock:
        for item in _todos:
            if item["id"] == id:
                item["done"] = True
                return json.dumps({"success": True, "id": id})
    return json.dumps({"error": f"TODO #{id} not found"})


def todo_remove(id: int, context: Any = None) -> str:
    with _todos_lock:
        for i, item in enumerate(_todos):
            if item["id"] == id:
                _todos.pop(i)
                return json.dumps({"success": True, "id": id})
    return json.dumps({"error": f"TODO #{id} not found"})


registry.register(
    name="todo_add",
    handler=todo_add,
    schema={
        "description": "Add a task to the TODO list.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["task"],
        },
    },
    toolset="coding", risk_level="safe", emoji="📝",
)

registry.register(
    name="todo_list",
    handler=todo_list_all,
    schema={
        "description": "List all TODO items.",
        "parameters": {"type": "object", "properties": {}},
    },
    toolset="coding", risk_level="safe", emoji="📋",
)

registry.register(
    name="todo_complete",
    handler=todo_complete,
    schema={
        "description": "Mark a TODO item as complete.",
        "parameters": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
    toolset="coding", risk_level="safe", emoji="✅",
)
