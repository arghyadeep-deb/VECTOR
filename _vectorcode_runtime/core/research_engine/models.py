"""Core dataclasses for the spec-10 Research Lab."""

from dataclasses import dataclass, field

__all__ = [
    "AnalysisResult",
    "ExperimentDesign",
    "ExperimentResult",
    "Hypothesis",
    "ResearchReport",
]

from datetime import datetime, timezone
from typing import Optional


@dataclass
class Hypothesis:
    id: str
    title: str
    description: str
    variables: dict = field(default_factory=dict)
    expected_outcome: str = ""
    confidence: float = 0.5
    status: str = "proposed"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = ""

    def __post_init__(self) -> None:
        valid_statuses = {"proposed", "active", "tested", "rejected", "accepted"}
        if self.status not in valid_statuses:
            raise ValueError(f"status must be one of {valid_statuses}, got {self.status!r}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


@dataclass
class ExperimentDesign:
    hypothesis_id: str
    experiment_type: str
    controlled_vars: dict = field(default_factory=dict)
    independent_var: str = ""
    dependent_var: str = ""
    sample_size: int = 30
    procedure: list[str] = field(default_factory=list)
    success_criteria: str = ""
    # "llm" or "rule_based" — lets callers (and tests) tell a genuine
    # LLM-designed experiment apart from the static-template fallback, so
    # "LIVE" doesn't quietly mean "permanently degraded to filler."
    design_source: str = "unknown"


@dataclass
class ExperimentResult:
    experiment_id: str
    status: str = "pending"
    raw_data: list[dict] = field(default_factory=list)
    summary_stats: dict = field(default_factory=dict)
    plots: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class AnalysisResult:
    experiment_id: str
    statistical_tests: list[dict] = field(default_factory=list)
    significance: float = 0.0
    effect_size: float = 0.0
    interpretation: str = ""
    supports_hypothesis: bool = False


@dataclass
class ResearchReport:
    hypothesis: Optional[Hypothesis] = None
    experiment: Optional[ExperimentDesign] = None
    analysis: Optional[AnalysisResult] = None
    sections: dict = field(default_factory=dict)
    figures: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
