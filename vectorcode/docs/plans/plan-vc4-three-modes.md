# VectorCode VC-4: Three Interaction Modes

**Goal:** Build Mode A (terminal REPL), Mode B (autonomous), and Mode C (hybrid) — all running simultaneously via TaskQueue, sharing VectorCodeSession state.
**Architecture:** repl.py is a blocking Rich-based terminal loop. autonomous.py submits a GSDLoop run as a TaskQueue HIGH-priority task and returns immediately. hybrid.py wraps autonomous.py but injects checkpoint gates at plan approval and RED-action boundaries using asyncio.Event for user confirmation. All three modes import and share VectorCodeSession.get() and GSDLoop.
**Files:**
- Create: `districts/coding/vectorcode/repl.py`
- Create: `districts/coding/vectorcode/autonomous.py`
- Create: `districts/coding/vectorcode/hybrid.py`
- Create: `tests/test_vectorcode_vc4.py`

---

### Task 1: Mode A — Terminal REPL

- [ ] Write failing test
  ```python
  from unittest.mock import patch, MagicMock
  from districts.coding.vectorcode.repl import VectorREPL
  def test_repl_instantiates():
      repl = VectorREPL()
      assert repl.mode == "repl"
      assert hasattr(repl, "session")
      assert hasattr(repl, "gsd")
  def test_repl_has_commands():
      repl = VectorREPL()
      assert hasattr(repl, "handle_command")
      commands = repl.COMMANDS
      assert "/help" in commands
      assert "/status" in commands
      assert "/mode" in commands
      assert "/quit" in commands
  def test_repl_mode_switch():
      repl = VectorREPL()
      repl.handle_command("/mode auto")
      assert repl.session.mode == "auto"
  def test_repl_status_returns_dict():
      repl = VectorREPL()
      status = repl.get_status()
      assert "mode" in status
      assert "model" in status
      assert "hp" in status
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc4.py -k "repl" -v` → expect FAIL
- [ ] Implement `districts/coding/vectorcode/repl.py`
- [ ] Run: `pytest tests/test_vectorcode_vc4.py -k "repl" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc4): VectorREPL Mode A terminal interface"`

---

### Task 2: Mode B — Autonomous agent

- [ ] Write failing test
  ```python
  from unittest.mock import patch, MagicMock
  from districts.coding.vectorcode.autonomous import VectorAutonomous
  def test_autonomous_submit_returns_task_id():
      with patch("districts.coding.vectorcode.autonomous.TaskQueue") as MockTQ:
          mock_tq = MagicMock()
          mock_tq.get.return_value = mock_tq
          mock_tq.submit.return_value = "task-abc-123"
          MockTQ.get.return_value = mock_tq
          va = VectorAutonomous()
          task_id = va.submit("build a login endpoint")
          assert task_id == "task-abc-123"
  def test_autonomous_uses_high_priority():
      with patch("districts.coding.vectorcode.autonomous.TaskQueue") as MockTQ:
          with patch("districts.coding.vectorcode.autonomous.Priority") as MockPri:
              mock_tq = MagicMock()
              mock_tq.get.return_value = mock_tq
              mock_tq.submit.return_value = "x"
              MockTQ.get.return_value = mock_tq
              va = VectorAutonomous()
              va.submit("task")
              call_kwargs = mock_tq.submit.call_args[1]
              assert "priority" in call_kwargs
  def test_autonomous_mode_is_auto():
      va = VectorAutonomous()
      assert va.session.mode in ("auto", "repl", "hybrid")
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc4.py -k "autonomous" -v` → expect FAIL
- [ ] Implement `districts/coding/vectorcode/autonomous.py`
- [ ] Run: `pytest tests/test_vectorcode_vc4.py -k "autonomous" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc4): VectorAutonomous Mode B TaskQueue-based"`

---

### Task 3: Mode C — Hybrid with checkpoint gates

- [ ] Write failing test
  ```python
  from unittest.mock import patch, MagicMock
  from districts.coding.vectorcode.hybrid import VectorHybrid, CheckpointGate
  def test_hybrid_has_checkpoint_types():
      assert hasattr(CheckpointGate, "PLAN_APPROVAL")
      assert hasattr(CheckpointGate, "RED_ACTION")
      assert hasattr(CheckpointGate, "DESTRUCTIVE_EDIT")
  def test_hybrid_checkpoint_registration():
      vh = VectorHybrid()
      assert hasattr(vh, "checkpoints")
      assert CheckpointGate.PLAN_APPROVAL in vh.checkpoints
      assert CheckpointGate.RED_ACTION in vh.checkpoints
  def test_hybrid_needs_approval_for_red():
      vh = VectorHybrid()
      assert vh.needs_approval("delete_files") is True
      assert vh.needs_approval("read_file") is False
  def test_hybrid_needs_approval_for_plan():
      vh = VectorHybrid()
      assert vh.needs_approval("plan_approval") is True
  def test_hybrid_mode_label():
      vh = VectorHybrid()
      assert vh.mode_label == "hybrid"
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc4.py -k "hybrid" -v` → expect FAIL
- [ ] Implement `districts/coding/vectorcode/hybrid.py`
- [ ] Run: `pytest tests/test_vectorcode_vc4.py -k "hybrid" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc4): VectorHybrid Mode C checkpoint gates"`

---

### Task 4: Full VC-4 integration smoke

- [ ] Run: `pytest tests/test_vectorcode_vc4.py -v` → all pass
- [ ] Commit: `git commit -m "feat(vc4): three interaction modes complete — REPL/Auto/Hybrid"`
