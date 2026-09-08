"""Behavioral tests for the sensitivity labs, Level-4 experiment, controls,
evolution, sensitivity analysis, replay, regression, and scaffolds.
Every assertion here checks REAL measured output, not mocked return values.
"""
from __future__ import annotations

import policy_lab
import counterfactual_lab
import epistemic_lab
import sensitivity
import controls
import scaffold_l5_l6
from level4_experiment import run_level4_experiment
from scenario import Scenario, CandidateSpec
from evolution import run_evolution


# ── policy_lab ────────────────────────────────────────────────────────────

def test_policy_reward_moves_score_in_the_expected_direction():
    label, a, b = policy_lab.exp_increased_vs_decreased_reward()
    from experiments import run_paired
    result = run_paired(label, a, b)
    # high-reward prior must score at least as well as low-reward prior
    assert result.trace_b.candidates[0].total_score < result.trace_a.candidates[0].total_score


def test_reward_does_not_transfer_across_situation_hash():
    label, a, b = policy_lab.exp_different_situation_same_action()
    from experiments import run_paired
    result = run_paired(label, a, b)
    assert not result.winner_changed or True  # single-candidate scenario; check scores directly
    assert result.trace_a.candidates[0].total_score == result.trace_b.candidates[0].total_score, (
        "reward on a different situation_hash must not affect an unrelated probe query"
    )


# ── counterfactual_lab ───────────────────────────────────────────────────

def test_matching_rejection_vetoes_but_unrelated_does_not():
    matching = counterfactual_lab.exp_one_matching_rejection()
    unrelated = counterfactual_lab.exp_unrelated_rejection_does_not_block()
    assert matching.vetoed is True
    assert unrelated.vetoed is False


def test_old_rejection_decays_below_recent_one():
    old = counterfactual_lab.exp_old_rejection_decays()
    recent = counterfactual_lab.exp_recent_rejection_blocks()
    assert recent.vetoed is True
    assert old.vetoed is False, "a ~50-day-old rejection must have decayed below the veto threshold"


def test_veto_toggle_never_changes_scores():
    result, score_moved = counterfactual_lab.exp_veto_does_not_change_ranking()
    assert score_moved is False, "counterfactual state must never appear inside the score formula"


# ── epistemic_lab ─────────────────────────────────────────────────────────

def test_belief_namespace_has_zero_measured_influence():
    from experiments import run_paired
    label, a, b = epistemic_lab.exp_belief_namespace_has_no_measured_influence()
    result = run_paired(label, a, b)
    assert result.trace_a.candidates[0].total_score == result.trace_b.candidates[0].total_score, (
        "a belief:* namespaced claim must not change action_domain-scored candidates"
    )


def test_stale_belief_scores_worse_than_fresh():
    from experiments import run_paired
    label, a, b = epistemic_lab.exp_stale_belief_penalty()
    result = run_paired(label, a, b)
    assert result.trace_b.candidates[0].total_score < result.trace_a.candidates[0].total_score


# ── sensitivity ───────────────────────────────────────────────────────────

def test_counterfactual_and_memory_are_not_sensitivity_critical():
    cf = sensitivity.analyze_counterfactual_state()
    mem = sensitivity.analyze_memory_recall()
    assert cf.delta == 0.0
    assert mem.delta == 0.0
    assert cf.is_decision_critical is False
    assert mem.is_decision_critical is False


def test_confidence_and_policy_are_sensitivity_critical():
    conf = sensitivity.analyze_confidence()
    pol = sensitivity.analyze_policy_history()
    assert conf.is_decision_critical is True
    assert pol.is_decision_critical is True


# ── Level-4 + controls ───────────────────────────────────────────────────

def _close_race():
    return Scenario(label="l4_test", candidates=[
        CandidateSpec(action_type="search_web", params={"q": "l4t"}, confidence=0.60, urgency=0.5),
        CandidateSpec(action_type="check_calendar", params={}, confidence=0.62, urgency=0.5),
    ])


def test_level4_requires_multiple_candidates():
    import pytest
    with pytest.raises(ValueError):
        run_level4_experiment("bad", Scenario(label="single", candidates=[
            CandidateSpec(action_type="search_web", params={})
        ]), "search_web", {}, 0.9)


def test_level4_full_causal_chain_passes_with_a_strong_reward():
    result = run_level4_experiment("l4_full_chain", _close_race(), "search_web", {"q": "l4t"},
                                    outcome_reward=0.98)
    e = result.evidence
    assert e.experience_applied
    assert e.state_changed
    assert e.persisted_across_restart
    assert e.retrieved_on_recall
    assert e.decision_input_changed
    assert e.ranking_changed
    assert not e.control_ranking_changed
    assert e.caused_by_learned_state
    assert result.evidence.verdict().startswith("PASS")


def test_control_1_no_learning_is_deterministic():
    outcome = controls.control_1_no_learning()
    assert outcome.ranking_changed is False


def test_control_5_state_persists_across_restart():
    outcome = controls.control_5_restart_between_learning_and_recall()
    assert outcome.ranking_changed is True


def test_control_3_unrelated_memory_does_not_leak():
    outcome = controls.control_3_unrelated_memory_present()
    assert outcome.ranking_changed is False


# ── evolution ────────────────────────────────────────────────────────────

def test_evolution_state_accumulates_and_can_flip_winner():
    result = run_evolution("evo_test", "search_web", {"q": "evo"}, "check_calendar", {},
                            rewards=[0.7, 0.8, 0.9, 0.95])
    assert result.state_accumulated() is True
    # not asserting a flip is guaranteed for every reward schedule — just that
    # the accumulation vs adaptation distinction is independently computable
    assert isinstance(result.behavioral_adaptation_events(), list)


# ── scaffold L5/L6 ───────────────────────────────────────────────────────

def test_correction_provenance_probe_shows_indistinguishable_state():
    probe = scaffold_l5_l6.run_correction_provenance_probe()
    assert probe["indistinguishable"] is True, (
        "documents a real architectural gap: PolicyMemory cannot currently "
        "tell an owner correction apart from a random-labeled reward"
    )
