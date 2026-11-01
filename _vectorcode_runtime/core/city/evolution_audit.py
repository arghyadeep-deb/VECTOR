"""Clean-room evolution audit schemas for prompt/policy changes."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

__all__ = ["EvolutionEvent", "EvolutionStatus", "StrategyGene"]


class EvolutionStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


@dataclass(frozen=True)
class StrategyGene:
    gene_id: str
    title: str
    target: str
    rule: str
    evidence_refs: tuple[str, ...]
    rollback_note: str


@dataclass
class EvolutionEvent:
    event_id: str
    gene: StrategyGene
    author: str
    status: EvolutionStatus = EvolutionStatus.PROPOSED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    review_note: str = ""

    def approve(self, reviewer: str, note: str = "") -> None:
        self.status = EvolutionStatus.APPROVED
        self.review_note = f"{reviewer}: {note}".strip()

    def apply(self) -> None:
        if self.status != EvolutionStatus.APPROVED:
            raise ValueError("evolution event must be approved before apply")
        self.status = EvolutionStatus.APPLIED
