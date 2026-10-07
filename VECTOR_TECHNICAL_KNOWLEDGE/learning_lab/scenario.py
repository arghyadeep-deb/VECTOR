"""
VECTOR Digital Twin Lab — deterministic scenario model.

A Scenario is a fully-specified, JSON-serializable description of everything
the Digital Twin needs to reproduce ONE decision deterministically:

    situation -> goals -> candidates -> memory/policy/counterfactual/epistemic
    state -> DecisionEngine -> DecisionTrace

Every field is optional and has an explicit, documented default so a minimal
Scenario (just a label) still runs — it falls back to VECTOR's REAL seeded
goals (`core.brain.goal_system.PRESEEDED_GOALS`) and REAL
`generate_immediate_actions()` candidate generation, which is what makes the
lab reproduce actual production behavior rather than a hand-picked toy case.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Literal


def atomic_write_text(path: Path, text: str) -> None:
    """Durably replace a text artifact without exposing a partial file."""
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


@dataclass
class CandidateSpec:
    """Deterministic recipe for one `core.loop.decision_engine.Candidate`.
    Field names/defaults mirror the real `Candidate` dataclass exactly."""
    action_type: str
    params: dict = field(default_factory=dict)
    goal_ids: list[str] = field(default_factory=list)
    confidence: float = 0.5
    urgency: float = 0.5
    timing_score: float = 1.0
    estimated_cost_inr: float = 0.0
    source: str = "system"


@dataclass
class PolicyUpdateSpec:
    """One `PolicyMemory.update_from_outcome()` call to replay BEFORE the
    decision is scored, i.e. a piece of "prior experience" the situation
    walks in with. `action_type`+`params` are hashed the same way
    `DecisionEngine._make_situation_hash()` hashes a real Candidate, so a
    PolicyUpdateSpec with the same action_type/params as a CandidateSpec in
    the same scenario is guaranteed to land on that candidate's policy row."""
    action_type: str
    params: dict = field(default_factory=dict)
    reward: float = 0.5
    note: str = ""


@dataclass
class CounterfactualRejectionSpec:
    """One `CounterfactualMemory.record_rejection()` call to replay before
    scoring. `created_at_days_ago` lets a test simulate an OLD rejection
    (staleness decay, T4) without waiting real days — it directly rewrites
    the row's `created_at` after insertion (see twin.py)."""
    proposal: str
    reason: str
    decision_id: str = "seed"
    context: dict = field(default_factory=dict)
    created_at_days_ago: float = 0.0


@dataclass
class EpistemicBeliefSpec:
    """One `EpistemicTracker.update_belief()` call to replay before scoring.
    `claim_id` must be `action_domain:<full_action_type>` to actually
    influence `DecisionEngine._epistemic_penalty()`
    — see `epistemic_lab.py` for the experiment that PROVES a `belief:*`-
    namespaced claim, by contrast, has zero measured influence on scoring."""
    claim_id: str
    value: str
    confidence: float
    source: str = "twin_lab"
    ttl_hours: int = 72
    age_hours_override: float | None = None  # simulate an old/stale belief


@dataclass
class GoalSpec:
    """Deterministic goal row — same shape as `PRESEEDED_GOALS` entries."""
    id: str
    title: str
    horizon: Literal["SHORT", "MID", "LONG"]
    priority: int = 5
    status: str = "active"
    progress: float = 0.0
    tags: list[str] = field(default_factory=list)


@dataclass
class Scenario:
    """A complete, deterministic, replayable decision scenario.

    `candidates="auto"` (the default) means: seed goals into a real
    GoalSystem, call the REAL `generate_immediate_actions()`, and score
    whatever it actually returns — this is how the lab reproduces genuine
    production candidate-generation behavior (including the historical
    analyze_progress dominance) rather than hand-picking a "fair" candidate
    set.
    """
    label: str
    situation: dict = field(default_factory=dict)
    goals: list[GoalSpec] | None = None            # None => real PRESEEDED_GOALS
    candidates: list[CandidateSpec] | Literal["auto"] = "auto"
    policy_updates: list[PolicyUpdateSpec] = field(default_factory=list)
    counterfactual_rejections: list[CounterfactualRejectionSpec] = field(default_factory=list)
    epistemic_beliefs: list[EpistemicBeliefSpec] = field(default_factory=list)
    apply_counterfactual_veto: bool = True
    metadata: dict = field(default_factory=dict)

    # ---- (de)serialization -------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Scenario":
        d = dict(d)
        if d.get("goals") is not None:
            d["goals"] = [GoalSpec(**g) for g in d["goals"]]
        if d.get("candidates") not in (None, "auto"):
            d["candidates"] = [CandidateSpec(**c) for c in d["candidates"]]
        d["policy_updates"] = [PolicyUpdateSpec(**p) for p in d.get("policy_updates", [])]
        d["counterfactual_rejections"] = [
            CounterfactualRejectionSpec(**c) for c in d.get("counterfactual_rejections", [])
        ]
        d["epistemic_beliefs"] = [
            EpistemicBeliefSpec(**e) for e in d.get("epistemic_beliefs", [])
        ]
        return cls(**d)

    def to_json(self, path: str | Path | None = None) -> str:
        text = json.dumps(self.to_dict(), indent=2, sort_keys=False, default=str)
        if path is not None:
            atomic_write_text(Path(path), text)
        return text

    @classmethod
    def from_json(cls, path: str | Path) -> "Scenario":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def clone(self, **overrides: Any) -> "Scenario":
        """Return a deep-ish copy with `overrides` applied — the primitive
        for every paired-experiment ("baseline + exactly ONE changed
        variable") in the lab. Uses the JSON round-trip so nested
        dataclasses are never accidentally shared by reference between the
        two scenario objects."""
        base = Scenario.from_dict(json.loads(self.to_json()))
        for k, v in overrides.items():
            setattr(base, k, v)
        return base
