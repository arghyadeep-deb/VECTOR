"""Regression for vectorcode/src/agent/transports/codex_event_projector.py:

_deterministic_call_id()'s fallback path (used whenever a Codex app-server
item arrives with no `id`) used to hash only the fixed `item_type` string --
the same string always hashes to the same digest, so every same-type tool
call in a session produced an IDENTICAL tool_call_id. Since tool_call_id is
the only thing correlating an assistant's tool_calls entry with its
subsequent tool-role result message, two same-type calls without an id in
one turn (e.g. two shell commands) collided, breaking that correlation.

Fixed with a per-type monotonic counter on the (per-session) projector
instance: unique within the instance's lifetime, and still deterministic
across a replay of the same ordered notification stream.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from agent.transports.codex_event_projector import CodexEventProjector


def _command_item(command: str) -> dict:
    return {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "commandExecution",
                "id": "",  # app-server omitted the id
                "command": command,
                "cwd": "/tmp",
                "aggregatedOutput": "ok",
                "exitCode": 0,
            }
        },
    }


def test_fallback_ids_are_unique_across_same_type_calls_without_item_id():
    projector = CodexEventProjector()

    result1 = projector.project(_command_item("echo one"))
    result2 = projector.project(_command_item("echo two"))

    call_id_1 = result1.messages[0]["tool_calls"][0]["id"]
    call_id_2 = result2.messages[0]["tool_calls"][0]["id"]

    assert call_id_1 != call_id_2, (
        "two same-type tool calls without an item id must not collide on "
        "the same tool_call_id"
    )

    # Each assistant message's tool_calls[0].id must match its own
    # paired tool-result message's tool_call_id -- no cross-wiring.
    assert result1.messages[1]["tool_call_id"] == call_id_1
    assert result2.messages[1]["tool_call_id"] == call_id_2


def test_fallback_ids_are_deterministic_across_a_replayed_event_order():
    events = [_command_item("echo one"), _command_item("echo two")]

    projector_a = CodexEventProjector()
    ids_a = [
        projector_a.project(ev).messages[0]["tool_calls"][0]["id"] for ev in events
    ]

    projector_b = CodexEventProjector()
    ids_b = [
        projector_b.project(ev).messages[0]["tool_calls"][0]["id"] for ev in events
    ]

    assert ids_a == ids_b, "replaying the same ordered event stream must yield the same ids"


def test_real_item_id_is_still_used_directly():
    projector = CodexEventProjector()
    item = _command_item("echo one")
    item["params"]["item"]["id"] = "real-id-123"

    result = projector.project(item)
    call_id = result.messages[0]["tool_calls"][0]["id"]

    assert "real-id-123" in call_id


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
