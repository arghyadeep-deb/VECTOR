import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import datetime, timezone

from core.research_engine.models import Hypothesis, ExperimentDesign
from core.research_engine.experiment_designer import ExperimentDesigner


def _make_hypothesis(title: str = "Test hypothesis", description: str = "Testing effect of X on Y") -> Hypothesis:
    return Hypothesis(
        id="HYP-TEST-001",
        title=title,
        description=description,
        variables={"x": "treatment", "y": "outcome"},
        expected_outcome="Significant effect observed",
        confidence=0.7,
        status="proposed",
        created_at=datetime.now(timezone.utc).isoformat(),
        source="test",
    )


class TestExperimentDesigner:
    def setup_method(self):
        self.designer = ExperimentDesigner()

    def test_design_from_hypothesis(self):
        h = _make_hypothesis()
        design = self.designer.design(h)
        assert isinstance(design, ExperimentDesign)
        assert design.hypothesis_id == h.id
        assert design.experiment_type in ("benchmark", "ml_train", "statistical_test", "ablation")
        assert design.sample_size >= 2
        assert len(design.procedure) > 0

    def test_validate_design_valid(self):
        design = ExperimentDesign(
            hypothesis_id="HYP-TEST-002",
            experiment_type="statistical_test",
            controlled_vars={"alpha": 0.05},
            independent_var="treatment",
            dependent_var="outcome",
            sample_size=30,
            procedure=["Collect data", "Run test"],
            success_criteria="p < 0.05",
        )
        errors = self.designer.validate_design(design)
        assert errors == []

    def test_validate_design_invalid(self):
        design = ExperimentDesign(
            hypothesis_id="HYP-TEST-003",
            experiment_type="",
            sample_size=1,
        )
        errors = self.designer.validate_design(design)
        assert len(errors) >= 3

    def test_template_selection_benchmark(self):
        h = _make_hypothesis(title="Benchmark throughput test", description="Measuring latency")
        design = self.designer.design(h)
        assert design.experiment_type == "benchmark"

    def test_template_selection_ml(self):
        h = _make_hypothesis(title="Train a neural network", description="Model accuracy test")
        design = self.designer.design(h)
        assert design.experiment_type in ("ml_train", "ml_training")

    def test_template_selection_ablation(self):
        h = _make_hypothesis(title="Ablation study", description="Remove component and measure impact")
        design = self.designer.design(h)
        assert design.experiment_type == "ablation"

    def test_script_generation_benchmark(self):
        design = ExperimentDesign(
            hypothesis_id="HYP-SCRIPT-001",
            experiment_type="benchmark",
            dependent_var="throughput_latency",
            sample_size=100,
            procedure=["Run benchmark"],
            success_criteria="pass",
        )
        script = self.designer.generate_script(design)
        assert script is not None
        assert "Benchmark experiment" in script
        assert "STAT:" in script

    def test_script_generation_ml_train(self):
        design = ExperimentDesign(
            hypothesis_id="HYP-SCRIPT-002",
            experiment_type="ml_train",
            controlled_vars={"epochs": 5, "batch_size": 16},
            independent_var="model",
            dependent_var="accuracy",
            sample_size=1000,
            procedure=["Train"],
            success_criteria="acc > 0.8",
        )
        script = self.designer.generate_script(design)
        assert script is not None
        assert "ML training" in script
        assert "epochs" in script

    def test_script_generation_statistical(self):
        design = ExperimentDesign(
            hypothesis_id="HYP-SCRIPT-003",
            experiment_type="statistical_test",
            controlled_vars={"alpha": 0.05, "test_type": "two_tailed"},
            sample_size=60,
            procedure=["Collect", "Test"],
            success_criteria="p < 0.05",
        )
        script = self.designer.generate_script(design)
        assert script is not None
        assert "Statistical test" in script
        assert "scipy" in script

    def test_script_generation_ablation(self):
        design = ExperimentDesign(
            hypothesis_id="HYP-SCRIPT-004",
            experiment_type="ablation",
            sample_size=50,
            independent_var="component_removed",
            dependent_var="performance",
            procedure=["Baseline", "Remove", "Compare"],
            success_criteria="delta > 5%",
        )
        script = self.designer.generate_script(design)
        assert script is not None
        assert "Ablation" in script
        assert "baseline_config" in script

    def test_identify_variables(self):
        h = _make_hypothesis(
            title="Effect of training size on model accuracy",
            description="Comparing different batch sizes and measuring validation loss",
        )
        vars = self.designer._identify_variables(h)
        assert "independent" in vars
        assert "dependent" in vars
        assert len(vars["independent"]) > 0
        assert len(vars["dependent"]) > 0
