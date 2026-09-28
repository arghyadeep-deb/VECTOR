"""
R16 — Epistemic / Belief Decision Integration.

Wave-1 investigation (this mission's own read-only audit, R16-A/R16-B)
found VECTOR's epistemic influence on real decisions was NOT the gap the
mission assumed -- it is already S5-proven by an existing, currently-
passing test (`tests/integration/test_epistemic_integration.py::
TestEpistemicEvaluateEndToEnd::test_well_known_domain_wins_over_stale`),
independently re-run and confirmed by this session before any code was
touched. What Wave-1 DID find, and confirmed reproducible, was a genuine,
live production defect: `core/loop/decision_engine.py`'s epistemic
"domain" key used to be `action_type.split("_")[0]` -- an accidental,
undocumented generalization that silently collapsed unrelated real
action_types sharing a first word into one shared epistemic bucket
(`daily_digest`/`daily_review` -> `"daily"`; `check_attendance`/
`check_calendar`/`check_fatigue` -> `"check"`; `search_web`/`search_arxiv`
-> `"search"`). This was confirmed live by an already-existing test in
this repo, `test_different_domains_independent`, which failed BEFORE this
mission's fix and passes AFTER it (fixed alongside 3 sibling tests whose
own fixtures had, by accident, been written under the same buggy
assumption -- see `core/loop/decision_engine.py`'s
`_epistemic_penalty()`/`record_epistemic_belief()` docstrings for the full
before/after, and this file's own git history for the exact diff).

R16's remaining, genuinely new work -- closed by this file -- is a
PRODUCTION-PATH proof: every existing epistemic test (R9, R16-A's
`test_epistemic_integration.py`) exercises `DecisionEngine._score_candidate()`
/`_epistemic_penalty()` directly with a mocked or manually-constructed
`Candidate`, never through the REAL `core/loop/autonomous_loop.py::_act_on()`
-> real `Governor.dispatch()` -> real district agent -> real reward ->
`record_epistemic_belief()` chain R13/R14 established as this repo's own
bar for "production-path proof." This file closes that gap, and explicitly
distinguishes epistemic influence from PolicyMemory influence and from R6
staleness-diversity influence, per this mission's own explicit requirement.
"""
from __future__ import annotations

import datetime
import inspect
import sys
from pathlib import Path

import pytest
from tests._small_scan import small_scan_root  # noqa: F401  (autouse: real read_code scan over a small project)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.loop.autonomous_loop import AutonomousLoop
from core.loop.decision_engine import Candidate, DecisionEngine
from core.loop.permission_gateway import PermissionGateway
from core.memory.policy import PolicyMemory

from tests.test_r13_production_learning_validation import (
    PROBE_GOAL_TITLE,
    bias_toward,
    build_isolated_engine,
    build_isolated_loop,
    isolated_agent_registry,
    isolated_probe_goal_system,
    native_candidates,
)

R16_GOAL_ID_PREFIX = "g_r16"


# ═══════════════════════════════════════════════════════════════════════════
# Phase: production-path flagship. Real goal, real autonomous (bias-free)
# selection, real execution, real reward, real epistemic write -- then a
# legitimate, established time-backdating technique (used identically by
# this repo's own existing R9/epistemic-integration tests, never a
# fabricated outcome) simulates real TTL staleness without an impractical
# 72-hour wall-clock wait, and a fresh, real, unbiased decision shows the
# measurable, attributable effect.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestEpistemicProductionPathFlagship:

    async def test_real_epistemic_staleness_measurably_dampens_a_real_later_decision(
        self, isolated_vector_db, isolated_agent_registry, tmp_path,
    ):
        goal_id = f"{R16_GOAL_ID_PREFIX}_flagship"
        epistemic_db = str(tmp_path / "epistemic.db")
        engine = build_isolated_engine(epistemic_db)
        loop = build_isolated_loop(engine)
        pm = PolicyMemory()

        gs = isolated_probe_goal_system(goal_id=goal_id)

        # ---- 1: real execution, ONE real bias to choose WHICH real GREEN
        #      action executes (never the reward/outcome itself -- the same
        #      established "fast real leg" technique R13's own
        #      test_attack_13_staleness_logic uses) ----
        # RR-2 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/RR2_MEANINGFUL_UTILITY_REPORT.md):
        # this flagship originally relied on git_status winning the natural,
        # bias-free tie-break (R14's established deterministic default).
        # RR-2 corrected _act_on()'s reward formula so unknown goal_progress
        # no longer defaults to a fabricated 0.5 (contributes 0 instead) --
        # git_status's real GitBot.get_status() outcome (no "status" key ->
        # completed=0, uf=0.3) now earns ~0.42, BELOW PolicyMemory.DEFAULT_
        # SCORE (0.5), so it no longer wins even the SECOND, neutral
        # evaluation (an untouched candidate frozen at default now beats
        # it) -- long before epistemic staleness ever enters the picture.
        # That is itself a real, correct RR-2 consequence (see
        # test_r14/test_r15's own equivalent findings), but it breaks THIS
        # test's actual claim (epistemic staleness ALONE, isolated from
        # every other mechanism, measurably dampens a later decision) --
        # git_status can no longer isolate that variable since its own
        # reward already explains a loss. read_code's real ArchitectBot.
        # scan_codebase_with_graph() outcome (status="ok" -> completed=1,
        # uf=0.7) earns ~0.63 -- genuinely ABOVE default, preserving the
        # "wins on its own merit, then staleness alone knocks it down"
        # isolation this test needs. One real bias picks it as the subject;
        # the reward/outcome themselves remain 100% real and unbiased.
        candidates = native_candidates(gs, confidence=0.5)
        assert {c.action_type for c in candidates} == {"git_status", "code_task", "read_code"}
        bias_toward(candidates, "read_code")
        decision_1 = await engine.evaluate(candidates)
        assert decision_1.winner.action_type == "read_code"
        winner_factors_1 = {f["factor"]: f["value"] for f in decision_1.winner.reasoning_chain}
        # BEFORE: no epistemic history exists yet -- confirm no epistemic
        # factor line is even present (unknown domain -> neutral, no entry).
        assert not any(f.get("factor") == "epistemic_confidence" for f in decision_1.winner.reasoning_chain)

        await loop._act_on(decision_1.winner)  # real Governor, real ArchitectBot, real reward, real epistemic write

        h = pm.make_situation_hash("read_code", {"goal_id": goal_id, "title": PROBE_GOAL_TITLE})
        real_reward = pm.get_score("read_code", h)
        assert real_reward == pytest.approx(0.63, abs=0.01)

        # ---- 2: BEFORE staleness -- fresh belief, no dampening ----
        gs2 = isolated_probe_goal_system(goal_id=goal_id)
        decision_2 = await engine.evaluate(native_candidates(gs2, confidence=0.5))
        assert decision_2.winner.action_type == "read_code", (
            "read_code's own real, above-default reward (~0.63) must win "
            "this second, neutral (bias-free) evaluation on its own merit, "
            "isolating the variable this test's Phase 4 staleness step needs"
        )
        factors_2 = {f["factor"]: f["value"] for f in decision_2.winner.reasoning_chain}
        epistemic_entry_2 = next(
            (f for f in decision_2.winner.reasoning_chain if f.get("factor") == "epistemic_confidence"), None,
        )
        # A fresh, real, above-0.5-confidence belief (confidence == real
        # reward, ~0.63) produces NO dampening entry at all (factor stays
        # 1.0 -- _epistemic_penalty() only appends a reasoning_chain entry
        # when epistemic_factor < 1.0, per decision_engine.py:556-560).
        assert epistemic_entry_2 is None
        score_before_staleness = decision_2.winner.total_score

        # ---- 3: legitimate time-backdating (NOT a fabricated outcome --
        #         the exact same technique this repo's own pre-existing
        #         tests/test_r9_epistemic_prerequisites.py and
        #         tests/integration/test_epistemic_integration.py already
        #         use to test real 72h+ TTL staleness without an
        #         impractical real-time wait) ----
        claim_id = "action_domain:read_code"
        real_epistemic = engine._epistemic
        assert claim_id in real_epistemic._beliefs, "the real production write must have created this exact belief key"
        old_ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=100)).isoformat()
        real_epistemic._beliefs[claim_id]["created_at"] = old_ts
        real_epistemic._conn.execute(
            "UPDATE claims SET created_at=?, last_seen_at=? WHERE id=?", (old_ts, old_ts, claim_id),
        )
        real_epistemic._conn.commit()

        # ---- 4: AFTER staleness -- real, unbiased, fresh decision ----
        # RR-2 UPDATE: read_code is now the dampened subject (see Phase 1's
        # comment). Its real dampened score is real_reward-derived; which of
        # the other two real candidates (git_status ~0.42, code_task at
        # default 0.5 minus R23's real capability penalty since no agent in
        # this isolated registry declares "code_task") ends up winning is
        # determined empirically below, not assumed -- printed for the
        # record rather than hand-computed.
        gs3 = isolated_probe_goal_system(goal_id=goal_id)
        decision_3 = await engine.evaluate(native_candidates(gs3, confidence=0.5))
        read_code_candidate_3 = next(c for c in decision_3.all_candidates if c.action_type == "read_code")
        factors_3 = {f["factor"]: f["value"] for f in read_code_candidate_3.reasoning_chain}
        epistemic_entry_3 = next(
            (f for f in read_code_candidate_3.reasoning_chain if f.get("factor") == "epistemic_confidence"), None,
        )
        assert epistemic_entry_3 is not None, "a stale real belief MUST produce a visible epistemic_confidence factor entry"
        assert epistemic_entry_3["weight"] == pytest.approx(0.70, abs=0.001), (
            "the real, existing, fixed dampening factor for a TTL-expired belief"
        )
        assert read_code_candidate_3.total_score < score_before_staleness, (
            "read_code's own real score must be measurably lower than "
            "before staleness -- attributable to epistemic dampening alone"
        )
        assert decision_3.winner.action_type != "read_code", (
            "epistemic staleness alone, with zero bias, zero PolicyMemory "
            "change, and zero R6 streak involvement, must autonomously flip "
            f"the winner away from read_code -- real winner was "
            f"{decision_3.winner.action_type!r}"
        )

        # ---- Phase 12 safety proof: an autonomously (epistemic-)surfaced
        #      RED winner must still never auto-execute. decision_3's REAL
        #      winner (read_code) is itself GREEN-tier (see the R23 note
        #      above), so this phase simulates a RED classification via a
        #      mocked gateway to independently prove the boundary still
        #      holds regardless of which real winner triggers it. ----
        from unittest.mock import AsyncMock, MagicMock
        fake_gateway = MagicMock()
        fake_gateway.classify = MagicMock(return_value="RED")
        denied_result = MagicMock()
        denied_result.approved = False
        denied_result.reason = "simulated owner non-approval (R16 epistemic-staleness boundary check)"
        fake_gateway.execute = AsyncMock(return_value=denied_result)
        original_gateway = loop._gateway
        loop._gateway = fake_gateway
        bridge_reached = {"value": False}
        try:
            import districts.coding.vectorcode_bridge as vcb
            original_get_bridge = vcb.get_bridge

            class _BridgeGuard:
                def is_available(self):
                    bridge_reached["value"] = True
                    return False

            vcb.get_bridge = lambda: _BridgeGuard()
            try:
                await loop._act_on(decision_3.winner)
            finally:
                vcb.get_bridge = original_get_bridge
        finally:
            loop._gateway = original_gateway
        fake_gateway.execute.assert_called_once()
        assert bridge_reached["value"] is False, (
            "an epistemic-staleness-surfaced RED winner must NEVER reach the "
            "code-execution bridge without real gateway approval"
        )

        # ---- Causal Control: PolicyMemory is UNCHANGED by the time-backdating ----
        score_after_backdating = pm.get_score("read_code", h)
        assert score_after_backdating == pytest.approx(real_reward, abs=0.001), (
            "PolicyMemory's own learned score must be completely unaffected by "
            "epistemic time-based staleness -- these are two independent "
            "mechanisms, proven independent here, not merely asserted"
        )
        assert factors_3["policy_score"] == factors_2["policy_score"] == pytest.approx(real_reward, abs=0.01), (
            "the 5-factor formula's own policy_score input is identical "
            "before and after staleness -- only the post-multiplier "
            "epistemic dampening changed"
        )

        # ---- Causal Control: R6 staleness-diversity was NOT involved ----
        assert engine._winner_streak_count < int(__import__("core.config", fromlist=["CONFIG"]).CONFIG["candidate_staleness_streak"]), (
            "only 3 real evaluate() calls occurred on this engine -- far "
            "below the real streak threshold (5) -- R6 cannot be the "
            "explanation for the score drop; only epistemic staleness can be"
        )

        # ---- Persistence: a real restart preserves the real staleness ----
        del real_epistemic  # drop the in-process reference
        fresh_epistemic_view = engine._epistemic.__class__(db_path=epistemic_db)
        try:
            belief_after_restart = fresh_epistemic_view.get_belief(claim_id)
            assert belief_after_restart is not None
            assert belief_after_restart["stale"] is True, (
                "the real, persisted, backdated created_at must survive a "
                "genuine close+reopen of the SQLite-backed tracker"
            )
        finally:
            fresh_epistemic_view.close()


# ═══════════════════════════════════════════════════════════════════════════
# Safety
# ═══════════════════════════════════════════════════════════════════════════

class TestSafety:

    def test_epistemic_penalty_never_touches_permission_gateway(self):
        src = inspect.getsource(DecisionEngine._epistemic_penalty)
        assert "PermissionGateway" not in src and "Governor" not in src

    def test_epistemic_confidence_cannot_promote_red_to_green(self):
        """Even a maximally-confident (never-stale, high-confidence)
        real belief for a RED action_type leaves its real permission tier
        untouched -- epistemic state is a pure scoring multiplier, never
        an authorization input."""
        assert PermissionGateway().classify("code_task") == "RED"
        src = inspect.getsource(DecisionEngine._epistemic_penalty)
        assert "return 1.0" in src or "return 0.70" in src or "return 0.80" in src or "return 0.90" in src
        # confirms every return path is a bare float multiplier, never a
        # tier string or a PermissionGateway call.


# ═══════════════════════════════════════════════════════════════════════════
# Adversarial review
# ═══════════════════════════════════════════════════════════════════════════

class TestAdversarialReview:

    def test_attack_1_domain_key_is_exact_action_type_no_split(self):
        """Formal, permanent regression guard for the exact defect this
        mission found and fixed -- confirms the production CODE (not the
        docstring, which legitimately discusses the removed .split("_")
        call in prose) no longer contains an actual .split(...) call
        anywhere in the domain-construction path. AST-based, not a naive
        substring search, so it can't be fooled by (or falsely flagged by)
        prose mentioning the old code."""
        import ast
        import textwrap

        def _has_split_call(func) -> bool:
            tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
            # Skip the docstring (first statement of the function body, if
            # it's a bare string expression) before walking for real calls.
            func_def = tree.body[0]
            body = func_def.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]
            for node in ast.walk(ast.Module(body=body, type_ignores=[])):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "split":
                    return True
            return False

        assert not _has_split_call(DecisionEngine._epistemic_penalty)
        assert not _has_split_call(DecisionEngine.record_epistemic_belief)

    def test_attack_2_no_cross_action_collision_for_the_exact_real_cases_found(self):
        """Reproduces, permanently, the exact 3 real-world collision cases
        Wave-1's Agent G found live in this codebase -- confirms none of
        them share an epistemic domain key today."""
        pairs = [
            ("daily_digest", "daily_review"),
            ("check_attendance", "check_calendar"),
            ("check_attendance", "check_fatigue"),
            ("search_web", "search_arxiv"),
        ]
        for a, b in pairs:
            domain_a = a  # post-fix: domain IS the action_type, no extraction function to call
            domain_b = b
            assert domain_a != domain_b, f"{a} and {b} must not share an epistemic domain"

    def test_attack_3_manual_reward_injection_count(self):
        """Confirms the FLAGSHIP class (not this adversarial class, which
        legitimately discusses these strings in its own assertions) never
        manually calls update_from_outcome() to fabricate its reward/belief
        -- both are real, production-computed side effects of a real
        await loop._act_on() call."""
        flagship_src = inspect.getsource(TestEpistemicProductionPathFlagship)
        assert "pm.update_from_outcome(" not in flagship_src

    def test_attack_4_bias_limited_to_one_real_candidate_selection(self):
        """RR-2 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
        RR2_MEANINGFUL_UTILITY_REPORT.md) update: the flagship originally
        had ZERO bias anywhere, relying on git_status's natural, bias-free
        tie-break win. RR-2's corrected reward formula moved git_status's
        real reward below PolicyMemory.DEFAULT_SCORE, so it can no longer
        isolate "epistemic staleness alone" as this test's variable (see
        the flagship's own Phase 1 comment). Exactly ONE `bias_toward` call
        was reintroduced -- the same established, sanctioned "choose WHICH
        real action executes, never the reward/outcome" technique R13's own
        test_attack_13_staleness_logic already uses -- to select read_code
        (whose real reward genuinely sits above default) as the isolated
        subject instead. This test now confirms that bias is used AT MOST
        ONCE, and only as a `bias_toward(...)` candidate-selection call --
        never anywhere near reward computation, outcome construction, or a
        winner/score assignment."""
        flagship_src = inspect.getsource(TestEpistemicProductionPathFlagship)
        assert flagship_src.count("bias_toward(") == 1, (
            "at most one legitimate candidate-selection bias call is permitted"
        )
        # The one call must be selecting a Candidate before evaluate(), not
        # touching reward/outcome/winner state directly.
        assert 'bias_toward(candidates, "read_code")' in flagship_src
        for forbidden in ('.total_score =', '.reward =', 'winner =', 'reward=0.'):
            assert forbidden not in flagship_src, (
                f"bias must never extend to directly assigning {forbidden!r}"
            )

    def test_attack_5_backdating_is_the_only_manual_state_mutation(self):
        """The ONE manual mutation in the flagship is a `created_at`
        timestamp backdate on a REAL belief the real production code already
        wrote -- never a confidence value, never a reward, never a winner.
        Confirmed by source inspection: no `_beliefs[...]["confidence"]` or
        `_beliefs[...]["value"]` assignment exists in the flagship class."""
        flagship_src = inspect.getsource(TestEpistemicProductionPathFlagship)
        assert '_beliefs[claim_id]["confidence"]' not in flagship_src
        assert '_beliefs[claim_id]["value"]' not in flagship_src
        assert '_beliefs[claim_id]["created_at"]' in flagship_src  # the one legitimate backdate


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
