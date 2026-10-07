"""Regression proofs for the benchmark/city correctness audit."""
from __future__ import annotations

import json
import os
from pathlib import Path

from core.benchmark.benchmark_runner import BenchmarkRunner
from core.benchmark.benchmark_task import BenchmarkTask
from core.benchmark.report import BenchmarkReport
from core.city.agent_registry import AgentRegistry
from core.city.intent_qwen3_8b import IntentQwen3_8B
from core.loop.permission_gateway import PermissionGateway


class _PassingTask(BenchmarkTask):
    task_id = "TEST"
    category = "regression"

    def run(self, state):
        return self._success("ran", "passed")


class _NullIsolation:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


def test_benchmark_runner_resets_results_between_runs(monkeypatch):
    runner = BenchmarkRunner.__new__(BenchmarkRunner)
    runner.tasks = [_PassingTask()]
    runner.results = []
    monkeypatch.setattr("core.benchmark.benchmark_runner.IsolatedState", _NullIsolation)

    assert runner.run().summary["total_tasks"] == 1
    assert runner.run().summary["total_tasks"] == 1


def test_benchmark_report_json_save_uses_atomic_replace(tmp_path, monkeypatch):
    destination = tmp_path / "report.json"
    replace_calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def recording_replace(source, target):
        replace_calls.append((Path(source), Path(target)))
        real_replace(source, target)

    monkeypatch.setattr("core.benchmark.report.os.replace", recording_replace)
    BenchmarkReport([]).save_json(destination)

    assert json.loads(destination.read_text(encoding="utf-8"))["summary"]["total_tasks"] == 0
    assert len(replace_calls) == 1
    assert replace_calls[0][1] == destination
    assert replace_calls[0][0].parent == destination.parent


def test_ghost_persistence_preserves_explicit_zero_hp(monkeypatch):
    captured: dict[str, tuple] = {}

    class _Connection:
        def execute(self, sql, params):
            captured["params"] = params

        def commit(self):
            captured["committed"] = ()

    monkeypatch.setattr("core.memory.episodic.get_db_connection", lambda: _Connection())
    registry = AgentRegistry.__new__(AgentRegistry)
    registry._persist_ghost({
        "agent_id": "dead-1", "agent_name": "DeadAgent", "district": "qa",
        "generation": 1, "final_hp": 0, "health_points": 123,
        "ghost_memory": {},
    })

    assert captured["params"][4] == 0
    assert "committed" in captured


async def test_qwen_intent_classifier_has_torch_available_during_inference(monkeypatch):
    import torch

    class _Inputs(dict):
        def to(self, device):
            return self

    class _Tokenizer:
        def __call__(self, prompt, return_tensors):
            return _Inputs()

        def decode(self, output, skip_special_tokens):
            return "District: coding"

    class _Model:
        def generate(self, **kwargs):
            return [torch.tensor([1])]

    classifier = IntentQwen3_8B()
    classifier._tokenizer = _Tokenizer()
    classifier._model = _Model()
    monkeypatch.setattr(classifier, "_load_model", lambda: True)

    result = await classifier.classify("fix this bug")

    assert result is not None
    assert result["district"] == "coding"


def test_gateway_does_not_call_failed_or_unimplemented_handler_executed():
    assert not PermissionGateway._execution_succeeded({"status": "error", "error": "boom"})
    assert not PermissionGateway._execution_succeeded({"status": "blocked"})
    assert not PermissionGateway._execution_succeeded({"status": "not_implemented"})
    assert PermissionGateway._execution_succeeded({"status": "ok"})
