"""Experiment designer — generates ExperimentDesign from Hypothesis."""

import json
import os

__all__ = [
    "ExperimentDesigner",
    "TEMPLATES_DIR",
]

import re
from pathlib import Path
from typing import Optional

from loguru import logger

from .models import Hypothesis, ExperimentDesign

TEMPLATES_DIR = Path(__file__).parent / "templates"
_TEMPLATE_MAP = {
    "benchmark": "benchmark.py.j2",
    "ml_train": "ml_train.py.j2",
    "statistical_test": "statistical_test.py.j2",
    "ablation": "ablation.py.j2",
}

_RULE_TEMPLATES: dict[str, dict] = {
    "benchmark": {
        "experiment_type": "benchmark",
        "controlled_vars": {"hardware": "fixed", "seed": 42, "num_runs": 5},
        "independent_var": "model_or_config",
        "dependent_var": "throughput_latency_accuracy",
        "sample_size": 100,
        "procedure": [
            "Warm up system for 10 iterations",
            "Run inference on test dataset",
            "Record latency per sample",
            "Compute throughput at batch sizes 1, 8, 32",
            "Report mean and std across runs",
        ],
        "success_criteria": "Latency p95 under 100ms, throughput > 1000 req/s",
    },
    "ml_train": {
        "experiment_type": "ml_training",
        "controlled_vars": {"learning_rate": 0.001, "optimizer": "adam", "epochs": 10, "batch_size": 32},
        "independent_var": "model_architecture",
        "dependent_var": "val_accuracy_val_loss",
        "sample_size": 1000,
        "procedure": [
            "Split data into train/val/test 70/15/15",
            "Train model with fixed hyperparameters",
            "Evaluate on validation set each epoch",
            "Select best checkpoint by val loss",
            "Report final test metrics",
        ],
        "success_criteria": "Test accuracy >= 0.85, loss < 0.3",
    },
    "statistical_test": {
        "experiment_type": "statistical_test",
        "controlled_vars": {"alpha": 0.05, "test_type": "two_tailed"},
        "independent_var": "treatment_group",
        "dependent_var": "outcome_metric",
        "sample_size": 60,
        "procedure": [
            "Collect control and treatment samples",
            "Check normality via Shapiro-Wilk",
            "Run appropriate parametric or non-parametric test",
            "Compute effect size (Cohen's d)",
            "Report p-value and confidence interval",
        ],
        "success_criteria": "p < 0.05, statistical power > 0.8",
    },
    "ablation": {
        "experiment_type": "ablation",
        "controlled_vars": {"base_config": "default", "seed": 42},
        "independent_var": "component_removed",
        "dependent_var": "performance_delta",
        "sample_size": 50,
        "procedure": [
            "Establish baseline performance with full system",
            "Remove one component at a time",
            "Measure performance after each removal",
            "Compare delta against baseline",
            "Rank components by impact",
        ],
        "success_criteria": "Ablation reveals component contribution > 5%",
    },
}

_LLM_DESIGN_PROMPT = """You are an experiment designer. Given a research hypothesis, design a controlled experiment.

Hypothesis: {title}
Description: {description}
Variables: {variables}
Expected outcome: {expected_outcome}

Return a JSON object with these keys:
- experiment_type: str
- controlled_vars: dict of variables held constant
- independent_var: str (what you change)
- dependent_var: str (what you measure)
- sample_size: int
- procedure: list of step strings
- success_criteria: str

Only return valid JSON, no other text."""


def _guess_template(hypothesis: Hypothesis) -> str:
    desc_lower = (hypothesis.description + " " + hypothesis.title).lower()
    if any(w in desc_lower for w in ("benchmark", "throughput", "latency", "performance")):
        return "benchmark"
    if any(w in desc_lower for w in ("train", "learn", "model", "nn", "network", "accuracy")):
        return "ml_train"
    if any(w in desc_lower for w in ("ablat", "remove", "component", "module")):
        return "ablation"
    return "statistical_test"


def _default_design_model() -> str:
    """VECTOR's own routed reasoning model, not the upstream project's
    unmodified 'llama3.2' default (never pulled in this VECTOR install)."""
    try:
        from core.config import CONFIG
        return CONFIG["models"]["reasoning"]
    except Exception:
        return "vector-reasoning"


class ExperimentDesigner:
    def __init__(self, ollama_base_url: str = "http://localhost:11434", model: str | None = None):
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.model = model or _default_design_model()
        self._jinja_env: Optional[object] = None

    def _load_jinja(self) -> Optional[object]:
        if self._jinja_env is not None:
            return self._jinja_env
        try:
            from jinja2 import Environment, FileSystemLoader

            loader = FileSystemLoader(str(TEMPLATES_DIR))
            self._jinja_env = Environment(loader=loader)
        except ImportError:
            logger.warning("jinja2 not available — skipping template rendering")
            self._jinja_env = None
        return self._jinja_env

    def _llm_design(self, hypothesis: Hypothesis) -> Optional[ExperimentDesign]:
        if os.environ.get("VECTOR_RESEARCH_LLM_DESIGN") != "1":
            logger.info("LLM experiment design disabled; using deterministic rule-based design")
            return None

        try:
            import httpx

            prompt = _LLM_DESIGN_PROMPT.format(
                title=hypothesis.title,
                description=hypothesis.description,
                variables=json.dumps(hypothesis.variables, indent=2),
                expected_outcome=hypothesis.expected_outcome,
            )
            resp = httpx.post(
                f"{self.ollama_base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                # Measured cold-load alone (model evicted, OLLAMA_KEEP_ALIVE
                # expired/swapped) at ~58s for a 9.3GB model on this hardware
                # — a 60s timeout was failing on cold start, not on inference.
                # 120s gives real margin for cold load + actual inference.
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("response", "")
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                text = text.rsplit("```", 1)[0]
            parsed = json.loads(text)
            return ExperimentDesign(
                hypothesis_id=hypothesis.id,
                experiment_type=parsed.get("experiment_type", "statistical_test"),
                controlled_vars=parsed.get("controlled_vars", {}),
                independent_var=parsed.get("independent_var", ""),
                dependent_var=parsed.get("dependent_var", ""),
                sample_size=parsed.get("sample_size", 30),
                procedure=parsed.get("procedure", []),
                success_criteria=parsed.get("success_criteria", ""),
                design_source="llm",
            )
        except Exception as exc:
            logger.warning("LLM design failed: {}", exc)
            return None

    def _rule_design(self, hypothesis: Hypothesis, template_name: str) -> ExperimentDesign:
        tmpl = _RULE_TEMPLATES.get(template_name, _RULE_TEMPLATES["statistical_test"]).copy()
        return ExperimentDesign(
            design_source="rule_based",
            hypothesis_id=hypothesis.id,
            experiment_type=tmpl["experiment_type"],
            controlled_vars=dict(tmpl["controlled_vars"]),
            independent_var=tmpl["independent_var"],
            dependent_var=tmpl["dependent_var"],
            sample_size=tmpl["sample_size"],
            procedure=list(tmpl["procedure"]),
            success_criteria=tmpl["success_criteria"],
        )

    def design(
        self,
        hypothesis: Hypothesis,
        template: Optional[str] = None,
    ) -> ExperimentDesign:
        if template is None:
            template = _guess_template(hypothesis)

        logger.info("Designing experiment for hypothesis '{}' using '{}' template", hypothesis.id, template)

        design = self._llm_design(hypothesis)
        if design is not None:
            return design

        logger.info("Falling back to rule-based design for template '{}'", template)
        return self._rule_design(hypothesis, template)

    def render_template(self, template_name: str, **kwargs) -> Optional[str]:
        env = self._load_jinja()
        if env is None:
            return None
        try:
            tmpl = env.get_template(template_name)
            return tmpl.render(**kwargs)
        except Exception as exc:
            logger.error("Template render failed: {}", exc)
            return None

    def validate_design(self, design: ExperimentDesign) -> list[str]:
        errors: list[str] = []
        if not design.experiment_type:
            errors.append("experiment_type is required")
        if not design.hypothesis_id:
            errors.append("hypothesis_id is required")
        if design.sample_size < 2:
            errors.append(f"sample_size must be >= 2, got {design.sample_size}")
        if not design.procedure:
            errors.append("procedure must have at least one step")
        if not design.independent_var:
            errors.append("independent_var is required")
        if not design.dependent_var:
            errors.append("dependent_var is required")
        return errors

    def generate_script(self, design: ExperimentDesign) -> Optional[str]:
        template_name = _TEMPLATE_MAP.get(design.experiment_type)
        if template_name is None:
            logger.warning("No template for experiment type '{}'", design.experiment_type)
            return None
        kwargs = {
            "experiment_name": design.hypothesis_id,
            "experiment_type": design.experiment_type,
            "metrics": design.dependent_var.split("_") if design.dependent_var else [],
            "iterations": max(1, design.sample_size // 10),
            "timeout_seconds": 300,
            "model_type": design.independent_var,
            "dataset_path": "",
            "hyperparameters": design.controlled_vars,
            "epochs": design.controlled_vars.get("epochs", 10),
            "batch_size": design.controlled_vars.get("batch_size", 32),
            "test_type": design.controlled_vars.get("test_type", "two_tailed"),
            "sample_size": design.sample_size,
            "effect_size": 0.5,
            "alpha": design.controlled_vars.get("alpha", 0.05),
            "baseline_config": {"default": 1.0},
            "ablation_configs": [{"label": "component_a", "value": 0.0}],
            "metric": design.dependent_var.split("_")[0] if design.dependent_var else "accuracy",
        }
        return self.render_template(template_name, **kwargs)

    def _identify_variables(self, hypothesis: Hypothesis) -> dict[str, list[str]]:
        text = f"{hypothesis.title} {hypothesis.description}"
        iv_patterns = [
            r"\b(effect|impact|influence|role|relationship)\s+of\s+(\w+)",
            r"\b(comparing|between|vs\.?|versus)\s+(\w+)",
            r"\b(\w+)\s+(affects|influences|impacts|changes)",
        ]
        dv_patterns = [
            r"\b(on|upon)\s+(\w+)",
            r"\b(measured|observed|recorded)\s+(by|as|using)\s+(\w+)",
            r"\b(\w+)\s+(rate|score|time|accuracy|loss)",
        ]
        independent_vars: list[str] = []
        dependent_vars: list[str] = []
        for pattern in iv_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                var = m[-1].strip().lower()
                if var and var not in ("the", "a", "an", "and", "or", "of", "to", "in", "for"):
                    independent_vars.append(var)
        for pattern in dv_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                var = m[-1].strip().lower()
                if var and var not in ("the", "a", "an", "and", "or", "of", "to", "in", "for"):
                    dependent_vars.append(var)
        return {
            "independent": list(dict.fromkeys(independent_vars)) or ["treatment"],
            "dependent": list(dict.fromkeys(dependent_vars)) or ["outcome"],
        }
