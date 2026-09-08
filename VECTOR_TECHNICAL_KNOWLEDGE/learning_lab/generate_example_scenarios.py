"""One-off generator for the example `scenarios/*.json` fixtures referenced
in 78_DIGITAL_TWIN_LAB.md. Re-run any time to refresh them — each is
produced by `replay.record()`, so the saved "expected" fingerprint is
always a REAL DigitalTwin output, never hand-typed."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario import Scenario, CandidateSpec, CounterfactualRejectionSpec, PolicyUpdateSpec
from replay import record

OUT = Path(__file__).resolve().parent / "scenarios"
OUT.mkdir(exist_ok=True)

# 001 — real production candidate generation from the real seeded goals
record(Scenario(label="auto_seeded_goals_baseline", candidates="auto"),
       OUT / "scenario_001_auto_seeded_goals.json")

# 002 — a deliberately close two-candidate race (used by level4_experiment.py
# and scorecard.py's Level-4 check)
record(Scenario(label="close_race", candidates=[
    CandidateSpec(action_type="search_web", params={"q": "l4t"}, confidence=0.60, urgency=0.5),
    CandidateSpec(action_type="check_calendar", params={}, confidence=0.62, urgency=0.5),
]), OUT / "scenario_002_close_race.json")

# 003 — counterfactual veto in action
record(Scenario(label="counterfactual_veto_demo", candidates=[
    CandidateSpec(action_type="delete_logs", params={"target": "all"}, confidence=0.9, urgency=0.5),
], counterfactual_rejections=[
    CounterfactualRejectionSpec(proposal='delete_logs {"target": "all"}',
                                 reason="Too destructive — irreversible"),
]), OUT / "scenario_003_counterfactual_veto.json")

# 004 — policy-influenced decision (search_web already has a strong reward history)
record(Scenario(label="policy_influenced", candidates=[
    CandidateSpec(action_type="search_web", params={"q": "policy_demo"}, confidence=0.5, urgency=0.5),
    CandidateSpec(action_type="check_calendar", params={}, confidence=0.5, urgency=0.5),
], policy_updates=[
    PolicyUpdateSpec("search_web", {"q": "policy_demo"}, reward=0.95),
]), OUT / "scenario_004_policy_influenced.json")

print(f"wrote {len(list(OUT.glob('scenario_*.json')))} scenario fixtures to {OUT}")
