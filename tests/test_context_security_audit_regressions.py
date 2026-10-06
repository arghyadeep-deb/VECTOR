"""Regression coverage for the context/security audit of 2026-10-07."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from vectorcode.src.context import references
from vectorcode.src.context import session_memory
from vectorcode.src.context.trajectory_compressor import validate
from vectorcode.src.vc_core.credentials import load_credentials, save_credential


def test_context_reference_cannot_read_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "outside.txt"
    secret.write_text("must-not-leak", encoding="utf-8")

    result = references.expand_context_references(
        f'@file:"{secret}"',
        cwd=workspace,
    )

    assert "must-not-leak" not in result.message
    assert any("outside the workspace" in warning for warning in result.warnings)


def test_context_reference_still_reads_file_inside_workspace(tmp_path: Path) -> None:
    source = tmp_path / "inside.txt"
    source.write_text("allowed-content", encoding="utf-8")

    result = references.expand_context_references('@file:"inside.txt"', cwd=tmp_path)

    assert "allowed-content" in result.message


def test_session_memory_replace_failure_preserves_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory_path = tmp_path / "memory.md"
    memory_path.write_text("original", encoding="utf-8")
    monkeypatch.setattr(session_memory, "VECTOR_DATA_DIR", tmp_path)
    monkeypatch.setattr(session_memory, "_MEMORY_PATH", memory_path)

    def fail_replace(_source: str, _target: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(session_memory.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        session_memory._write_memory({"Build Commands": ["pytest"]})

    assert memory_path.read_text(encoding="utf-8") == "original"
    assert not list(tmp_path.glob(".memory.md.*.tmp"))


def test_credential_save_is_atomic_and_toml_escapes_values(tmp_path: Path) -> None:
    credential_path = tmp_path / "credentials.toml"
    value = 'token "quoted" with\\slashes\nand newline'
    previous = os.environ.get("TAVILY_API_KEY")
    try:
        save_credential("web_search", "TAVILY_API_KEY", value, path=credential_path)
        assert load_credentials(credential_path)["web_search"]["TAVILY_API_KEY"] == value
        assert not list(tmp_path.glob(".credentials.toml.*.tmp"))
    finally:
        if previous is None:
            os.environ.pop("TAVILY_API_KEY", None)
        else:
            os.environ["TAVILY_API_KEY"] = previous


def test_trajectory_validation_drops_tool_result_without_preceding_call() -> None:
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "tool", "tool_call_id": "orphan", "content": "secret output"},
    ]

    assert validate(messages) == [messages[0]]


def test_trajectory_validation_accepts_openai_tool_call_pair() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "function": {"name": "read"}}],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "ok"},
    ]

    assert validate(messages) == messages
