"""Regression tests for indeterminate LLM-judge backend failures."""

import pytest

from vectorcode.src.evals.core.types import EvalRecord
from vectorcode.src.evals.scorers.deepplanning_scorer import DeepPlanningScorer
from vectorcode.src.evals.scorers.hle_judge import HLEScorer
from vectorcode.src.evals.scorers.frames_judge import FRAMESScorer
from vectorcode.src.evals.scorers.gaia_exact import GAIAScorer
from vectorcode.src.evals.scorers.knowledge_base import KnowledgeBaseScorer
from vectorcode.src.evals.scorers.loghub_scorer import LogHubScorer
from vectorcode.src.evals.scorers.paperarena_judge import PaperArenaScorer
from vectorcode.src.evals.scorers.ipw_mixed import IPWMixedScorer
from vectorcode.src.evals.scorers.reasoning_judge import ReasoningJudgeScorer
from vectorcode.src.evals.scorers.simpleqa_judge import SimpleQAScorer
from vectorcode.src.evals.scorers.terminalbench_judge import TerminalBenchScorer


class _FailingJudgeBackend:
    def generate(self, *_args, **_kwargs):
        raise RuntimeError("judge unavailable")


@pytest.mark.parametrize(
    "scorer_type",
    [
        DeepPlanningScorer,
        GAIAScorer,
        HLEScorer,
        KnowledgeBaseScorer,
        LogHubScorer,
        PaperArenaScorer,
        ReasoningJudgeScorer,
        SimpleQAScorer,
    ],
)
def test_judge_backend_failure_is_indeterminate(scorer_type):
    scorer = scorer_type(_FailingJudgeBackend(), "judge-model")
    record = EvalRecord(
        record_id="judge-failure",
        problem="What is two plus two?",
        reference="4",
        category="reasoning",
    )

    is_correct, metadata = scorer.score(record, "four")

    assert is_correct is None
    assert metadata["error"] == "judge unavailable"


class _MalformedJudgeBackend:
    def generate(self, *_args, **_kwargs):
        return "I cannot determine a grade."


@pytest.mark.parametrize(
    "scorer_type",
    [
        DeepPlanningScorer,
        FRAMESScorer,
        GAIAScorer,
        HLEScorer,
        IPWMixedScorer,
        KnowledgeBaseScorer,
        LogHubScorer,
        PaperArenaScorer,
        ReasoningJudgeScorer,
        SimpleQAScorer,
        TerminalBenchScorer,
    ],
)
def test_unparseable_judge_output_is_indeterminate(scorer_type):
    scorer = scorer_type(_MalformedJudgeBackend(), "judge-model")
    record = EvalRecord(
        record_id="judge-malformed",
        problem="Classify this result.",
        reference="expected answer",
        category="reasoning",
    )

    is_correct, metadata = scorer.score(record, "different answer")

    assert is_correct is None
    assert metadata["match_type"].endswith("unparseable")
