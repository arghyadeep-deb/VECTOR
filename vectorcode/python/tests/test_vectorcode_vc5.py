import pytest
import time
from unittest.mock import patch, MagicMock

def test_all_hook_names_defined():
    from vectorcode.hooks.registry import HookRegistry, HookName
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
    from vectorcode.hooks.registry import HookRegistry, HookName
    reg = HookRegistry()
    called = []
    reg.register(HookName.PRE_EDIT, lambda ctx: called.append(ctx))
    reg.fire(HookName.PRE_EDIT, {"file": "main.py"})
    assert len(called) == 1
    assert called[0]["file"] == "main.py"

def test_hook_priority_order():
    from vectorcode.hooks.registry import HookRegistry, HookName
    reg = HookRegistry()
    order = []
    reg.register(HookName.POST_TASK, lambda ctx: order.append("low"), priority=10)
    reg.register(HookName.POST_TASK, lambda ctx: order.append("high"), priority=1)
    reg.fire(HookName.POST_TASK, {})
    assert order == ["high", "low"]

def test_hook_timeout_protection():
    from vectorcode.hooks.registry import HookRegistry, HookName
    reg = HookRegistry(default_timeout=0.1)
    def slow_hook(ctx):
        time.sleep(5)
    reg.register(HookName.PRE_TASK, slow_hook)
    # Should not raise — timeout caught internally
    reg.fire(HookName.PRE_TASK, {})

def test_hook_multiple_handlers():
    from vectorcode.hooks.registry import HookRegistry, HookName
    reg = HookRegistry()
    results = []
    reg.register(HookName.POST_EDIT, lambda ctx: results.append("a"))
    reg.register(HookName.POST_EDIT, lambda ctx: results.append("b"))
    reg.fire(HookName.POST_EDIT, {})
    assert len(results) == 2

def test_hook_unregister():
    from vectorcode.hooks.registry import HookRegistry, HookName
    reg = HookRegistry()
    called = []
    fn = lambda ctx: called.append(1)
    reg.register(HookName.NOTIFY, fn)
    reg.unregister(HookName.NOTIFY, fn)
    reg.fire(HookName.NOTIFY, {})
    assert len(called) == 0

def test_hook_list():
    from vectorcode.hooks.registry import HookRegistry, HookName
    reg = HookRegistry()
    reg.register(HookName.ROUTE, lambda ctx: None)
    handlers = reg.list_handlers(HookName.ROUTE)
    assert len(handlers) == 1

def test_all_worker_names_defined():
    from vectorcode.hooks.workers import BackgroundWorkers, WorkerName
    expected = {
        "ULTRALEARN", "OPTIMIZE", "CONSOLIDATE", "PREDICT",
        "AUDIT", "MAP", "PRELOAD", "DEEPDIVE",
        "DOCUMENT", "REFACTOR", "BENCHMARK", "TESTGAPS"
    }
    actual = {w.name for w in WorkerName}
    assert expected == actual

def test_worker_submits_to_task_queue():
    with patch("vectorcode.hooks.workers.TaskQueue") as MockTQ:
        mock_tq = MagicMock()
        mock_tq.get.return_value = mock_tq
        mock_tq.submit.return_value = "worker-task-1"
        MockTQ.get.return_value = mock_tq
        from vectorcode.hooks.workers import BackgroundWorkers
        bw = BackgroundWorkers()
        task_id = bw.submit(from_module_import_WorkerName_ULTRALEARN())
        assert task_id is not None
        mock_tq.submit.assert_called_once()

def from_module_import_WorkerName_ULTRALEARN():
    from vectorcode.hooks.workers import WorkerName
    return WorkerName.ULTRALEARN

def test_worker_uses_low_priority():
    with patch("vectorcode.hooks.workers.TaskQueue") as MockTQ:
        mock_tq = MagicMock()
        mock_tq.get.return_value = mock_tq
        mock_tq.submit.return_value = "x"
        MockTQ.get.return_value = mock_tq
        from vectorcode.hooks.workers import BackgroundWorkers, WorkerName
        bw = BackgroundWorkers()
        bw.submit(WorkerName.OPTIMIZE)
        kwargs = mock_tq.submit.call_args[1]
        assert "priority" in kwargs

def test_ultralearn_extracts_patterns():
    with patch("vectorcode.hooks.workers.PatternStore") as MockPS:
        with patch("vectorcode.hooks.workers.EpisodicMemory") as MockMem:
            mock_mem = MagicMock()
            mock_mem.recall.return_value = [{"content": "test", "tags": ["code"]}]
            MockMem.return_value = mock_mem
            MockPS.return_value = MagicMock()
            from vectorcode.hooks.workers import BackgroundWorkers
            bw = BackgroundWorkers()
            bw.run_ultralearn()
            MockPS.return_value.save_pattern.assert_called()

def test_worker_list():
    from vectorcode.hooks.workers import BackgroundWorkers, WorkerName
    bw = BackgroundWorkers()
    workers = bw.list_workers()
    assert len(workers) == 12
    assert WorkerName.ULTRALEARN in workers

def test_hook_context_passed_correctly():
    from vectorcode.hooks.registry import HookRegistry, HookName
    reg = HookRegistry()
    received = []
    reg.register(HookName.SESSION_START, lambda ctx: received.append(ctx.copy()))
    reg.fire(HookName.SESSION_START, {"session_id": "abc", "mode": "repl"})
    assert received[0]["session_id"] == "abc"
    assert received[0]["mode"] == "repl"


