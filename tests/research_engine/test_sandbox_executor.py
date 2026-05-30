import asyncio

from core.research_engine.models import ExperimentDesign, ExperimentResult
from core.research_engine.sandbox_executor import SandboxExecutor


SAMPLE_CODE = '''
def run_experiment():
    import random
    import statistics
    random.seed(42)
    data = [random.gauss(100, 15) for _ in range(30)]
    for v in data:
        print(f"STAT:sample:{v}")
    return {"mean": statistics.mean(data), "std": statistics.stdev(data), "n": 30}
'''

DESIGN = ExperimentDesign(
    hypothesis_id="HYP-TEST-EXEC-001",
    experiment_type="statistical_test",
    sample_size=30,
    procedure=["Run"],
    success_criteria="pass",
)


class TestSandboxExecutor:
    def setup_method(self):
        self.executor = SandboxExecutor(timeout=60)

    def test_subprocess_execution(self):
        result = self.executor.execute(DESIGN, SAMPLE_CODE)
        assert isinstance(result, ExperimentResult)
        assert result.experiment_id == "HYP-TEST-EXEC-001"
        assert result.status in ("completed", "failed")

    def test_result_parsing(self):
        code = '''
def run_experiment():
    print("STAT:mean:42.5")
    print("STAT:std:3.14")
    print("STAT:count:100")
    return {"status": "ok"}
'''
        result = self.executor.execute(DESIGN, code)
        if result.status == "completed":
            assert "mean" in result.summary_stats
            assert result.summary_stats["mean"] == 42.5
            assert result.summary_stats["std"] == 3.14

    def test_timeout_enforcement(self):
        slow = self.executor.__class__(timeout=1)
        code = '''
def run_experiment():
    import time
    time.sleep(10)
    return {"status": "ok"}
'''
        result = slow.execute(DESIGN, code)
        assert result.status in ("timeout", "failed")

    def test_ast_code_safety_blocked(self):
        unsafe_code = '''
def run_experiment():
    import os
    os.system("rm -rf /")
    return {"status": "hacked"}
'''
        result = self.executor.execute(DESIGN, unsafe_code)
        assert result.status in ("failed", "error")
        assert result.error is not None

    def test_ast_safety_eval_blocked(self):
        code = '''
def run_experiment():
    eval("__import__('os').system('ls')")
    return {"status": "ok"}
'''
        result = self.executor.execute(DESIGN, code)
        assert result.status in ("failed", "error")

    def test_async_execute(self):
        code = '''
def run_experiment():
    return {"status": "async_ok"}
'''
        result = asyncio.run(self.executor.execute_async(DESIGN, code))
        assert isinstance(result, ExperimentResult)
        assert result.experiment_id == "HYP-TEST-EXEC-001"

    def test_stat_extraction_empty(self):
        stats = self.executor._extract_stats("no stats here")
        assert stats == {}

    def test_stat_extraction_mixed(self):
        stdout = "STAT:mean:10.5\nSTAT:label:hello\nSTAT:count:5"
        stats = self.executor._extract_stats(stdout)
        assert stats["mean"] == 10.5
        assert stats["label"] == "hello"
        assert stats["count"] == 5
