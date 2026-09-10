"""
R21 — Generalization.

Phase 1's 9 parallel read-only investigators (see
VECTOR_TECHNICAL_KNOWLEDGE/R21_R23_ORCHESTRATOR_LEDGER.md) audited every
existing VECTOR mechanism that could plausibly transfer learned knowledge
from one situation to a materially different, related one. PolicyMemory
and EpistemicTracker are exact-match by prior, deliberate, DOCUMENTED
safety decisions (R8's correction-penalty design; R16's own domain-key-
collision fix) and must not be loosened. ReasoningBank's "embedding" is a
plain SHA256 hash tiled into a vector -- no real locality, fake similarity,
explicitly rejected as a substrate. LightRAG is real but fully unwired to
any decision path (would be disproportionate new wiring for this
milestone).

`core/memory/counterfactual.py::CounterfactualMemory` is the one
mechanism that is BOTH real (genuine token-level Jaccard similarity, not
exact-hash matching) AND already production-wired (`AutonomousLoop
._act_on()`'s Gap-4 block calls `should_avoid()`/`record_rejection()` on
every real winning Candidate, before dispatch). Two independent Phase-1
investigators independently ranked it the strongest R21 substrate, and a
third (fresh, adversarial) investigator confirmed a real A->B transfer is
achievable through the real `_act_on()` path WITHOUT any real LLM call
(ThreatDetector, the real rejection source this file uses for situation
A, is pure regex pattern matching -- no cloud/local model call).

The read-only safety audit (Phase 1 Agent B, independently reconfirmed by
the fresh adversarial investigator) found a real, pre-existing gap:
`get_similar_rejections()`'s SQL query was completely unscoped (`SELECT *
FROM rejections`, zero action_type/goal filtering) -- two DIFFERENT,
UNRELATED action_types sharing a similar JSON params SHAPE could
Jaccard-match at a high score purely by structural coincidence (verified
empirically during this session: two real proposals differing ONLY in
action_type, identical params, scored 0.75 -- comfortably above the 0.7
veto threshold `_act_on()` itself uses). R21's own minimal safety fix
(`core/memory/counterfactual.py`, this session): `get_similar_rejections()`
/`should_avoid()` now default to `scope_to_action_type=True`, restricting
a match to rejections recorded under the SAME action_type. This preserves
genuine transfer WITHIN an action_type (situation A -> materially
different situation B, same action_type) -- exactly what R21 must
demonstrate -- while closing the cross-action-type false-positive this
session's own audit found.

Flagship narrative (all real, all through `AutonomousLoop._act_on()`,
zero real LLM calls needed for the flagship itself):
  A (action_type="script", cmd="sudo bash restart_production_server.sh")
    -> real ThreatDetector match (pattern-based, no LLM) -> real rejection
       recorded via _record_external_rejection().
  B (SAME action_type "script", MATERIALLY DIFFERENT cmd ("systemctl
    restart ...") but otherwise-identical topic/duration/priority/team --
    real Jaccard(A,B)=0.727, clears the real 0.7 veto threshold; B is
    independently confirmed, via a direct real ThreatDetector scan of B's
    OWN text inside the flagship itself, to be "otherwise safe" -- zero
    critical signals on its own) -> real should_avoid() veto, BEFORE ever
    reaching ThreatDetector -- the transfer is DEMONSTRABLY what blocked
    B, not an independent trigger (an adversarial-review-driven fix: an
    earlier draft's B also happened to contain "sudo bash" and so was
    independently risky too, which only proved attribution-ORDER, not
    that transfer ALONE changes an otherwise-permitted action's fate).
  C (SAME action_type "script", UNRELATED topic, real Jaccard(A,C)=0.14)
    -> NOT vetoed -- the unrelated control does not receive the transfer.
  D (DIFFERENT action_type "idea_validate", SAME params as A, real raw
    Jaccard(A,D)=0.75 -- i.e. would ALSO have been wrongly vetoed under
    the pre-fix unscoped behavior) -> NOT vetoed BY THE TRANSFER, because
    of R21's own scope_to_action_type fix -- proves the safety boundary is
    real and load-bearing, not merely descriptive (D is still
    independently rejected by its own real ThreatDetector match, since D
    reuses A's "sudo bash" cmd verbatim -- the assertion checks D's
    recorded rejection REASON, distinguishing the two mechanisms).
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.brain.goal_system import GoalSystem
from core.city.agent_registry import AgentRegistry
from core.loop.decision_engine import Candidate
from core.loop.permission_gateway import PermissionGateway
from core.memory.counterfactual import CounterfactualMemory, _jaccard
from core.memory.policy import PolicyMemory

from tests.test_r13_production_learning_validation import build_isolated_engine, build_isolated_loop


def _proposal(action_type: str, params: dict) -> str:
    """Exact real production convention (autonomous_loop.py's own
    `_proposal = f"{winner.action_type} {json.dumps(winner.params, default=str)}"`)."""
    return f"{action_type} " + json.dumps(params, default=str)


A_PARAMS = {
    "topic": "restart the production database server for maintenance",
    "cmd": "sudo bash restart_production_server.sh",
    "duration_min": 5.0, "priority": "high", "team": "infra",
}
# R21 adversarial review (2026-09-10) finding: an earlier draft's B was
# ITSELF independently ThreatDetector-triggering ("sudo bash" appeared in
# B's own text too), so a passing test proved real attribution (the CFM
# block runs and returns first, with a distinguishable reason string) but
# did not prove the transfer ALONE changes an otherwise-permitted action's
# fate. Fixed: B now shares every OTHER field with A (topic/duration_min/
# priority/team -- real Jaccard(A,B)=0.727, still clears the real 0.7 veto
# threshold _act_on() uses) but its "cmd" field ("systemctl restart ...")
# is genuinely, independently threat-free -- verified directly against the
# real ThreatDetector class: B alone produces zero critical signals. B is
# now demonstrably an "otherwise safe" action blocked ONLY by the real
# counterfactual transfer from A.
B_PARAMS = {
    "topic": "restart the production database server for maintenance",
    "cmd": "systemctl restart production-server.service",
    "duration_min": 5.0, "priority": "high", "team": "infra",
}
C_PARAMS = {"topic": "AI trends", "duration_min": 3.0}


@pytest.fixture
def isolated_r21_registry():
    """Real, but deliberately EMPTY AgentRegistry -- no agent is registered
    for "script"/"idea_validate" here. Situations A/B are blocked before
    ever reaching dispatch (by ThreatDetector / CounterfactualMemory
    respectively); situations C/D are only required to prove they are NOT
    vetoed -- if they proceed to Governor.dispatch(), an empty registry
    means a real, fast, honest "no_agents" refusal, never a real LLM call."""
    import core.city.agent_registry as registry_mod
    original = registry_mod._registry_singleton
    fresh = AgentRegistry()
    registry_mod._registry_singleton = fresh
    yield fresh
    registry_mod._registry_singleton = original


def _neutral_candidate(action_type: str, params: dict) -> Candidate:
    return Candidate(
        action_type=action_type, params=params, goal_ids=[], urgency=0.5,
        confidence=0.5, source="think_loop",
    )


async def _real_winner(engine, action_type: str, params: dict) -> Candidate:
    """A real DecisionEngine.evaluate() call over a single real Candidate
    -- mints a real decision_id/candidate_id, matching the established
    R13-R20 "no hand-built Candidate used as the only proof" methodology
    (the winner IS the Candidate, but it only becomes usable as a
    production winner once it has passed through real evaluate())."""
    decision = await engine.evaluate([_neutral_candidate(action_type, params)])
    return decision.winner


# ═══════════════════════════════════════════════════════════════════════════
# Fast, no-LLM unit checks of the real Jaccard substrate + R21's own safety fix
# ═══════════════════════════════════════════════════════════════════════════

class TestSubstrateAndSafetyFix:

    def test_a_b_materially_different_but_related_high_similarity(self):
        """B is NOT identical to A (different server name in "topic") --
        confirms this is genuine A != B, not a same-situation replay."""
        a, b = _proposal("script", A_PARAMS), _proposal("script", B_PARAMS)
        assert a != b
        assert _jaccard(a, b) >= 0.7

    def test_c_unrelated_low_similarity(self):
        a, c = _proposal("script", A_PARAMS), _proposal("script", C_PARAMS)
        assert _jaccard(a, c) < 0.7

    def test_d_cross_action_type_raw_similarity_would_have_falsely_matched(self):
        """Confirms the REAL, pre-fix vulnerability this session's own
        audit found: same params, DIFFERENT action_type, still scores
        exactly as high as the legitimate A-B pair -- proving the fix
        below is not addressing an imagined risk."""
        a, d = _proposal("script", A_PARAMS), _proposal("idea_validate", A_PARAMS)
        assert _jaccard(a, d) >= 0.7

    def test_safety_fix_blocks_cross_action_type_match_by_default(self, tmp_path):
        cf = CounterfactualMemory(db_path=str(tmp_path / "cf.db"))
        cf.record_rejection("dec-a", _proposal("script", A_PARAMS), "blocked by ThreatDetector")
        avoid, score, _ = cf.should_avoid(_proposal("idea_validate", A_PARAMS), threshold=0.7)
        assert avoid is False, (
            f"cross-action-type match must be blocked by the new scope_to_action_type "
            f"default, got avoid={avoid} score={score}"
        )
        cf.close()

    def test_same_action_type_transfer_still_works_after_the_fix(self, tmp_path):
        """The fix must narrow, not eliminate, real generalization."""
        cf = CounterfactualMemory(db_path=str(tmp_path / "cf.db"))
        cf.record_rejection("dec-a", _proposal("script", A_PARAMS), "blocked by ThreatDetector")
        avoid, score, reason = cf.should_avoid(_proposal("script", B_PARAMS), threshold=0.7)
        assert avoid is True
        assert score >= 0.7
        cf.close()

    def test_opt_out_still_available_for_explicit_cross_action_type_use(self, tmp_path):
        """scope_to_action_type=False remains available for a deliberate
        future caller -- the fix narrows the DEFAULT, not the capability."""
        cf = CounterfactualMemory(db_path=str(tmp_path / "cf.db"))
        cf.record_rejection("dec-a", _proposal("script", A_PARAMS), "blocked by ThreatDetector")
        avoid, score, _ = cf.should_avoid(
            _proposal("idea_validate", A_PARAMS), threshold=0.7, scope_to_action_type=False,
        )
        assert avoid is True
        cf.close()


# ═══════════════════════════════════════════════════════════════════════════
# FLAGSHIP: real A->B transfer, real unrelated-C non-transfer, real
# cross-action-type-D non-transfer, all through the real, unmodified
# AutonomousLoop._act_on() production path. Zero real LLM calls needed
# (ThreatDetector is pattern-based; no agent is registered to dispatch to).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFlagshipRealGeneralization:

    async def test_real_rejection_transfers_to_related_situation_not_to_unrelated_or_cross_type(
        self, isolated_vector_db, isolated_r21_registry, tmp_path,
    ):
        """No hand-built Candidate used as the only proof (every winner
        comes from a real DecisionEngine.evaluate() call). No manual
        policy injection. No manually selected winner. No fabricated
        reward/outcome -- A's rejection is a REAL ThreatDetector match on
        REAL text; B/C/D's veto-or-not is the REAL should_avoid() result
        of _act_on()'s own real Gap-4 block."""
        cf_db_path = str(tmp_path / "counterfactual.db")

        # R21's flagship exercises the REAL, unmodified CounterfactualMemory()
        # default-path constructor exactly as _act_on() itself calls it --
        # this monkeypatch only redirects where that default path points,
        # never changes _act_on()'s own code or call shape.
        import core.runtime_paths as runtime_paths_module
        original_get_data_root = runtime_paths_module.get_data_root
        def _isolated_get_data_root():
            return tmp_path
        runtime_paths_module.get_data_root = _isolated_get_data_root
        try:
            engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
            loop = build_isolated_loop(engine)

            # ---- Situation A: real rejection, real ThreatDetector, no LLM ----
            winner_a = await _real_winner(engine, "script", A_PARAMS)
            assert winner_a.decision_id and winner_a.decision_id.startswith("d:")
            await loop._act_on(winner_a)

            cf = CounterfactualMemory(db_path=cf_db_path)
            rejections_after_a = cf.get_all_rejections(limit=10)
            assert len(rejections_after_a) == 1, (
                f"situation A must produce exactly one real rejection row, got {rejections_after_a}"
            )
            assert "ThreatDetector" in rejections_after_a[0]["reason"]

            # ---- Situation B: materially different, same action_type ->
            # real transfer, vetoed BEFORE ThreatDetector (attributable to
            # the counterfactual match, not an independent trigger). B is
            # independently confirmed "otherwise safe" here -- a real,
            # direct ThreatDetector scan of B's OWN text, run BEFORE B ever
            # goes near CounterfactualMemory, finds zero critical signals --
            # so if B still gets blocked below, that block can only be the
            # real counterfactual transfer, not a coincidentally-independent
            # trigger of B's own. ----
            from vectorcode.src.guidance import ThreatDetector as _RealThreatDetector
            b_own_signals = _RealThreatDetector().analyze_input(_proposal("script", B_PARAMS), "r21_test_precheck")
            assert not [s for s in b_own_signals if s.severity >= 0.85], (
                "B must be independently threat-free on its own text -- otherwise "
                "a later block on B would be ambiguous between the real transfer "
                "and an independent trigger"
            )

            winner_b = await _real_winner(engine, "script", B_PARAMS)
            assert winner_b.decision_id != winner_a.decision_id
            await loop._act_on(winner_b)

            rejections_after_b = cf.get_all_rejections(limit=10)
            assert len(rejections_after_b) == 2, (
                f"situation B must have been vetoed and recorded as a SECOND real "
                f"rejection, got {rejections_after_b}"
            )
            b_row = next(r for r in rejections_after_b if r["decision_id"] == winner_b.decision_id)
            assert "auto-blocked: similar to past rejection" in b_row["reason"], (
                "B's block must be attributable to the real counterfactual transfer "
                "from A, not a coincidentally-independent ThreatDetector trigger"
            )

            # ---- Situation C: unrelated -> must NOT receive the transfer ----
            winner_c = await _real_winner(engine, "script", C_PARAMS)
            await loop._act_on(winner_c)
            rejections_after_c = cf.get_all_rejections(limit=10)
            assert len(rejections_after_c) == 2, (
                f"unrelated situation C must NOT be vetoed/recorded as a rejection, "
                f"got {rejections_after_c}"
            )

            # ---- Situation D: same params as A, DIFFERENT action_type ->
            # would have falsely matched pre-fix (raw Jaccard 0.75); must
            # NOT receive the COUNTERFACTUAL transfer post-fix. D's params
            # are byte-identical to A's, so D ALSO independently re-triggers
            # the real ThreatDetector pattern on its own real text (same as
            # A did) -- a real, separate, unavoidable second gate any
            # "sudo bash" text hits regardless of the counterfactual check.
            # The point under test is specifically whether the
            # COUNTERFACTUAL mechanism transferred A's rejection to D -- so
            # the assertion checks D's own recorded rejection REASON, not
            # merely whether some rejection occurred. If the pre-fix
            # (unscoped) behavior were still active, D would be blocked
            # inside the CFM block itself (reason "auto-blocked: similar to
            # past rejection...", returning BEFORE ever reaching
            # ThreatDetector) -- exactly like B was. Post-fix, D is only
            # ever blocked by its own independent ThreatDetector match. ----
            winner_d = await _real_winner(engine, "idea_validate", A_PARAMS)
            await loop._act_on(winner_d)
            rejections_after_d = cf.get_all_rejections(limit=10)
            d_row = next(r for r in rejections_after_d if r["decision_id"] == winner_d.decision_id)
            assert "auto-blocked: similar to past rejection" not in d_row["reason"], (
                f"cross-action-type situation D must NOT be vetoed by A's rejection via "
                f"the counterfactual transfer post-fix, got reason={d_row['reason']!r}"
            )
            assert "ThreatDetector" in d_row["reason"], (
                "D's real, independent ThreatDetector match (same 'sudo bash' text as A) "
                "is expected and orthogonal to the counterfactual-transfer question"
            )

            # ---- Direct confirmation via the same real API _act_on() uses.
            # D is deliberately NOT re-checked here: by this point D's own
            # (independent, ThreatDetector-caused) rejection is itself in
            # the table, so a fresh should_avoid() query for D's exact
            # proposal would self-match D's OWN just-recorded row --
            # correct behavior (a verbatim repeat of a just-rejected
            # proposal should be flagged), but it no longer isolates
            # whether A's rejection specifically transferred to D. That
            # question is already answered precisely above by D's real
            # rejection ROW's REASON (ThreatDetector, never "auto-blocked:
            # similar to past rejection") from the one query that ran
            # before D had a rejection row of its own. ----
            avoid_b, score_b, _ = cf.should_avoid(_proposal("script", B_PARAMS), threshold=0.7)
            avoid_c, score_c, _ = cf.should_avoid(_proposal("script", C_PARAMS), threshold=0.7)
            assert avoid_b is True and score_b >= 0.7
            assert avoid_c is False and score_c < 0.7

            cf.close()

            # ---- Persistence: real restart, real reopen, transfer survives ----
            cf2 = CounterfactualMemory(db_path=cf_db_path)
            avoid_b_2, score_b_2, _ = cf2.should_avoid(_proposal("script", B_PARAMS), threshold=0.7)
            assert avoid_b_2 is True
            assert score_b_2 == pytest.approx(score_b, abs=0.01)
            cf2.close()
        finally:
            runtime_paths_module.get_data_root = original_get_data_root


# ═══════════════════════════════════════════════════════════════════════════
# Safety: transferred/generalized knowledge is a scoring/veto input, never
# an authorization change.
# ═══════════════════════════════════════════════════════════════════════════

class TestSafety:

    def test_classify_is_pure_static_function_unreachable_from_counterfactual(self):
        src = inspect.getsource(PermissionGateway._classify)
        for forbidden in ("CounterfactualMemory", "should_avoid", "get_similar_rejections", "PolicyMemory", "EpistemicTracker"):
            assert forbidden not in src

    def test_red_tier_unaffected_by_a_maximally_similar_real_rejection(self, tmp_path):
        """Even a real rejection that would Jaccard-match a RED action at
        the maximum possible score changes nothing about its real
        permission tier -- a learned/transferred veto is a SCORING/gating
        input at the candidate level, never an authorization change."""
        cf = CounterfactualMemory(db_path=str(tmp_path / "cf.db"))
        red_proposal = _proposal("code_task", {"cmd": "rm -rf /"})
        cf.record_rejection("dec-red", red_proposal, "blocked by ThreatDetector")
        avoid, score, _ = cf.should_avoid(red_proposal, threshold=0.4)
        assert avoid is True
        assert PermissionGateway().classify("code_task") == "RED"
        cf.close()

    def test_no_dynamic_mutation_of_permission_tiers_from_counterfactual_module(self):
        src = inspect.getsource(sys.modules["core.memory.counterfactual"])
        for forbidden in ("GREEN.append", "RED.append", "YELLOW.append", "FORBIDDEN.append", "core.config.CONFIG["):
            assert forbidden not in src


if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v", "--timeout=60"])
    print("OK test_r21_generalization.py" if result.returncode == 0 else "FAILED test_r21_generalization.py")
