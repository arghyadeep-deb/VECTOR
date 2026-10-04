"""Regression coverage for trajectory diagnostics."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


AGENT_SRC = Path("vectorcode/src").resolve()
if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

from agent.trajectory import save_trajectory


def test_save_trajectory_renders_filename_in_loguru_message(tmp_path: Path) -> None:
    output = tmp_path / "trace.jsonl"
    messages: list[str] = []
    sink_id = logger.add(lambda record: messages.append(record), format="{message}")
    try:
        save_trajectory([], "model", True, str(output))
    finally:
        logger.remove(sink_id)

    assert output.exists()
    assert any(f"Trajectory saved to {output}" in message for message in messages)
    assert not any("%s" in message for message in messages)
