# VectorCode VC-5: Hooks + Background Workers

**Goal:** Port reference 17 hooks and 12 background workers to Python, wired into VectorCode's task lifecycle and VECTOR's TaskQueue.
**Architecture:** HookRegistry is a priority-ordered dict of hook_name → list[callable]. HookExecutor fires hooks with timeout protection. All 12 background workers submit themselves as LOW-priority TaskQueue tasks. Workers run between user tasks and feed results back into PatternStore and episodic_memory.
**Files:**
- Create: `agents/districts/coding/vectorcode/hooks/__init__.py`
- Create: `agents/districts/coding/vectorcode/hooks/registry.py`
- Create: `agents/districts/coding/vectorcode/hooks/workers.py`
- Create: `tests/test_vectorcode_vc5.py`

---

### Task 1: HookRegistry — 17 hooks

- [ ] Write failing test
  ```python
  from agents.districts.coding.vectorcode.hooks.registry import HookRegistry, HookName
  def test_all_hook_names_defined():
      expected = {
          "PRE_EDIT", "POST_EDIT", "PRE_TASK", "POST_TASK",
          "SESSION_START", "SESSION_END", "ROUTE", "EXPLAIN",
          "PRETRAIN", "BUILD_AGENTS", "TRANSFER", "TEAMMATE_IDLE",
          "TASK_COMPLETE", "NOTIFY", "INTELLIGENCE",
          "SESSION_RESTORE", "POST_COMMAND"
      }
      actual = {h.name for h in HookName}
      assert expected == actual
  def test_hook_register_and_fire():
      reg = HookRegistry()
      called = []
      reg.register(HookName.PRE_EDIT, lambda ctx: called.append(ctx))
      reg.fire(HookName.PRE_EDIT, {"file": "main.py"})
      assert len(called) == 1
      assert called[0]["file"] == "main.py"
  def test_hook_priority_order():
      reg = HookRegistry()
      order = []
      reg.register(HookName.POST_TASK, lambda ctx: order.append("low"), priority=10)
      reg.register(HookName.POST_TASK, lambda ctx: order.append("high"), priority=1)
      reg.fire(HookName.POST_TASK, {})
      assert order == ["high", "low"]
  def test_hook_timeout_protection():
      import time
      reg = HookRegistry(default_timeout=0.1)
      import pytest
      def slow_hook(ctx):
          time.sleep(5)
      reg.register(HookName.PRE_TASK, slow_hook)
      # Should not raise — timeout is caught internally
      reg.fire(HookName.PRE_TASK, {})
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc5.py -k "hook" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/hooks/registry.py`
- [ ] Run: `pytest tests/test_vectorcode_vc5.py -k "hook" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc5): HookRegistry 17 hooks priority-ordered"`

---

### Task 2: BackgroundWorkers — 12 workers via TaskQueue

- [ ] Write failing test
  ```python
  from unittest.mock import patch, MagicMock
  from agents.districts.coding.vectorcode.hooks.workers import BackgroundWorkers, WorkerName
  def test_all_worker_names_defined():
      expected = {
          "ULTRALEARN", "OPTIMIZE", "CONSOLIDATE", "PREDICT",
          "AUDIT", "MAP", "PRELOAD", "DEEPDIVE",
          "DOCUMENT", "REFACTOR", "BENCHMARK", "TESTGAPS"
      }
      actual = {w.name for w in WorkerName}
      assert expected == actual
  def test_worker_submits_to_task_queue():
      with patch("agents.districts.coding.vectorcode.hooks.workers.TaskQueue") as MockTQ:
          mock_tq = MagicMock()
          mock_tq.get.return_value = mock_tq
          mock_tq.submit.return_value = "worker-task-1"
          MockTQ.get.return_value = mock_tq
          bw = BackgroundWorkers()
          task_id = bw.submit(WorkerName.ULTRALEARN)
          assert task_id is not None
          mock_tq.submit.assert_called_once()
  def test_worker_uses_low_priority():
      with patch("agents.districts.coding.vectorcode.hooks.workers.TaskQueue") as MockTQ:
          with patch("agents.districts.coding.vectorcode.hooks.workers.Priority") as MockPri:
              mock_tq = MagicMock()
              mock_tq.get.return_value = mock_tq
              mock_tq.submit.return_value = "x"
              MockTQ.get.return_value = mock_tq
              bw = BackgroundWorkers()
              bw.submit(WorkerName.OPTIMIZE)
              kwargs = mock_tq.submit.call_args[1]
              assert "priority" in kwargs
  def test_ultralearn_extracts_patterns():
      with patch("agents.districts.coding.vectorcode.hooks.workers.PatternStore") as MockPS:
          with patch("agents.districts.coding.vectorcode.hooks.workers.EpisodicMemory") as MockMem:
              mock_mem = MagicMock()
              mock_mem.recall.return_value = [{"content": "test", "tags": ["code"]}]
              MockMem.return_value = mock_mem
              MockPS.return_value = MagicMock()
              bw = BackgroundWorkers()
              bw.run_ultralearn()
              MockPS.return_value.save_pattern.assert_called()
  ```
- [ ] Run: `pytest tests/test_vectorcode_vc5.py -k "worker" -v` → expect FAIL
- [ ] Implement `agents/districts/coding/vectorcode/hooks/workers.py`
- [ ] Run: `pytest tests/test_vectorcode_vc5.py -k "worker" -v` → expect PASS
- [ ] Commit: `git commit -m "feat(vc5): BackgroundWorkers 12 workers via TaskQueue"`

---

### Task 3: Full VC-5 integration smoke

- [ ] Run: `pytest tests/test_vectorcode_vc5.py -v` → all pass
- [ ] Commit: `git commit -m "feat(vc5): hooks + workers complete — 17 hooks, 12 bg workers"`

