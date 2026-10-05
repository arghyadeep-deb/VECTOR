"""Regression tests for round-9 LLM-judge indeterminate results."""

from vectorcode.src.evals.core.types import EvalRecord
from vectorcode.src.evals.scorers.ama_bench_judge import AMABenchScorer, _parse_judge_label
from vectorcode.src.evals.scorers.email_triage import EmailTriageScorer
from vectorcode.src.evals.scorers.liveresearch import LiveResearchBenchScorer as DeepResearchScorer
from vectorcode.src.evals.scorers.liveresearchbench import LiveResearchBenchScorer
from vectorcode.src.evals.scorers.pinchbench import PinchBenchScorer
from vectorcode.src.evals.scorers.research_mining import ResearchMiningScorer
from vectorcode.src.evals.scorers._checklist import ChecklistScorer


class _Judge:
    def __init__(self, response="not a verdict", error=None):
        self.response = response
        self.error = error

    def generate(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


def _record(**metadata):
    return EvalRecord(
        record_id="round9",
        category="test",
        problem="Research question: Why?",
        reference="reference answer",
        metadata=metadata,
    )


def test_ama_unparseable_judge_is_indeterminate():
    result, meta = AMABenchScorer(_Judge(), "judge").score(_record(), "reference answer")
    assert result is None
    assert meta["judge_parse_failed"] is True


def test_ama_contradictory_yes_and_no_is_unparseable():
    assert _parse_judge_label("Yes on relevance, but no overall") is None


def test_email_unparseable_and_exception_are_indeterminate():
    record = _record(urgency="high", category="action")
    answer = "urgency: low\ncategory: info\ndraft: hello"
    assert EmailTriageScorer(_Judge(), "judge").score(record, answer)[0] is None
    assert EmailTriageScorer(_Judge(error=RuntimeError("down")), "judge").score(record, answer)[0] is None


def test_research_mining_does_not_invent_missing_scores():
    result, meta = ResearchMiningScorer(_Judge("accuracy: 5"), "judge").score(_record(), "report")
    assert result is None
    assert meta["scores"] == {"accuracy": 5}


def test_deep_research_unparseable_judge_is_indeterminate():
    result, meta = DeepResearchScorer(_Judge(), "judge").score(_record(), "report")
    assert result is None
    assert meta["reason"] == "unparseable_judge_response"


def test_live_research_bench_unparseable_judge_is_indeterminate():
    result, meta = LiveResearchBenchScorer(_Judge(), "judge").score(
        _record(checklist=["one"]), "report"
    )
    assert result is None
    assert meta["reason"] == "unparseable_judge_response"


def test_pinchbench_unparseable_judge_is_indeterminate():
    record = _record(grading_type="llm_judge", llm_judge_rubric="score quality")
    result, meta = PinchBenchScorer(_Judge(), "judge").score(record, "answer")
    assert result is None
    assert meta["score"] is None


def test_shared_checklist_parse_failure_is_indeterminate():
    score, details = ChecklistScorer(_Judge(), "judge").score_checklist(
        "answer", ["criterion"]
    )
    assert score is None
    assert details[0]["passed"] is None
