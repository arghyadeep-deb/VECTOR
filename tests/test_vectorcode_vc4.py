import pytest
from unittest.mock import patch, MagicMock


# ─── Mode A: VectorREPL ───────────────────────────────────────────────────────

def test_repl_instantiates():
    from agents.coding.vectorcode.repl import VectorREPL
    repl = VectorREPL()
    assert repl.mode == "repl"
    assert hasattr(repl, "session")
    assert hasattr(repl, "gsd")

def test_repl_has_commands():
    from agents.coding.vectorcode.repl import VectorREPL
    repl = VectorREPL()
    assert hasattr(repl, "handle_command")
    commands = repl.COMMANDS
    assert "/help" in commands
    assert "/status" in commands
    assert "/mode" in commands
    assert "/quit" in commands

def test_repl_mode_switch():
    from agents.coding.vectorcode.repl import VectorREPL
    repl = VectorREPL()
    repl.handle_command("/mode auto")
    assert repl.session.mode == "auto"

def test_repl_status_returns_dict():
    from agents.coding.vectorcode.repl import VectorREPL
    repl = VectorREPL()
    status = repl.get_status()
    assert "mode" in status
    assert "model" in status
    assert "hp" in status

def test_repl_invalid_mode():
    from agents.coding.vectorcode.repl import VectorREPL
    repl = VectorREPL()
    result = repl.handle_command("/mode badmode")
    assert "Invalid" in result or "invalid" in result or "Must be" in result

def test_repl_quit_stops_running():
    from agents.coding.vectorcode.repl import VectorREPL
    repl = VectorREPL()
    repl._running = True
    repl.handle_command("/quit")
    assert repl._running is False


# ─── Mode B: VectorAutonomous ─────────────────────────────────────────────────

def test_autonomous_submit_returns_task_id():
    with patch("agents.coding.vectorcode.autonomous.TaskQueue") as MockTQ:
        mock_tq = MagicMock()
        mock_tq.get.return_value = mock_tq
        mock_tq.submit.return_value = "task-abc-123"
        MockTQ.get.return_value = mock_tq
        from agents.coding.vectorcode.autonomous import VectorAutonomous
        va = VectorAutonomous()
        task_id = va.submit("build a login endpoint")
        assert task_id == "task-abc-123"

def test_autonomous_uses_high_priority():
    with patch("agents.coding.vectorcode.autonomous.TaskQueue") as MockTQ:
        mock_tq = MagicMock()
        mock_tq.get.return_value = mock_tq
        mock_tq.submit.return_value = "x"
        MockTQ.get.return_value = mock_tq
        from agents.coding.vectorcode.autonomous import VectorAutonomous
        va = VectorAutonomous()
        va.submit("task")
        call_kwargs = mock_tq.submit.call_args[1]
        assert "priority" in call_kwargs

def test_autonomous_mode_is_valid():
    from agents.coding.vectorcode.autonomous import VectorAutonomous
    va = VectorAutonomous()
    assert va.session.mode in ("auto", "repl", "hybrid")


# ─── Mode C: VectorHybrid ─────────────────────────────────────────────────────

def test_hybrid_has_checkpoint_types():
    from agents.coding.vectorcode.hybrid import CheckpointGate
    assert hasattr(CheckpointGate, "PLAN_APPROVAL")
    assert hasattr(CheckpointGate, "RED_ACTION")
    assert hasattr(CheckpointGate, "DESTRUCTIVE_EDIT")

def test_hybrid_checkpoint_registration():
    from agents.coding.vectorcode.hybrid import VectorHybrid, CheckpointGate
    vh = VectorHybrid()
    assert hasattr(vh, "checkpoints")
    assert CheckpointGate.PLAN_APPROVAL in vh.checkpoints
    assert CheckpointGate.RED_ACTION in vh.checkpoints

def test_hybrid_needs_approval_for_red():
    from agents.coding.vectorcode.hybrid import VectorHybrid
    vh = VectorHybrid()
    assert vh.needs_approval("delete_files") is True
    assert vh.needs_approval("read_file") is False

def test_hybrid_needs_approval_for_plan():
    from agents.coding.vectorcode.hybrid import VectorHybrid
    vh = VectorHybrid()
    assert vh.needs_approval("plan_approval") is True

def test_hybrid_mode_label():
    from agents.coding.vectorcode.hybrid import VectorHybrid
    vh = VectorHybrid()
    assert vh.mode_label == "hybrid"
