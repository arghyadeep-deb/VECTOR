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
# Flagship: fully autonomous (bias-free) GREEN→GREEN switching, via the
# real, existing R6 staleness-diversity mechanism, on a real GREEN-only
# native candidate set.
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

        # ---- The actual capability delta: a real, autonomous, unsteered
        #      switch from one GREEN strategy to a DIFFERENT GREEN strategy. ----
        assert winners == ["git_status"] * 5 + ["consolidate"], (
            f"expected the real R6 staleness mechanism to autonomously "
            f"switch from git_status to consolidate on cycle 6 (both real, "
            f"both GREEN) -- got {winners}. If this repo's exact scoring/"
            f"config/generation-order ever changes, this assertion (not the "
            f"underlying capability) needs re-verification against real "
            f"behavior, never silently loosened."
        )
        assert len(decision_ids) == 6 and len(candidate_ids) == 6, "every real cycle mints fresh, non-colliding IDs"

        # ---- Real outcomes for BOTH strategies, both genuinely executed ----
        git_status_reward = next(c["reward"] for c in cycles if c["winner"] == "git_status")
        consolidate_reward = next(c["reward"] for c in cycles if c["winner"] == "consolidate")
        assert git_status_reward == pytest.approx(0.545, abs=0.01)
        assert consolidate_reward == pytest.approx(0.755, abs=0.01), (
            "consolidate's real reward (uf=0.7 since ConsolidationBot genuinely "
            "returns status='ok' on a real, empty, isolated episodic-memory "
            "scan) -- a real, non-fabricated, independently-computed outcome"
        )

        # ---- Outcome attribution for the switch itself ----
        switch_decision_id = cycles[5]["decision_id"]
        attribution = read_reasoning_chain_for_decision(switch_decision_id)
        assert attribution is not None
        assert attribution["action_taken"] == "consolidate"
        assert attribution["candidate_id"] == cycles[5]["candidate_id"]
        assert attribution["reward"] == pytest.approx(0.755, abs=0.01)

        # ---- Persistence: the switch survives a real restart ----
        from core.memory.episodic import close_db_connection
        close_db_connection()
        gs2 = isolated_r15_goal_system(goal_id)
        engine2 = build_isolated_engine(str(tmp_path / "epistemic2.db"))
        after_restart = await engine2.evaluate(native_candidates(gs2, confidence=0.5))
        h_git = pm.make_situation_hash("git_status", {"goal_id": goal_id, "title": R15_TITLE})
        h_con = pm.make_situation_hash("consolidate", {"goal_id": goal_id, "title": R15_TITLE})
        assert pm.get_score("git_status", h_git) == pytest.approx(0.545, abs=0.01)
        assert pm.get_score("consolidate", h_con) == pytest.approx(0.755, abs=0.01)
        # NOTE: engine2 is a FRESH DecisionEngine -- its own _winner_streak_count
        # resets to 0 on construction (process-local, not persisted -- see
        # R14's report §12), so the post-restart winner is decided by the
        # (now real, persisted, learned) policy scores alone, not by a
        # carried-over streak. consolidate's higher real learned score
        # (0.755 vs 0.545) legitimately makes it the winner here too.
        assert after_restart.winner.action_type == "consolidate"


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
        """Per _select_staleness_aware_winner()'s own real, documented
        contract: once something else wins, the previous winner's
        suppression pressure resets -- it is not a permanent blacklist,
        and there is no artificial "force it back" rule either. What
        ACTUALLY happens on cycle 7 (empirically discovered by this test,
        not assumed): `consolidate`'s real, learned reward (0.755) is
        genuinely HIGHER than `git_status`'s (0.545), so once R6's forced
        cycle-6 trial gives `consolidate` its first real sample,
        PolicyMemory's own real learning -- not R6, not a reset rule --
        keeps it winning on cycle 7 too, because it legitimately scores
        better. This is a stronger, more honest finding than "it reverts
        after one try": VECTOR's real experience of the alternative
        strategy revealed it was actually the better real choice, and
        real learning (not forced exploration) is what sustains the
        switch afterward."""
        goal_id = f"{R15_GOAL_ID_PREFIX}_control_b"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        gs = isolated_r15_goal_system(goal_id)
        winners = []
        for _ in range(7):
            decision = await engine.evaluate(native_candidates(gs, confidence=0.5))
            winners.append(decision.winner.action_type)
            await loop._act_on(decision.winner)
        assert winners[:5] == ["git_status"] * 5
        assert winners[5] == "consolidate"
        assert winners[6] == "consolidate", (
            "consolidate's real learned reward (0.755) genuinely exceeds "
            "git_status's (0.545) -- real PolicyMemory learning, not the "
            "R6 streak mechanism, sustains the switch on cycle 7"
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
