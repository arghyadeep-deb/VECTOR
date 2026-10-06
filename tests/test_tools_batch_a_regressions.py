"""Regression tests for the batch-A ``vectorcode.src.tools`` audit."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest


VECTORCODE_SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(VECTORCODE_SRC) not in sys.path:
    sys.path.insert(0, str(VECTORCODE_SRC))


def test_execute_code_keeps_explicitly_empty_tool_scope_empty() -> None:
    from tools.code_execution_tool import SANDBOX_ALLOWED_TOOLS, _resolve_sandbox_tools

    assert _resolve_sandbox_tools(None) == SANDBOX_ALLOWED_TOOLS
    assert _resolve_sandbox_tools([]) == frozenset()
    assert _resolve_sandbox_tools(["not-a-sandbox-tool"]) == frozenset()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
@pytest.mark.parametrize("implementation", ["checkpoint", "checkpoint_manager"])
def test_full_checkpoint_restore_removes_files_added_after_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    implementation: str,
) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    original = workdir / "original.txt"
    original.write_text("original", encoding="utf-8")

    if implementation == "checkpoint":
        from tools import checkpoint as module

        monkeypatch.setattr(module, "CHECKPOINT_BASE", tmp_path / "snapshots")
        manager = module.CheckpointManager(workdir)
        first = manager.create_checkpoint("initial")
        assert first["ok"] is True
        commit_hash = first["commit_hash"]

        (workdir / "added-later.txt").write_text("later", encoding="utf-8")
        assert manager.create_checkpoint("later")["ok"] is True
        restored = manager.restore_checkpoint(commit_hash, force=True)
        assert restored["ok"] is True
    else:
        from tools import checkpoint_manager as module

        monkeypatch.setattr(module, "CHECKPOINT_BASE", tmp_path / "snapshots")
        manager = module.CheckpointManager(enabled=True)
        assert manager.ensure_checkpoint(str(workdir), "initial") is True
        commit_hash = manager.list_checkpoints(str(workdir))[0]["hash"]

        (workdir / "added-later.txt").write_text("later", encoding="utf-8")
        manager.new_turn()
        assert manager.ensure_checkpoint(str(workdir), "later") is True
        restored = manager.restore(str(workdir), commit_hash)
        assert restored["success"] is True

    assert original.read_text(encoding="utf-8") == "original"
    assert not (workdir / "added-later.txt").exists()
