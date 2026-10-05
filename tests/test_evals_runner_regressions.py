"""Regression tests for resource and state handling in the eval runner."""

from pathlib import Path

from vectorcode.src.evals.core.backend import InferenceBackend
from vectorcode.src.evals.core.dataset import DatasetProvider
from vectorcode.src.evals.core.runner import EvalRunner
from vectorcode.src.evals.core.scorer import Scorer
from vectorcode.src.evals.core.types import EvalRecord, RunConfig


class _Dataset(DatasetProvider):
    dataset_id = "runner-regression"
    dataset_name = "Runner regression"

    def __init__(self) -> None:
        self.records = []

    def load(self, *, max_samples=None, split=None, seed=None) -> None:
        self.records = [EvalRecord("one", "question", "answer", "chat")]

    def iter_records(self):
        return iter(self.records)

    def size(self) -> int:
        return len(self.records)


class _Backend(InferenceBackend):
    backend_id = "runner-regression"

    def generate(self, prompt, *, model, system="", temperature=0.0, max_tokens=2048):
        return "answer"

    def generate_full(
        self, prompt, *, model, system="", temperature=0.0, max_tokens=2048
    ):
        return {"content": "answer", "usage": {}}


class _Scorer(Scorer):
    scorer_id = "runner-regression"

    def score(self, record, model_answer):
        return model_answer == record.reference, {}


class _TrackedEnvironment:
    THREAD_SAFE = True

    def __init__(self, close_events: list["_TrackedEnvironment"]) -> None:
        self.close_events = close_events

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self) -> None:
        self.close_events.append(self)


class _EnvironmentDataset(_Dataset):
    def __init__(self) -> None:
        super().__init__()
        self.created = []
        self.closed = []

    def create_task_env(self, record):
        env = _TrackedEnvironment(self.closed)
        self.created.append(env)
        return env


def _runner(dataset: DatasetProvider, output_path: Path) -> EvalRunner:
    config = RunConfig(
        benchmark="runner-regression",
        backend="runner-regression",
        model="test-model",
        max_workers=1,
        output_path=str(output_path),
    )
    return EvalRunner(config, dataset, _Backend(), _Scorer())


def test_run_does_not_accumulate_results_across_invocations(tmp_path):
    runner = _runner(_Dataset(), tmp_path / "results.jsonl")

    first = runner.run()
    second = runner.run()

    assert first.total_samples == 1
    assert second.total_samples == 1
    assert len(runner.results) == 1


def test_thread_safety_probe_closes_constructed_environment(tmp_path):
    dataset = _EnvironmentDataset()

    _runner(dataset, tmp_path / "results.jsonl").run()

    assert len(dataset.created) == 2
    assert dataset.created[0] in dataset.closed
    assert dataset.created[1] in dataset.closed


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        test_run_does_not_accumulate_results_across_invocations(Path(temp_dir))
        test_thread_safety_probe_closes_constructed_environment(Path(temp_dir))
