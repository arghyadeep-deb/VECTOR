import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.research_engine.models import Hypothesis, ExperimentDesign, AnalysisResult, ResearchReport
from core.research_engine.report_assembler import ReportAssembler


def _make_hypothesis() -> Hypothesis:
    return Hypothesis(
        id="HYP-TEST-RPT-001",
        title="Test hypothesis for report",
        description="Testing effect of X on Y",
        variables={"x": "treatment"},
        expected_outcome="Significant",
        confidence=0.7,
        status="proposed",
        created_at=datetime.now(timezone.utc).isoformat(),
        source="test",
    )


def _make_design() -> ExperimentDesign:
    return ExperimentDesign(
        hypothesis_id="HYP-TEST-RPT-001",
        experiment_type="statistical_test",
        controlled_vars={"alpha": 0.05},
        independent_var="treatment",
        dependent_var="outcome",
        sample_size=30,
        procedure=["Collect", "Test"],
        success_criteria="p < 0.05",
    )


def _make_analysis() -> AnalysisResult:
    return AnalysisResult(
        experiment_id="HYP-TEST-RPT-001",
        statistical_tests=[{"test": "t_test", "p_value": 0.02}],
        significance=0.02,
        effect_size=0.5,
        interpretation="Significant result",
        supports_hypothesis=True,
    )


class TestReportAssembler:
    def setup_method(self):
        self.assembler = ReportAssembler()

    def test_assemble_report(self):
        h = _make_hypothesis()
        d = _make_design()
        a = _make_analysis()
        report = self.assembler.assemble(h, d, a)
        assert isinstance(report, ResearchReport)
        assert report.hypothesis == h
        assert report.experiment == d
        assert report.analysis == a
        assert len(report.sections) > 0
        assert "title" in report.sections

    def test_markdown_output(self):
        h = _make_hypothesis()
        d = _make_design()
        a = _make_analysis()
        report = self.assembler.assemble(h, d, a)
        md = self.assembler.render_markdown(report)
        assert isinstance(md, str)
        assert len(md) > 50
        assert "Research Report" in md
        assert h.title in md

    def test_assembler_without_hypothesis(self):
        d = _make_design()
        a = _make_analysis()
        report = self.assembler.assemble(None, d, a)
        assert report.sections.get("title") == "Research Report: Untitled"

    def test_assembler_without_analysis(self):
        h = _make_hypothesis()
        d = _make_design()
        report = self.assembler.assemble(h, d, None)
        assert report.sections.get("conclusion") is not None

    def test_conclusion_supports(self):
        h = _make_hypothesis()
        a = _make_analysis()
        conclusion = self.assembler._build_conclusion(h, a)
        assert "supports" in conclusion.lower()

    def test_conclusion_does_not_support(self):
        h = _make_hypothesis()
        a = _make_analysis()
        a.supports_hypothesis = False
        conclusion = self.assembler._build_conclusion(h, a)
        assert "does not support" in conclusion.lower()

    def test_vault_save_mocked(self):
        h = _make_hypothesis()
        d = _make_design()
        a = _make_analysis()

        with patch.object(self.assembler, "_save_to_vault") as mock_save:
            report = self.assembler.assemble(h, d, a)
            mock_save.assert_called_once_with(report)

    def test_vault_save_creates_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            assembler = ReportAssembler(vault_path=Path(tmpdir))
            h = _make_hypothesis()
            d = _make_design()
            a = _make_analysis()
            assembler.assemble(h, d, a)
            files = list(Path(tmpdir).iterdir())
            assert len(files) >= 1
            assert files[0].suffix == ".md"

    def test_generated_at_set(self):
        h = _make_hypothesis()
        d = _make_design()
        a = _make_analysis()
        report = self.assembler.assemble(h, d, a)
        assert report.generated_at is not None
        assert "T" in report.generated_at
