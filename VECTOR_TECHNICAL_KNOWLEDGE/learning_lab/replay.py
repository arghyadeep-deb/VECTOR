"""
VECTOR Digital Twin Lab — reproducible scenario replay (Task 78 Phase 13).

A recorded scenario file contains the Scenario itself PLUS the exact
decision outcome it produced at record time, so a later replay can prove
(or disprove) determinism rather than merely re-running and hoping the
result "looks similar".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from scenario import Scenario, atomic_write_text
from trace import DecisionTrace
from twin import DigitalTwin


def _canonical_fingerprint(trace: DecisionTrace) -> dict:
    """The deterministic subset of a trace — excludes run_id (random per
    run by design) and anything timestamp-derived."""
    return {
        "selected_action": trace.selected_action,
        "selected_params": trace.selected_params,
        "ranking": trace.ranking(),
        "candidate_scores": {c.action_type: c.total_score for c in trace.candidates},
        "counterfactual_vetoed": trace.counterfactual_vetoed,
    }


def _hash_fingerprint(fp: dict) -> str:
    return hashlib.sha256(json.dumps(fp, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class ReplayResult:
    matched: bool
    reason: str
    recorded_fingerprint: dict
    replay_fingerprint: dict


def record(scenario: Scenario, path: str | Path, twin: DigitalTwin | None = None) -> DecisionTrace:
    """Run `scenario` once, and save both the scenario and its resulting
    fingerprint to `path` — this IS the saved-scenario format
    (`scenario_001.json` etc.)."""
    twin = twin or DigitalTwin()
    trace = twin.run(scenario)
    if trace.error:
        raise RuntimeError(f"cannot record a failed twin run: {trace.error}")
    fp = _canonical_fingerprint(trace)
    payload = {
        "scenario": scenario.to_dict(),
        "expected": {"fingerprint": fp, "fingerprint_hash": _hash_fingerprint(fp)},
    }
    atomic_write_text(Path(path), json.dumps(payload, indent=2, default=str))
    return trace


def replay(path: str | Path, twin: DigitalTwin | None = None) -> ReplayResult:
    """Load a recorded scenario, re-run it fresh, and report exactly
    whether — and if not, WHY not — it reproduces the recorded fingerprint."""
    twin = twin or DigitalTwin()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    scenario = Scenario.from_dict(payload["scenario"])
    expected_fp = payload["expected"]["fingerprint"]
    expected_hash = payload["expected"]["fingerprint_hash"]

    if _hash_fingerprint(expected_fp) != expected_hash:
        return ReplayResult(
            False,
            "stored fingerprint hash does not match the stored fingerprint",
            expected_fp,
            {},
        )

    trace = twin.run(scenario)
    if trace.error:
        return ReplayResult(False, f"twin replay failed: {trace.error}", expected_fp, {})
    actual_fp = _canonical_fingerprint(trace)
    actual_hash = _hash_fingerprint(actual_fp)

    if actual_hash == expected_hash:
        return ReplayResult(True, "fingerprint matched exactly", expected_fp, actual_fp)

    reasons = []
    if expected_fp["selected_action"] != actual_fp["selected_action"]:
        reasons.append(
            f"selected_action changed: {expected_fp['selected_action']!r} -> {actual_fp['selected_action']!r}"
        )
    if expected_fp["ranking"] != actual_fp["ranking"]:
        reasons.append(f"ranking changed: {expected_fp['ranking']} -> {actual_fp['ranking']}")
    for action, old_score in expected_fp["candidate_scores"].items():
        new_score = actual_fp["candidate_scores"].get(action)
        if new_score is None:
            reasons.append(f"candidate {action!r} missing on replay (was {old_score})")
        elif new_score != old_score:
            reasons.append(f"{action} score changed: {old_score} -> {new_score}")
    for action in actual_fp["candidate_scores"]:
        if action not in expected_fp["candidate_scores"]:
            reasons.append(f"candidate {action!r} appeared on replay but was not in the recording")
    if expected_fp["counterfactual_vetoed"] != actual_fp["counterfactual_vetoed"]:
        reasons.append(
            f"counterfactual_vetoed changed: {expected_fp['counterfactual_vetoed']} -> "
            f"{actual_fp['counterfactual_vetoed']}"
        )
    if not reasons:
        reasons.append("hash mismatch with no field-level difference detected — investigate fingerprint logic")

    return ReplayResult(False, "; ".join(reasons), expected_fp, actual_fp)


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[2]))
    sys.path.insert(0, str(_P(__file__).resolve().parent))
    from scenario import CandidateSpec

    scn = Scenario(label="replay_demo", candidates=[
        CandidateSpec(action_type="search_web", params={"q": "replay"}, confidence=0.7, urgency=0.5),
        CandidateSpec(action_type="check_calendar", params={}, confidence=0.5, urgency=0.5),
    ])
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "scenario_demo.json"
        record(scn, p)
        result = replay(p)
        print("matched:", result.matched, "-", result.reason)
        assert result.matched, "a freshly-recorded, unmodified scenario MUST replay deterministically"
        print("OK: replay.py deterministic round-trip confirmed")
