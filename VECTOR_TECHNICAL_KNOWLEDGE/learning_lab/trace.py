"""
VECTOR Digital Twin Lab — decision trace model.

A DecisionTrace is the structured, inspectable record of exactly one
DigitalTwin.run(scenario) call. It exists so "why did action X win?" is
answerable by reading a data structure, not by re-reading DecisionEngine's
source every time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class CandidateTrace:
    action_type: str
    params: dict
    goal_ids: list[str]
    confidence: float
    urgency: float
    timing_score: float
    estimated_cost_inr: float
    source: str
    goal_alignment: float
    policy_score: float
    total_score: float
    score_components: list[dict]     # candidate.reasoning_chain, verbatim from the REAL engine
    reasoning_steps: list[str]       # candidate.reasoning_steps, verbatim
    rejected: bool
    rejection_reason: str = ""       # populated only for the winner if counterfactual-vetoed


@dataclass
class DecisionTrace:
    run_id: str
    scenario_label: str

    # INPUT SITUATION
    situation: dict

    # ACTIVE GOALS
    active_goals: list[dict]

    # GENERATED CANDIDATES (pre-scoring, as handed to DecisionEngine)
    generated_candidates: list[dict]

    # MEMORY / POLICY / COUNTERFACTUAL / EPISTEMIC INPUTS applied before scoring
    memory_inputs: dict
    policy_inputs: list[dict]
    counterfactual_inputs: dict
    epistemic_inputs: list[dict]

    # PER-CANDIDATE SCORE COMPONENTS + FINAL SCORES + RANKING
    candidates: list[CandidateTrace]

    # SELECTED / REJECTED
    selected_action: Optional[str]
    selected_params: dict
    rejected_actions: list[str]

    # DECISION REASON — the real DecisionEngine.reasoning string, plus the
    # counterfactual-veto reason if the raw winner was blocked.
    decision_reason: str
    counterfactual_vetoed: bool
    veto_reason: str

    # STATE DIFFERENCES FROM BASELINE — populated by experiments.compare(),
    # empty for a standalone run.
    state_diff: dict = field(default_factory=dict)

    error: Optional[str] = None

    # ---- convenience -------------------------------------------------------

    def ranking(self) -> list[str]:
        return [c.action_type for c in sorted(self.candidates, key=lambda c: c.total_score, reverse=True)]

    def winner_score(self) -> Optional[float]:
        for c in self.candidates:
            if c.action_type == self.selected_action and not c.rejected:
                return c.total_score
        return None

    def score_of(self, action_type: str) -> Optional[float]:
        for c in self.candidates:
            if c.action_type == action_type:
                return c.total_score
        return None

    def explain(self) -> str:
        """Human-readable "why did action X win?" narrative built entirely
        from real DecisionEngine output — no re-derivation, no guessing."""
        lines = [f"RUN {self.run_id} — scenario '{self.scenario_label}'"]
        if self.error:
            lines.append(f"ERROR: {self.error}")
            return "\n".join(lines)
        if not self.candidates:
            lines.append("No candidates were generated.")
            return "\n".join(lines)
        lines.append(f"Candidates evaluated: {len(self.candidates)}")
        for c in sorted(self.candidates, key=lambda c: c.total_score, reverse=True):
            tag = "WINNER" if c.action_type == self.selected_action and not c.rejected else "rejected"
            lines.append(f"  [{tag:8}] {c.action_type:24} score={c.total_score:.4f}")
            for comp in c.score_components:
                value = comp["value"]
                rendered_value = f"{value:.3f}" if isinstance(value, (int, float)) else repr(value)
                lines.append(
                    f"              {comp['factor']:22} value={rendered_value} weight={comp['weight']}"
                )
        if self.counterfactual_vetoed:
            lines.append(f"COUNTERFACTUAL VETO on '{self.selected_action}': {self.veto_reason}")
        lines.append(f"Decision reason: {self.decision_reason}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: Optional[str | Path] = None) -> str:
        text = json.dumps(self.to_dict(), indent=2, sort_keys=False, default=str)
        if path is not None:
            from scenario import atomic_write_text
            atomic_write_text(Path(path), text)
        return text
