"""
R11 — Native Goal Strategy Candidate Generation: Digital Twin Lab confirmation.

Second, independently-designed piece of evidence for R11's fix, using the
pre-existing Task-78 Digital Twin Lab machinery (isolation.py / scenario.py /
twin.py) rather than tests/test_r11_*.py's own directly-constructed pattern —
a genuinely different harness reaching the same conclusion is stronger
evidence than one harness alone.

`auto_candidates_from_goals()` (twin.py) was updated by R11 to match the
real, fixed `core.brain.goal_system.GoalSystem.generate_immediate_actions()`
(see twin.py's own updated module comment for the full history — it used to
deliberately reproduce the OLD dead `_TAG_TO_ACTION` lookup, because the
twin's job is to reproduce REAL production behavior, dead code included;
now that the dead code is fixed in production, reproducing the fix is the
same principle applied to the new reality).
"""
from isolation import IsolatedVectorEnv
from scenario import GoalSpec
from twin import auto_candidates_from_goals, build_isolated_engine


def test_auto_candidates_from_goals_now_yields_real_native_diversity():
    """A GoalSpec matching the REAL g_daily_commit goal's own tags
    (["git", "habit", "coding"]) must now naturally produce >= 2 distinct
    real CandidateSpecs via the REAL, unmodified
    GoalSystem.generate_immediate_actions() -- through the lab's own
    isolated, unmodified-elsewhere GoalSystem instance, not a reimplementation."""
    with IsolatedVectorEnv() as env:
        engine = build_isolated_engine(env)
        engine._goals._goals = [{
            "id": "g_lab_daily_commit", "title": "Commit code every day",
            "horizon": "SHORT", "priority": 7, "status": "active",
            "progress": 0.0, "tags": ["git", "habit", "coding"],
        }]
        engine._goals._persist()

        specs = auto_candidates_from_goals(engine._goals)

        distinct_types = {s.action_type for s in specs}
        assert distinct_types == {"git_status", "code_task"}, (
            f"expected the real production path to naturally propose both a "
            f"git_status and a code_task strategy for this goal's real tags, "
            f"got {distinct_types}"
        )


def test_auto_mode_scenario_end_to_end_through_the_real_twin():
    """The full Scenario -> DigitalTwin -> DecisionTrace path, with
    `candidates="auto"` (the lab's own default, meaning "call the REAL
    generate_immediate_actions()"), against a goal engineered to have real
    tag-derived diversity. Proves R11's fix is visible end-to-end through
    the pre-existing lab's own primary entry point, not just through the
    one adapter function tested above."""
    from scenario import Scenario
    from twin import DigitalTwin

    twin = DigitalTwin()
    scenario = Scenario(
        label="r11_native_diversity_check",
        goals=[GoalSpec(
            id="g_lab_daily_commit_2", title="Commit code every day",
            horizon="SHORT", priority=7, tags=["git", "coding"],
        )],
        candidates="auto",
        apply_counterfactual_veto=False,
    )
    trace = twin.run(scenario)

    assert trace.error is None, f"twin run failed: {trace.error}"
    generated_types = {c["action_type"] for c in trace.generated_candidates}
    assert generated_types == {"git_status", "code_task"}
    assert trace.selected_action in generated_types
    assert len(trace.candidates) == 2


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
    test_auto_candidates_from_goals_now_yields_real_native_diversity()
    test_auto_mode_scenario_end_to_end_through_the_real_twin()
    print("✅ test_r11_native_diversity OK")
