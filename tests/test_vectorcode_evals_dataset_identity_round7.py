"""Regression tests for stable evaluation dataset identities."""

import sys
from types import SimpleNamespace

import pytest

from vectorcode.src.evals.datasets.livecodebench import LiveCodeBenchDataset
from vectorcode.src.evals.datasets.liveresearch import LiveResearchBenchDataset
from vectorcode.src.evals.datasets.swebench import SWEBenchDataset
from vectorcode.src.evals.datasets.swefficiency import SWEfficiencyDataset
from vectorcode.src.evals.datasets.terminalbench import TerminalBenchDataset
from vectorcode.src.evals.datasets.webchorearena import WebChoreArenaDataset


def _records_by_problem(provider):
    return {record.problem: record.record_id for record in provider.iter_records()}


@pytest.mark.parametrize(
    ("factory", "rows"),
    [
        (
            LiveCodeBenchDataset,
            [{"question_content": f"problem {i}"} for i in range(8)],
        ),
        (
            SWEBenchDataset,
            [{"problem_statement": f"problem {i}"} for i in range(8)],
        ),
        (
            SWEfficiencyDataset,
            [{"problem_statement": f"problem {i}"} for i in range(8)],
        ),
        (
            TerminalBenchDataset,
            [{"question": f"problem {i}"} for i in range(8)],
        ),
    ],
)
def test_fallback_record_ids_survive_shuffle_seed(monkeypatch, factory, rows):
    fake_datasets = SimpleNamespace(load_dataset=lambda *args, **kwargs: list(rows))
    monkeypatch.setitem(sys.modules, "datasets", fake_datasets)

    first = factory()
    first.load(seed=1)
    second = factory()
    second.load(seed=7)

    assert _records_by_problem(first) == _records_by_problem(second)


def test_webchorearena_fallback_record_ids_survive_shuffle_seed(tmp_path, monkeypatch):
    tasks = [{"intent": f"task {i}"} for i in range(8)]
    config_dir = tmp_path / "repo" / "AgentOccam" / "config_files"
    config_dir.mkdir(parents=True)

    first = WebChoreArenaDataset(cache_dir=str(tmp_path))
    second = WebChoreArenaDataset(cache_dir=str(tmp_path))
    monkeypatch.setattr(first, "_load_tasks", lambda unused: list(tasks))
    monkeypatch.setattr(second, "_load_tasks", lambda unused: list(tasks))

    first.load(seed=1)
    second.load(seed=7)

    assert _records_by_problem(first) == _records_by_problem(second)


def test_liveresearch_preserves_zero_id(tmp_path):
    prompt_dir = tmp_path / "data" / "prompt_data"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "query.jsonl").write_text(
        '{"id": 0, "prompt": "zero", "topic": "test"}\n', encoding="utf-8"
    )

    provider = LiveResearchBenchDataset(path=str(tmp_path))
    provider.load()

    assert next(provider.iter_records()).record_id == "liveresearch-0"


if __name__ == "__main__":
    raise SystemExit("Run with pytest")
