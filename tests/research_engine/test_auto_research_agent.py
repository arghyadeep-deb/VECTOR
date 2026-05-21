import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.research_engine.models import Hypothesis, ExperimentDesign, ExperimentResult, AnalysisResult, ResearchReport
from core.research_engine.auto_research_agent import AutoResearchAgent


def _make_design(hypothesis_id: str = "HYP-TEST-001") -> ExperimentDesign:
    return ExperimentDesign(
        hypothesis_id=hypothesis_id,
        experiment_type="statistical_test",
        controlled_vars={"alpha": 0.05},
        independent_var="treatment",
        dependent_var="outcome",
        sample_size=30,
        procedure=["Collect", "Test"],
        success_criteria="p < 0.05",
    )


def _make_result(experiment_id: str = "HYP-TEST-001") -> ExperimentResult:
    return ExperimentResult(
        experiment_id=experiment_id,
        status="completed",
        raw_data=[{"value": 1.0}, {"value": 2.0}],
        summary_stats={"mean": 1.5},
    )


def _make_analysis(experiment_id: str = "HYP-TEST-001") -> AnalysisResult:
    return AnalysisResult(
        experiment_id=experiment_id,
        statistical_tests=[{"test": "t_test", "p_value": 0.03}],
        significance=0.03,
        effect_size=0.5,
        interpretation="Significant result",
        supports_hypothesis=True,
    )


class TestAutoResearchAgent:
    def setup_method(self):
        self.agent = AutoResearchAgent()

    def test_full_cycle_execution(self):
        h = Hypothesis(
            id="HYP-TEST-CYCLE-001",
            title="Cycle test",
            description="Testing full cycle",
            variables={},
            expected_outcome="Significant",
            confidence=0.6,
            status="proposed",
            source="test",
        )
        with (
            patch.object(self.agent.designer, "design", return_value=_make_design(h.id)),
            patch.object(self.agent.executor, "execute", return_value=_make_result(h.id)),
            patch.object(self.agent.analyzer, "analyze", return_value=_make_analysis(h.id)),
        ):
            report = self.agent.run_from_hypothesis(h)
            assert isinstance(report, ResearchReport)
            assert report.hypothesis == h
            assert report.analysis is not None
            assert h.status in ("accepted", "rejected")

    def test_run_full_cycle(self):
        with (
            patch.object(self.agent, "generate_hypothesis") as mock_gh,
            patch.object(self.agent, "design_experiment") as mock_de,
            patch.object(self.agent, "execute_experiment") as mock_ee,
            patch.object(self.agent, "analyze_results") as mock_ar,
            patch.object(self.agent, "assemble_report") as mock_assemble,
        ):
            h = Hypothesis(id="HYP-TEST-002", title="Test", description="Test", status="proposed", source="test")
            d = _make_design(h.id)
            r = _make_result(h.id)
            a = _make_analysis(h.id)
            report = ResearchReport(hypothesis=h, experiment=d, analysis=a)

            mock_gh.return_value = h
            mock_de.return_value = d
            mock_ee.return_value = r
            mock_ar.return_value = a
            mock_assemble.return_value = report

            result = self.agent.run_full_cycle("test topic")
            assert result.hypothesis.id == "HYP-TEST-002"

    def test_error_handling(self):
        h = Hypothesis(id="HYP-TEST-ERR-001", title="Error test", description="Test error", status="proposed", source="test")
        with patch.object(self.agent.designer, "design", side_effect=RuntimeError("Design failed")):
            try:
                self.agent.run_from_hypothesis(h)
            except RuntimeError:
                assert True

    def test_generate_hypothesis(self):
        h = self.agent.generate_hypothesis("machine learning")
        assert isinstance(h, Hypothesis)
        assert "machine learning" in h.title.lower() or "machine learning" in h.description.lower()
        assert h.status == "proposed"
        assert 0.0 <= h.confidence <= 1.0

    def test_default_code_generated(self):
        d = _make_design()
        code = self.agent._default_experiment_code(d)
        assert "def run_experiment" in code
        assert "STAT:" in code
        assert str(d.sample_size) in code

    def test_scheduled_research_cancellation(self):
        import asyncio
        async def run():
            task = asyncio.create_task(self.agent.scheduled_research(interval_hours=24))
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        asyncio.run(run())
