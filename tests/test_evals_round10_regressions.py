"""Regression proofs for the round-10 eval audit fixes."""

from __future__ import annotations

import ast
import subprocess
from types import SimpleNamespace

import pytest

from vectorcode.src.evals.core.types import EvalRecord, EvalResult


@pytest.mark.parametrize(
    "relative_path",
    [
        "vectorcode/src/evals/comparison/table_gen.py",
        "vectorcode/src/evals/core/export.py",
        "vectorcode/src/evals/core/trace.py",
        "vectorcode/src/evals/datasets/loghub.py",
        "vectorcode/src/evals/datasets/paperarena.py",
        "vectorcode/src/evals/datasets/pinchbench.py",
        "vectorcode/src/evals/datasets/terminalbench_native.py",
    ],
)
def test_text_file_io_declares_utf8(relative_path: str) -> None:
    source = open(relative_path, encoding="utf-8").read()
    tree = ast.parse(source)
    missing = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else ""
        )
        if name not in {"open", "read_text", "write_text"}:
            continue
        if name == "open" and len(node.args) > 1:
            mode = node.args[1]
            if isinstance(mode, ast.Constant) and "b" in str(mode.value):
                continue
        if not any(keyword.arg == "encoding" for keyword in node.keywords):
            missing.append(node.lineno)

    assert missing == [], f"text I/O without encoding at lines {missing}"


class _JudgeBackend:
    def __init__(self, response: str) -> None:
        self.response = response

    def generate(self, *args, **kwargs) -> str:
        return self.response


@pytest.mark.parametrize(
    ("module_name", "class_name", "valid_answer"),
    [
        ("gpqa_mcq", "GPQAScorer", "A"),
        ("mmlu_pro_mcq", "MMLUProScorer", "J"),
        ("supergpqa_mcq", "SuperGPQAScorer", "D"),
    ],
)
def test_mcq_judges_accept_explicit_answer_phrase(
    module_name: str,
    class_name: str,
    valid_answer: str,
) -> None:
    module = __import__(
        f"vectorcode.src.evals.scorers.{module_name}",
        fromlist=[class_name],
    )
    scorer = getattr(module, class_name)(
        _JudgeBackend(f"The answer is: {valid_answer}"),
        "judge",
    )
    record = EvalRecord("id", "problem", valid_answer, "reasoning")

    is_correct, metadata = scorer.score(record, "candidate response")

    assert is_correct is True
    assert metadata["candidate_letter"] == valid_answer


def test_morning_brief_unparseable_judge_is_indeterminate() -> None:
    from vectorcode.src.evals.scorers.morning_brief import MorningBriefScorer

    scorer = MorningBriefScorer(_JudgeBackend("not a structured verdict"), "judge")
    record = EvalRecord("brief", "calendar and todos", "urgent item", "agentic")

    is_correct, metadata = scorer.score(record, "a non-empty briefing")

    assert is_correct is None
    assert metadata["reason"] == "unparseable_judge_response"


def test_empty_third_party_commit_pin_is_rejected(tmp_path, monkeypatch) -> None:
    from vectorcode.src.evals.comparison.third_party import (
        CommitDriftError,
        ThirdPartyEntry,
        verify_commit_pin,
    )

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="a" * 40),
    )
    entry = ThirdPartyEntry(
        name="vector",
        path=tmp_path,
        pinned_commit="",
        runner_script="runner.py",
    )

    with pytest.raises(CommitDriftError, match="no pinned_commit"):
        verify_commit_pin(entry)


def test_wandb_tracker_omits_indeterminate_correctness(monkeypatch) -> None:
    import vectorcode.src.evals.trackers.wandb_tracker as module

    logged = []
    monkeypatch.setattr(
        module,
        "wandb",
        SimpleNamespace(log=lambda data, step: logged.append((data, step))),
    )
    tracker = module.WandbTracker("project")
    tracker._run = object()

    tracker.on_result(EvalResult("id", "answer", is_correct=None), SimpleNamespace())

    assert "sample/is_correct" not in logged[0][0]


def test_skill_benchmark_excludes_indeterminate_and_closes_backends(monkeypatch) -> None:
    import vectorcode.src.evals.backends.vector_direct as direct_module
    import vectorcode.src.evals.core.runner as runner_module
    import vectorcode.src.evals.datasets.pinchbench as dataset_module
    import vectorcode.src.evals.scorers.pinchbench as scorer_module
    from vectorcode.src.evals.skill_benchmark import (
        SkillBenchmarkConfig,
        SkillBenchmarkRunner,
    )

    class FakeBackend:
        def __init__(self, *args, **kwargs) -> None:
            self.closed = 0

        def close(self) -> None:
            self.closed += 1

    class FakeDataset:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def load(self, **kwargs) -> None:
            pass

    class FakeScorer:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeEvalRunner:
        def __init__(self, **kwargs) -> None:
            self.results = [
                EvalResult("pass", "", is_correct=True),
                EvalResult("unknown", "", is_correct=None),
            ]

        def run(self):
            return SimpleNamespace(
                accuracy=0.5,
                total_input_tokens=2,
                total_output_tokens=3,
            )

    agent_backend = FakeBackend()
    judge_backend = FakeBackend()
    benchmark = SkillBenchmarkRunner(SkillBenchmarkConfig(seeds=[42]))
    monkeypatch.setattr(
        benchmark,
        "_build_backend_for_condition",
        lambda condition: agent_backend,
    )
    monkeypatch.setattr(direct_module, "VectorDirectBackend", lambda **kwargs: judge_backend)
    monkeypatch.setattr(dataset_module, "PinchBenchDataset", FakeDataset)
    monkeypatch.setattr(scorer_module, "PinchBenchScorer", FakeScorer)
    monkeypatch.setattr(runner_module, "EvalRunner", FakeEvalRunner)

    result = benchmark._run_single_seed("no_skills", 42)

    assert result["pass_rate"] == 1.0
    assert result["per_task"] == {"pass": True}
    assert result["total_tokens"] == 5
    assert agent_backend.closed == 1
    assert judge_backend.closed == 1


def test_skill_benchmark_closes_agent_when_dataset_load_fails(monkeypatch) -> None:
    import vectorcode.src.evals.datasets.pinchbench as dataset_module
    from vectorcode.src.evals.skill_benchmark import (
        SkillBenchmarkConfig,
        SkillBenchmarkRunner,
    )

    class FakeBackend:
        closed = 0

        def close(self) -> None:
            self.closed += 1

    class BrokenDataset:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def load(self, **kwargs) -> None:
            raise RuntimeError("dataset failed")

    backend = FakeBackend()
    benchmark = SkillBenchmarkRunner(SkillBenchmarkConfig(seeds=[42]))
    monkeypatch.setattr(
        benchmark,
        "_build_backend_for_condition",
        lambda condition: backend,
    )
    monkeypatch.setattr(dataset_module, "PinchBenchDataset", BrokenDataset)

    with pytest.raises(RuntimeError, match="dataset failed"):
        benchmark._run_single_seed("no_skills", 42)

    assert backend.closed == 1
