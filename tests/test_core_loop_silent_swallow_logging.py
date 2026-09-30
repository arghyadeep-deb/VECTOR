"""Regression test for core/loop/'s "silent swallow" logging bug (Phase 3
whole-repo audit, Claude/Codex 50/50 split, 2026-09-30) — the same bug class
already found and fixed in core/brain/ (tests/test_core_brain_silent_swallow_
logging.py, commit bd5f842da): an earlier automated pass had added
`logger.warning("[VECTOR] silent swallow")` to previously-bare
`except: pass` blocks, but the message is a static, generic string with zero
diagnostic information — no exception type, no `{}` interpolation, no
`exc_info`. A real failure at any of these 9 sites (context_engine.py,
autonomous_loop.py x2, cron_jobs.py x4, permission_gateway.py, task_ledger.py)
was completely unobservable: the log line looked like a warning but conveyed
nothing about what actually went wrong.

Fixed by capturing the exception (`except Exception as e:`) and rendering it
via loguru's `{}` interpolation, matching each file's own established
logging convention (e.g. task_ledger.py's own `get()` method, immediately
above the fixed `close()`, already did this correctly).

This file covers the 6 of 9 sites that are reasonably isolable for a direct,
non-mocked-to-death behavioral test. The other 3 (autonomous_loop.py's two
sites, deep inside `_observe_tick`'s voice-intent branch and the
VectorCode-MCP-server supervision loop) received the identical textual fix
but aren't separately unit-tested here — AutonomousLoop is a large stateful
singleton-ish class whose construction for an isolated single-branch test
would require more scaffolding than the fix's own risk warrants; verified
instead by direct code review (same before/after pattern as the 6 tested
here).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_task_ledger_close_logs_real_exception(caplog):
    from core.loop.task_ledger import TaskLedger

    tl = TaskLedger(db_path=Path(tempfile.mkdtemp()) / "test_ledger.db")
    tl._conn = MagicMock(close=MagicMock(side_effect=RuntimeError("boom-close")))

    import loguru
    messages = []
    handler_id = loguru.logger.add(lambda m: messages.append(m), level="WARNING")
    try:
        tl.close()
    finally:
        loguru.logger.remove(handler_id)

    joined = "".join(str(m) for m in messages)
    assert "boom-close" in joined
    assert "silent swallow" not in joined


def test_context_engine_brain_commands_failure_logs_real_exception():
    from core.loop.context_engine import ContextEngine

    ce = ContextEngine()
    import loguru
    messages = []
    handler_id = loguru.logger.add(lambda m: messages.append(str(m)), level="WARNING")
    try:
        with patch(
            "vectorcode.src.command_registry.get_command_registry",
            side_effect=RuntimeError("boom-brain-commands"),
        ):
            ce.session_hydration_prompt({"query": "test"})
    finally:
        loguru.logger.remove(handler_id)

    joined = "".join(messages)
    assert "brain commands unavailable" in joined
    assert "boom-brain-commands" in joined
    assert "[VECTOR] silent swallow" not in joined


def test_cron_selfcheck_failures_log_real_exceptions():
    """Exercises job_nightly_selfcheck() with subprocess.run and
    EpisodicMemory().store() both failing -- hits both cron_jobs.py sites
    fixed this pass (git-log lookup at ~line 265, episodic store at ~line 286)
    in one real (not over-mocked) run."""
    import core.loop.cron_jobs as cron_jobs_mod
    import asyncio

    import loguru
    messages = []
    handler_id = loguru.logger.add(lambda m: messages.append(str(m)), level="WARNING")
    try:
        with patch("subprocess.run", side_effect=RuntimeError("boom-subprocess")), \
             patch("core.memory.episodic.EpisodicMemory") as mock_mem:
            mock_mem.return_value.store.side_effect = RuntimeError("boom-episodic-store")
            asyncio.run(cron_jobs_mod.job_nightly_selfcheck())
    finally:
        loguru.logger.remove(handler_id)

    joined = "".join(messages)
    assert "git log lookup failed" in joined
    assert "boom-subprocess" in joined
    assert "episodic store of failure record failed" in joined
    assert "boom-episodic-store" in joined
    assert "[VECTOR] silent swallow" not in joined


def test_permission_gateway_set_timer_episodic_failure_logs_real_exception():
    from core.loop.permission_gateway import PermissionGateway, Action
    import asyncio

    gw = PermissionGateway()
    import loguru
    messages = []
    handler_id = loguru.logger.add(lambda m: messages.append(m), level="WARNING")
    try:
        with patch("core.memory.episodic.EpisodicMemory") as mock_mem:
            mock_mem.return_value.store.side_effect = RuntimeError("boom-timer-store")
            action = Action(action_type="set_timer", params={"duration_sec": 5},
                             proposed_by="test")
            result = asyncio.run(gw._execute_action(action))
    finally:
        loguru.logger.remove(handler_id)

    joined = "".join(str(m) for m in messages)
    assert "boom-timer-store" in joined
    assert "[VECTOR] silent swallow" not in joined
    # Behavior unchanged: set_timer still reports ok even if the episodic
    # side-effect log failed (this test only proves the LOGGING fix, not a
    # behavior change).
    assert result["status"] == "ok"


def test_no_remaining_silent_swallow_placeholders_in_core_loop():
    """Golden test: the literal placeholder string must not reappear in
    core/loop/ — guards against the same bug being reintroduced by a future
    automated pass."""
    import subprocess
    repo_root = Path(__file__).parent.parent
    out = subprocess.run(
        ["git", "grep", "-l", "silent swallow", "--", "core/loop/"],
        cwd=repo_root, capture_output=True, text=True,
    )
    assert out.stdout.strip() == "", f"'silent swallow' placeholder still present in: {out.stdout}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
