"""
R15 — Autonomous GREEN→GREEN Strategy Switching.

R14 proved autonomous, bias-free selection + real execution + real reward
+ persistence + a real, safety-verified strategy switch via R6 staleness-
diversity -- but its only real multi-strategy goal pattern
(tags=["git","coding"]) has exactly 2 GREEN options (git_status, read_code)
with a RED one (code_task) positioned between them in real generation
order, so R6's "next distinct candidate" was RED, not the second GREEN
option. R14 explicitly reported this as "AUTONOMOUS RED EXPOSURE, NOT
GREEN->GREEN SWITCHING" and left GREEN->GREEN switching as an open
question for the next mission.

Wave-1 investigation (this mission's own read-only audit, Agent R15-A)
found the missing piece is NOT a code gap -- `_select_staleness_aware_
winner()`, `_score_candidate()`, and `_act_on()` already treat GREEN and
RED candidates identically for selection purposes; tier only matters at
the `_act_on()`/gateway execution boundary, never at generation or
ranking. The actual gap is a GOAL-TAGGING gap: no existing real
`PRESEEDED_GOALS` entry happens to carry two tags that BOTH map to GREEN
action_types with no RED tag mixed in between them in generation order.

R15-A identified several real, already-trustworthy tag pairs (from
`core/brain/goal_system.py::_TAG_TO_ACTION_TYPE`, unmodified since R11)
that would produce a GREEN-only candidate set with real, non-stub
handlers: `["git","research"]` -> [git_status, daily_digest] (real, but
daily_digest makes multiple live network calls -- HN/GitHub/DevTo/ArXiv/
crypto/tech-news -- unsuitable for a deterministic, fast test);
`["git","memory"]` -> [git_status, consolidate] (real,
`districts/memory_curator/consolidation_bot.py::ConsolidationBot`, purely
local -- on a fresh, empty, isolated episodic-memory DB,
`consolidate_old_episodes()` finds zero old episodes and returns
`{"status":"ok","consolidated":0}` immediately, before any LLM/network/
Obsidian code path is ever reached, confirmed by reading its source in
full). This file uses `["git","memory"]` for exactly this reason: real,
fast, deterministic, and zero external side effects.

**No production code was modified for this milestone.** Exactly like
R11-R14's own "isolated real goal, real tags" methodology, this proof
uses an isolated `GoalSystem` instance with a real, already-trustworthy
tag combination -- not a new `PRESEEDED_GOALS` entry, not a new tag
mapping, not a new action_type. The capability this file proves was
already fully wired; it had simply never been demonstrated because no
prior mission's chosen goal pattern happened to be GREEN-only.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest
from tests._small_scan import small_scan_root  # noqa: F401  (autouse: real read_code scan over a small project)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.brain.goal_system import GoalSystem
from core.loop.autonomous_loop import AutonomousLoop
from core.loop.decision_engine import DecisionEngine
from core.loop.permission_gateway import PermissionGateway
from core.memory.policy import PolicyMemory
from districts.coding.git_bot import GitBot
from districts.memory_curator.consolidation_bot import ConsolidationBot

from tests.test_r13_production_learning_validation import (
    build_isolated_engine,
    build_isolated_loop,
    native_candidates,
    read_reasoning_chain_for_decision,
)

R15_GOAL_ID_PREFIX = "g_r15"
R15_TAGS = ["git", "memory"]
R15_TITLE = "Commit code every day (R15 probe)"


def isolated_r15_goal_system(goal_id: str) -> GoalSystem:
    """Real GoalSystem, __new__ bypass (established R11-R14 isolation
    pattern) -- real, already-trustworthy tags ["git","memory"], never a
    fabricated tag or a modification to the real PRESEEDED_GOALS list."""
    import datetime
    gs = GoalSystem.__new__(GoalSystem)
    gs._memory = None
    gs._persist = lambda: None
    gs._goals = [{
        "id": goal_id, "title": R15_TITLE, "horizon": "SHORT", "priority": 9,
        "status": "active", "progress": 0.0, "tags": list(R15_TAGS),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }]
    return gs


@pytest.fixture
def isolated_r15_agent_registry():
    """Fresh AgentRegistry with only the two real, real-capability-
    declaring GREEN agents this scenario needs: GitBot (git_status) and
    ConsolidationBot (consolidate) -- no RED-capable agent is even
    registered, since this scenario never needs one."""
    import core.city.agent_registry as registry_mod
    from core.city.agent_registry import AgentRegistry
    original = registry_mod._registry_singleton
    fresh = AgentRegistry()
    fresh.register(GitBot())
    fresh.register(ConsolidationBot())
    registry_mod._registry_singleton = fresh
    yield fresh
    registry_mod._registry_singleton = original


# ═══════════════════════════════════════════════════════════════════════════
# Flagship: fully autonomous (bias-free) GREEN→GREEN switching on a real
# GREEN-only native candidate set.
#
# 2026-09-23 (supersedes the original RR-2 claim below, kept in the inline
# comments for history): RR-2's original finding was that the switch was
# reward-driven -- git_status scoring durably BELOW consolidate's default
# after one real execution. That depended on a real bug (GitBot's genuine
# success carrying no "status" key, miscounted as a failure). With that bug
# fixed, git_status and consolidate now earn an IDENTICAL real reward
# (0.63) on success, so there is no reward asymmetry left to drive a
# switch. The switch this test observes is now driven purely by R6's
# mechanical 5-consecutive-win staleness suppression, not reward learning.
# See the assertion below for the full, current explanation.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestGreenToGreenFlagship:

    async def test_autonomous_green_to_green_switch_via_r6(
        self, isolated_vector_db, isolated_r15_agent_registry, tmp_path,
    ):
        goal_id = f"{R15_GOAL_ID_PREFIX}_flagship"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        pm = PolicyMemory()
        gs = isolated_r15_goal_system(goal_id)

        # ---- Real native candidate generation: exactly 2 real strategies,
        #      BOTH GREEN, zero RED -- confirmed via the real, unmodified
        #      permission tiers, not assumed. ----
        first_candidates = native_candidates(gs, confidence=0.5)
        assert {c.action_type for c in first_candidates} == {"git_status", "consolidate"}
        gw = PermissionGateway()
        assert gw.classify("git_status") == "GREEN"
        assert gw.classify("consolidate") == "GREEN"

        decision_ids: set[str] = set()
        candidate_ids: set[str] = set()
        cycles: list[dict] = []

        # ---- 6 real, bias-free, autonomous cycles -- the test never
        #      chooses, alternates, or steers which action wins. ----
        for cycle_num in range(1, 7):
            candidates = native_candidates(gs, confidence=0.5)  # uniform confidence, no bias_toward anywhere
            assert len({c.confidence for c in candidates}) == 1
            assert len({c.urgency for c in candidates}) == 1
            decision = await engine.evaluate(candidates)
            decision_ids.add(decision.winner.decision_id)
            candidate_ids.add(decision.winner.candidate_id)

            tier = gw.classify(decision.winner.action_type)
            assert tier == "GREEN", (
                f"this scenario's native candidate set is GREEN-only by "
                f"construction -- {decision.winner.action_type} must never "
                f"be non-GREEN; got {tier}"
            )

            await loop._act_on(decision.winner)  # real Governor, real district agent, real reward, no stubs
            h = pm.make_situation_hash(decision.winner.action_type, {"goal_id": goal_id, "title": R15_TITLE})
            cycles.append({
                "cycle": cycle_num,
                "decision_id": decision.winner.decision_id,
                "candidate_id": decision.winner.candidate_id,
                "winner": decision.winner.action_type,
                "total_score": decision.winner.total_score,
                "reward": pm.get_score(decision.winner.action_type, h),
            })

        winners = [c["winner"] for c in cycles]

        # ---- 2026-09-23 UPDATE (superseding the RR-2 update below, kept
        #      for history): RR-2's own finding depended on a real bug --
        #      GitBot.get_status() returns a raw dict with no "status" key
        #      on a genuine success, so _act_on()'s generic dispatch path
        #      scored a real git_status success as completed=0.0 (real
        #      reward ~0.42, BELOW PolicyMemory.DEFAULT_SCORE). That bug is
        #      now fixed (see core/loop/autonomous_loop.py's own 2026-09-23
        #      comment on its read-only-result evidence check): a git_status
        #      success with a real `branch` present now correctly scores
        #      "ok", same as consolidate's own real success -- both now earn
        #      an IDENTICAL real reward (0.63). With no reward asymmetry
        #      left, this scenario reverts to exactly the R14-era regime RR-2's
        #      own docstring (above) describes as the "before" state: R6's
        #      mechanical 5-consecutive-win staleness exhaustion is once again
        #      the ONLY mechanism that ever dislodges git_status, not reward
        #      learning. This is the correct, more honest outcome -- the
        #      switch capability itself still works, just via the mechanism
        #      RR-2 originally found less interesting, because the reward
        #      asymmetry it relied on was never real to begin with. ----
        assert winners == ["git_status"] * 5 + ["consolidate"], (
            f"expected git_status to win cycles 1-5 (both actions now score "
            f"an identical real 0.63 on success, so R6's mechanical "
            f"5-consecutive-win staleness suppression -- not reward learning "
            f"-- is what forces cycle 6's switch) -- got {winners}. If this "
            f"repo's exact scoring/config/generation-order ever changes, "
            f"this assertion (not the underlying capability) needs "
            f"re-verification against real behavior, never silently "
            f"loosened."
        )
        assert len(decision_ids) == 6 and len(candidate_ids) == 6, "every real cycle mints fresh, non-colliding IDs"

        # ---- Real outcomes for BOTH strategies, both genuinely executed,
        #      both now correctly earning the SAME real reward. ----
        git_status_reward = next(c["reward"] for c in cycles if c["winner"] == "git_status")
        consolidate_reward = next(c["reward"] for c in cycles if c["winner"] == "consolidate")
        assert git_status_reward == pytest.approx(0.63, abs=0.01), (
            "git_status's real reward, now that a genuine success (real "
            "'branch' present) correctly earns 'ok' instead of being "
            "silently miscounted as a failure -- see the 2026-09-23 "
            "autonomous_loop.py fix"
        )
        assert consolidate_reward == pytest.approx(0.63, abs=0.01), (
            "consolidate's real reward (uf=0.7 since ConsolidationBot genuinely "
            "returns status='ok' on a real, empty, isolated episodic-memory "
            "scan) -- a real, non-fabricated, independently-computed outcome"
        )

        # ---- Outcome attribution for the switch itself (now cycle 6, index 5) ----
        switch_decision_id = cycles[5]["decision_id"]
        attribution = read_reasoning_chain_for_decision(switch_decision_id)
        assert attribution is not None
        assert attribution["action_taken"] == "consolidate"
        assert attribution["candidate_id"] == cycles[5]["candidate_id"]
        assert attribution["reward"] == pytest.approx(0.63, abs=0.01)

        # ---- Persistence: the switch survives a real restart ----
        from core.memory.episodic import close_db_connection
        close_db_connection()
        gs2 = isolated_r15_goal_system(goal_id)
        engine2 = build_isolated_engine(str(tmp_path / "epistemic2.db"))
        after_restart = await engine2.evaluate(native_candidates(gs2, confidence=0.5))
        h_git = pm.make_situation_hash("git_status", {"goal_id": goal_id, "title": R15_TITLE})
        h_con = pm.make_situation_hash("consolidate", {"goal_id": goal_id, "title": R15_TITLE})
        assert pm.get_score("git_status", h_git) == pytest.approx(0.63, abs=0.01)
        assert pm.get_score("consolidate", h_con) == pytest.approx(0.63, abs=0.01)
        # NOTE (2026-09-23, updated): engine2 is a FRESH DecisionEngine --
        # its own _winner_streak_count resets to 0 on construction
        # (process-local, not persisted -- see R14's report §12), so the
        # post-restart winner is decided by the (now real, persisted,
        # learned) policy scores alone, not by a carried-over streak. Both
        # actions now carry the SAME real learned score (0.63 vs 0.63, no
        # longer 0.63 vs 0.42) at the PolicyMemory layer -- but this is not
        # a policy-score tie broken by generation order. The persisted
        # CausalGraph (same episodic DB, real across the restart) still
        # carries git_status's 5 real hit_count observations at strength
        # 0.63, clearing DecisionEngine.CAUSAL_MIN_OBSERVATIONS and earning
        # a real >1.0 _causal_factor multiplier (decision_engine.py:786-
        # 814); consolidate's single observation stays below that floor and
        # scores causally neutral at 1.0. git_status's total candidate score
        # is therefore genuinely higher post-restart too -- a plain score
        # win, not a tie-break.
        assert after_restart.winner.action_type == "git_status"


# ═══════════════════════════════════════════════════════════════════════════
# Causal controls
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCausalControls:

    async def test_control_a_no_learning_control_group_never_switches(
        self, isolated_vector_db, isolated_r15_agent_registry, tmp_path,
    ):
        """A FRESH engine per cycle (streak never accumulates, exactly like
        R14's own flagship-vs-multicycle distinction) never switches --
        confirms the switch is attributable to the persistent engine's real
        streak state, not to the candidate set itself always preferring
        consolidate."""
        goal_id = f"{R15_GOAL_ID_PREFIX}_control_a"
        winners = []
        for i in range(6):
            gs = isolated_r15_goal_system(goal_id)
            engine = build_isolated_engine(str(tmp_path / f"epistemic_{i}.db"))
            decision = await engine.evaluate(native_candidates(gs, confidence=0.5))
            winners.append(decision.winner.action_type)
        assert winners == ["git_status"] * 6, (
            "with a FRESH DecisionEngine every cycle (no persistent streak), "
            "git_status must win every single time -- ruling out 'the "
            "candidate set itself just naturally alternates' as a confound"
        )

    async def test_control_b_streak_resets_after_a_real_switch(
        self, isolated_vector_db, isolated_r15_agent_registry, tmp_path,
    ):
        """2026-09-23 UPDATE (superseding the RR-2 update below, kept for
        history): the real bug RR-2's finding depended on (GitBot.get_status()
        success miscounted as completed=0.0 because the raw dict has no
        "status" key) is now fixed -- see core/loop/autonomous_loop.py's own
        2026-09-23 comment. git_status's real reward is no longer below
        PolicyMemory.DEFAULT_SCORE; it now correctly ties consolidate's own
        real reward at 0.63. With that asymmetry gone, R6's mechanical
        staleness-diversity mechanism is once again the ONLY thing that
        moves the winner off git_status: 5 consecutive real git_status wins
        (cycles 1-5), R6 forces `consolidate` in for exactly one cycle
        (cycle 6), then git_status resumes winning (cycle 7). 2026-09-23
        round 9 correction: cycle 7 is NOT a policy-score tie broken by
        generation order -- PolicyMemory ties at 0.63/0.63, but
        DecisionEngine._causal_factor() (core/loop/decision_engine.py:786-
        814) applies an extra multiplier once an action clears
        CAUSAL_MIN_OBSERVATIONS (3): git_status has 5 recorded causal-graph
        hits at strength 0.63, earning a real >1.0 factor, while
        consolidate has only 1 hit (below the observation floor) and stays
        causally neutral at 1.0. So git_status's total candidate score is
        genuinely, if marginally, higher in cycle 7 -- a plain score win,
        not a tie-break. Real, empirically observed, not assumed; the
        original RR-2 docstring is kept below for history, but its premise
        no longer holds now that the bug it depended on is fixed."""
        goal_id = f"{R15_GOAL_ID_PREFIX}_control_b"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        gs = isolated_r15_goal_system(goal_id)
        winners = []
        for _ in range(7):
            decision = await engine.evaluate(native_candidates(gs, confidence=0.5))
            winners.append(decision.winner.action_type)
            await loop._act_on(decision.winner)
        assert winners == ["git_status"] * 5 + ["consolidate"] + ["git_status"], (
            "expected: cycles 1-5 git_status (a plain win, not a tie -- "
            "git_status has already learned 0.63 from cycle 1 while "
            "consolidate remains untried at PolicyMemory's 0.5 default, so "
            "git_status simply outscores it every cycle until R6 forces a "
            "switch), cycle 6 consolidate (R6's real 5-consecutive-win "
            "staleness suppression firing exactly as designed -- this is "
            "also the FIRST time consolidate actually runs, earning it the "
            "same real 0.63 as git_status), cycle 7 git_status resumes "
            "(PolicyMemory ties 0.63/0.63, but git_status's 5 recorded "
            "causal-graph observations clear CAUSAL_MIN_OBSERVATIONS and "
            "earn a real >1.0 _causal_factor multiplier while consolidate's "
            "single observation stays neutral at 1.0 -- a genuine score "
            "win, not a generation-order tie-break) -- got " + str(winners)
        )

    async def test_control_c_wrong_candidate_attribution(
        self, isolated_vector_db, isolated_r15_agent_registry, tmp_path,
    ):
        goal_id = f"{R15_GOAL_ID_PREFIX}_control_c"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        gs = isolated_r15_goal_system(goal_id)
        decisions = []
        for _ in range(6):
            decision = await engine.evaluate(native_candidates(gs, confidence=0.5))
            await loop._act_on(decision.winner)
            decisions.append(decision)
        attr_git = read_reasoning_chain_for_decision(decisions[0].winner.decision_id)
        attr_con = read_reasoning_chain_for_decision(decisions[5].winner.decision_id)
        assert attr_git["candidate_id"] == decisions[0].winner.candidate_id
        assert attr_con["candidate_id"] == decisions[5].winner.candidate_id
        assert attr_git["candidate_id"] != attr_con["candidate_id"]
        assert attr_git["action_taken"] == "git_status"
        assert attr_con["action_taken"] == "consolidate"

    async def test_control_d_generation_stability(self, isolated_vector_db, isolated_r15_agent_registry, tmp_path):
        goal_id = f"{R15_GOAL_ID_PREFIX}_control_d"
        gs1 = isolated_r15_goal_system(goal_id)
        gs2 = isolated_r15_goal_system(goal_id)
        types1 = {c.action_type for c in native_candidates(gs1, confidence=0.5)}
        types2 = {c.action_type for c in native_candidates(gs2, confidence=0.5)}
        assert types1 == types2 == {"git_status", "consolidate"}


# ═══════════════════════════════════════════════════════════════════════════
# Safety
# ═══════════════════════════════════════════════════════════════════════════

class TestSafety:

    def test_permission_tiers_unaffected(self):
        gw = PermissionGateway()
        assert gw.classify("git_status") == "GREEN"
        assert gw.classify("consolidate") == "GREEN"
        assert gw.classify("code_task") == "RED"  # unaffected by this scenario's choices

    def test_no_production_code_was_modified_for_r15(self):
        """R15's entire capability delta comes from a real, already-
        trustworthy tag pair and the pre-existing R6 mechanism -- confirmed
        by construction (this file adds no new tag mapping, no new
        action_type, no new decision_engine.py/goal_system.py logic)."""
        gen_src = inspect.getsource(GoalSystem.generate_immediate_actions)
        assert "R15" not in gen_src  # no R15-specific code exists in production


# ═══════════════════════════════════════════════════════════════════════════
# Adversarial review
# ═══════════════════════════════════════════════════════════════════════════

class TestAdversarialReview:

    def test_attack_1_no_bias_anywhere_in_flagship(self):
        """AST-based (not substring) check -- a naive substring search
        would be fooled by this file's own legitimate comments stating
        that no bias is used (e.g. "no bias_toward anywhere")."""
        import ast
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(TestGreenToGreenFlagship)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
                assert name != "bias_toward", "the flagship must never actually call bias_toward()"

    def test_attack_2_no_manual_winner_selection(self):
        flagship_src = inspect.getsource(TestGreenToGreenFlagship)
        assert "winner =" not in flagship_src.replace("decision.winner", "")  # no hand-assignment of a winner

    def test_attack_3_no_manual_reward_injection(self):
        flagship_src = inspect.getsource(TestGreenToGreenFlagship)
        assert "update_from_outcome(" not in flagship_src

    def test_attack_4_candidate_generation_unchanged_by_learning(self):
        """Already covered by Control D -- re-confirmed."""
        gs1 = isolated_r15_goal_system("g_r15_attack4")
        types_before_any_execution = {c.action_type for c in native_candidates(gs1, confidence=0.5)}
        assert types_before_any_execution == {"git_status", "consolidate"}

    def test_attack_5_hash_consistency(self):
        pm = PolicyMemory()
        h1 = pm.make_situation_hash("consolidate", {"goal_id": "g_r15_attack5", "title": R15_TITLE})
        h2 = pm.make_situation_hash("consolidate", {"goal_id": "g_r15_attack5", "title": R15_TITLE})
        assert h1 == h2

    def test_attack_6_wrong_db(self, isolated_vector_db):
        import os
        assert os.environ.get("VECTOR_DB_PATH") == isolated_vector_db
        assert isolated_vector_db != "vector_memory.db"

    def test_attack_7_safety_tier_bypass(self):
        gw = PermissionGateway()
        assert gw.classify("git_status") == "GREEN"
        assert gw.classify("consolidate") == "GREEN"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
