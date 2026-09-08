"""End-to-end scorecard test — the whole lab wired together, one run."""
from __future__ import annotations

from scorecard import run_scorecard, Verdict


def test_scorecard_runs_all_eight_levels_without_crashing():
    results = run_scorecard()
    assert len(results) == 8
    assert [r.level for r in results] == list(range(8))


def test_scorecard_levels_0_through_4_pass_on_real_production_logic():
    results = run_scorecard()
    by_level = {r.level: r for r in results}
    for lvl in (0, 1, 2, 3, 4):
        assert by_level[lvl].verdict == Verdict.PASS, (
            f"Level {lvl} ({by_level[lvl].name}) expected PASS, got "
            f"{by_level[lvl].verdict}: {by_level[lvl].evidence}"
        )


def test_scorecard_level_6_and_7_are_honestly_not_implemented():
    results = run_scorecard()
    by_level = {r.level: r for r in results}
    assert by_level[6].verdict == Verdict.NOT_IMPLEMENTED
    assert by_level[7].verdict == Verdict.NOT_IMPLEMENTED
