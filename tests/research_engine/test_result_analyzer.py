import sys
from unittest.mock import patch


from core.research_engine.models import ExperimentResult, AnalysisResult
from core.research_engine.result_analyzer import ResultAnalyzer


class MockTTestResult:
    statistic = 2.5
    pvalue = 0.02


class MockPearsonResult:
    statistic = 0.6
    pvalue = 0.01


class MockScipyStats:
    @staticmethod
    def ttest_ind(a, b):
        return MockTTestResult()

    @staticmethod
    def pearsonr(x, y):
        return MockPearsonResult()

    @staticmethod
    def normaltest(data):
        return MockTTestResult()


class MockNumpy:
    @staticmethod
    def std(data, ddof=1):
        return 1.0

    @staticmethod
    def mean(data):
        return sum(data) / len(data)


class TestResultAnalyzer:
    def setup_method(self):
        with patch.dict("sys.modules", {
            "scipy.stats": MockScipyStats(),
            "numpy": MockNumpy(),
        }):
            self.analyzer = ResultAnalyzer()

    def _make_result(self, values: list[float]) -> ExperimentResult:
        return ExperimentResult(
            experiment_id="HYP-TEST-ANA-001",
            status="completed",
            raw_data=[{"value": v} for v in values],
            summary_stats={"mean": sum(values) / len(values)},
        )

    def test_descriptive_statistics(self):
        result = self._make_result([10, 20, 30, 40, 50])
        analysis = self.analyzer.analyze(result)
        assert isinstance(analysis, AnalysisResult)
        assert analysis.experiment_id == "HYP-TEST-ANA-001"
        assert analysis.significance >= 0.0
        assert analysis.effect_size >= 0.0

    def test_significance_test(self):
        with patch.dict("sys.modules", {
            "scipy.stats": MockScipyStats(),
            "numpy": MockNumpy(),
        }):
            analyzer = ResultAnalyzer()
            result = self._make_result([1, 2, 3, 4, 5, 6, 7, 8])
            analysis = analyzer.analyze(result)
            assert len(analysis.statistical_tests) > 0
            assert analysis.significance < 0.05

    def test_insufficient_data(self):
        result = self._make_result([1.0])
        analysis = self.analyzer.analyze(result)
        assert len(analysis.statistical_tests) == 0

    def test_interpretation_significant(self):
        interp = self.analyzer._interpret(0.03, 0.6, 1)
        assert "Significant result" in interp

    def test_interpretation_not_significant(self):
        interp = self.analyzer._interpret(0.50, 0.1, 1)
        assert "not statistically significant" in interp.lower()

    def test_supports_hypothesis(self):
        with patch.dict("sys.modules", {
            "scipy.stats": MockScipyStats(),
            "numpy": MockNumpy(),
        }):
            analyzer = ResultAnalyzer()
            result = self._make_result([1, 2, 3, 4, 5, 6, 7, 8])
            analysis = analyzer.analyze(result)
            assert isinstance(analysis.supports_hypothesis, bool)

    def test_flatten_data(self):
        result = self._make_result([1.0, 2.0, 3.0])
        flat = self.analyzer._flatten_data(result.raw_data)
        assert len(flat) == 3
        assert flat == [1.0, 2.0, 3.0]

    def test_basic_stats(self):
        stats = self.analyzer._basic_stats([1, 2, 3, 4, 5])
        assert stats["mean"] == 3.0
        assert stats["count"] == 5
        assert stats["min"] == 1.0
        assert stats["max"] == 5.0
        assert stats["median"] == 3.0

    def test_basic_stats_empty(self):
        stats = self.analyzer._basic_stats([])
        assert stats["count"] == 0

    def test_llm_interpretation_mock(self):
        interp = self.analyzer._interpret(0.03, 0.6, 1)
        assert "Significant" in interp
        assert "Medium" in interp
