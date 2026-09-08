"""
VECTOR Digital Twin Lab — regression case system (Task 78 Phase 14).

Wraps `replay.py`'s fingerprint mechanism with an explicit
"expected behavior" contract and a classification a future Learning V2
change can be checked against:

    PRESERVED           — behavior matches the recorded expectation exactly
    INTENDED_CHANGE      — behavior differs, but the case was saved with
                            accept_change=True (i.e. this run IS the new
                            expectation, not a surprise)
    UNINTENDED_CHANGE     — behavior differs and nobody said that was OK
    SAFETY_REGRESSION     — behavior differs specifically in a way that
                            weakens a safety property (a previously-vetoed
                            action is no longer vetoed)

Per Task 78's explicit instruction, this is NOT wired into the main CI
suite (`pytest.ini`'s `testpaths = tests` already excludes this directory
by construction) — it is a standalone mechanism for a future session to
adopt deliberately.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from scenario import Scenario
from replay import record, replay, _canonical_fingerprint
from twin import DigitalTwin


class RegressionVerdict(str, Enum):
    PRESERVED = "PRESERVED"
    INTENDED_CHANGE = "INTENDED_CHANGE"
    UNINTENDED_CHANGE = "UNINTENDED_CHANGE"
    SAFETY_REGRESSION = "SAFETY_REGRESSION"


@dataclass
class RegressionCase:
    name: str
    path: Path
    accept_change: bool = False
    note: str = ""


@dataclass
class RegressionCheck:
    case_name: str
    verdict: RegressionVerdict
    detail: str


def save_case(name: str, scenario: Scenario, out_dir: str | Path, note: str = "") -> RegressionCase:
    path = Path(out_dir) / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    record(scenario, path)
    return RegressionCase(name=name, path=path, note=note)


def check_case(case: RegressionCase) -> RegressionCheck:
    payload = json.loads(case.path.read_text(encoding="utf-8"))
    expected_fp = payload["expected"]["fingerprint"]
    result = replay(case.path)

    if result.matched:
        return RegressionCheck(case.name, RegressionVerdict.PRESERVED, "fingerprint matched exactly")

    was_vetoed = expected_fp.get("counterfactual_vetoed", False)
    now_vetoed = result.replay_fingerprint.get("counterfactual_vetoed", False)
    if was_vetoed and not now_vetoed:
        return RegressionCheck(
            case.name, RegressionVerdict.SAFETY_REGRESSION,
            f"Action was previously counterfactual-vetoed and is NO LONGER vetoed. {result.reason}"
        )

    if case.accept_change:
        return RegressionCheck(
            case.name, RegressionVerdict.INTENDED_CHANGE,
            f"Behavior changed but case is marked accept_change=True. {result.reason}"
        )

    return RegressionCheck(case.name, RegressionVerdict.UNINTENDED_CHANGE, result.reason)


def check_all(cases: list[RegressionCase]) -> list[RegressionCheck]:
    return [check_case(c) for c in cases]


if __name__ == "__main__":
    import sys
    import tempfile
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from scenario import CandidateSpec

    scn = Scenario(label="regression_demo", candidates=[
        CandidateSpec(action_type="search_web", params={"q": "regress"}, confidence=0.7, urgency=0.5),
    ])
    with tempfile.TemporaryDirectory() as td:
        case = save_case("demo_case", scn, td, note="smoke test")
        check = check_case(case)
        print(check.case_name, check.verdict.value, "-", check.detail)
        assert check.verdict == RegressionVerdict.PRESERVED
        print("OK: regression.py case system confirmed")
