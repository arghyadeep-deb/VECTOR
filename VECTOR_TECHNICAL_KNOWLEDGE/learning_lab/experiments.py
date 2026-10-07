"""
VECTOR Digital Twin Lab — paired counterfactual experiments (Task 78 Phase 5).

The single reusable primitive every sensitivity lab (policy/counterfactual/
epistemic) and the Level-4 experiment builds on: run baseline scenario A,
run scenario B (A + exactly one changed variable), and produce an honest,
falsifiable comparison — never inferring influence that isn't actually
measured in the two traces.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Real

from scenario import Scenario
from trace import DecisionTrace
from twin import DigitalTwin


@dataclass
class ScoreComponentDelta:
    action_type: str
    factor: str
    value_a: float | None
    value_b: float | None
    delta: float | None


@dataclass
class ComparisonResult:
    label: str
    trace_a: DecisionTrace
    trace_b: DecisionTrace
    ranking_a: list[str]
    ranking_b: list[str]
    winner_a: str | None
    winner_b: str | None
    winner_changed: bool
    score_deltas: list[ScoreComponentDelta] = field(default_factory=list)
    common_action_types: list[str] = field(default_factory=list)
    a_only_actions: list[str] = field(default_factory=list)
    b_only_actions: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """The exact honest-null-result contract Task 78 requires: never
        claim influence the data doesn't show."""
        lines = [f"PAIRED EXPERIMENT: {self.label}"]
        lines.append(f"  winner A = {self.winner_a!r}   winner B = {self.winner_b!r}")
        if self.winner_changed:
            lines.append("  WINNER CHANGED.")
        else:
            lines.append("  Winner did NOT change.")
        moved = [d for d in self.score_deltas if d.delta is not None and abs(d.delta) > 1e-9]
        if not moved and not self.winner_changed:
            lines.append(
                "  No score component measurably changed for any shared candidate. "
                "This variable had NO measured behavioral influence in this scenario."
            )
        else:
            for d in moved:
                lines.append(
                    f"  [{d.action_type}] {d.factor}: {d.value_a} -> {d.value_b} (Δ={d.delta:+.4f})"
                )
        if self.a_only_actions or self.b_only_actions:
            lines.append(f"  candidates only in A: {self.a_only_actions}")
            lines.append(f"  candidates only in B: {self.b_only_actions}")
        return "\n".join(lines)


def _components_by_action(trace: DecisionTrace) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for c in trace.candidates:
        out[c.action_type] = {
            comp["factor"]: float(comp["value"])
            for comp in c.score_components
            if isinstance(comp.get("value"), Real) and not isinstance(comp.get("value"), bool)
        }
        out[c.action_type]["total_score"] = c.total_score
    return out


def run_paired(label: str, scenario_a: Scenario, scenario_b: Scenario,
                twin: DigitalTwin | None = None) -> ComparisonResult:
    """Run A and B in TWO INDEPENDENT isolated environments (each scenario
    is fully self-contained/deterministic — see scenario.py) and diff the
    resulting traces. Independent environments are the correct default for
    "exactly one changed variable" experiments: it guarantees B's isolated
    DB cannot have been contaminated by A's run, which is what makes the
    observed delta attributable to the declared variable and nothing else.
    (Level-4's persistence experiment, by contrast, deliberately reuses ONE
    environment across two runs — see level4_experiment.py — because
    persistence-across-restart is exactly what it needs to prove.)"""
    twin = twin or DigitalTwin()
    trace_a = twin.run(scenario_a)
    trace_b = twin.run(scenario_b)

    ranking_a = trace_a.ranking()
    ranking_b = trace_b.ranking()
    winner_a = trace_a.selected_action
    winner_b = trace_b.selected_action

    comp_a = _components_by_action(trace_a)
    comp_b = _components_by_action(trace_b)
    common = sorted(set(comp_a) & set(comp_b))
    a_only = sorted(set(comp_a) - set(comp_b))
    b_only = sorted(set(comp_b) - set(comp_a))

    deltas: list[ScoreComponentDelta] = []
    for action in common:
        factors = sorted(set(comp_a[action]) | set(comp_b[action]))
        for f in factors:
            va = comp_a[action].get(f)
            vb = comp_b[action].get(f)
            d = (vb - va) if (va is not None and vb is not None) else None
            deltas.append(ScoreComponentDelta(action, f, va, vb, d))

    result = ComparisonResult(
        label=label, trace_a=trace_a, trace_b=trace_b,
        ranking_a=ranking_a, ranking_b=ranking_b,
        winner_a=winner_a, winner_b=winner_b,
        winner_changed=(winner_a != winner_b),
        score_deltas=deltas, common_action_types=common,
        a_only_actions=a_only, b_only_actions=b_only,
    )
    trace_a.state_diff = {"compared_to": "B", "winner_changed": result.winner_changed}
    trace_b.state_diff = {"compared_to": "A", "winner_changed": result.winner_changed}
    return result
