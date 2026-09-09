"""
E6 — Native Candidate Competition. THE FINAL LEARNING GATE.

============================================================
UPDATE 2026-09-09 (R11 — Native Goal Strategy Candidate Generation): see
VECTOR_TECHNICAL_KNOWLEDGE/R11_NATIVE_GOAL_STRATEGY_CANDIDATE_GENERATION_REPORT.md
============================================================
This file's own headline conclusion below ("NATIVE CANDIDATE COMPETITION
DOES NOT EXIST TODAY") was TRUE, verified live, at the time this file was
written — it is preserved here unmodified as an accurate historical record
of that finding and audit, exactly as this whole session's convention has
been (see e.g. R8's report, never rewritten by R9's follow-on fix). R11
closed the exact bottleneck items 1/2/4 describe below: goals whose tags map
to >= 2 known action_types now genuinely produce that many distinct
candidates (see tests/test_r11_native_goal_strategy_candidates.py for the
new coverage). Items 3 ("0 active plans") and the GOAL_ACTION_MAP 2-value
fallback ceiling are UNCHANGED by R11 and remain accurate. Only ONE test in
this file (`test_think_tick_tag_to_action_dict_is_unreachable_dead_code`)
asserted something that is no longer true for the reason it now correctly
fails for (the mapping moved, not "became reachable in place") — it has
been replaced below with its accurate successor; every other test in this
file remains a correct, unmodified regression check (the empty-tags fallback
case in `test_all_short_horizon_actions_share_the_identical_action_type`
deliberately used goals with NO tags, so it is untouched by, and still
correctly describes, the fallback path R11 preserves).

Question: can VECTOR's REAL candidate-generation pipeline naturally produce
at least TWO meaningfully different action types for the SAME decision
context?

============================================================
AUDIT RESULT (full detail: VECTOR_TECHNICAL_KNOWLEDGE/E6_NATIVE_CANDIDATE_COMPETITION_REPORT.md)
============================================================

NATIVE CANDIDATE COMPETITION DOES NOT EXIST TODAY. Traced and confirmed
directly against the REAL running production code and REAL current goal/
plan state (not simulated):

1. `core/brain/goal_system.py::generate_immediate_actions()` derives its
   `action_type` from `GOAL_ACTION_MAP.get(goal["horizon"], ...)`:
       GOAL_ACTION_MAP = {"SHORT": "research_topic", "MID": "analyze_progress",
                           "LONG": "analyze_progress"}
   This is keyed ONLY by horizon (SHORT/MID/LONG) -- NEVER by the goal's own
   content, tags, or domain. Every single SHORT-horizon goal, regardless of
   what it is actually about, produces the literal SAME action_type
   ("research_topic"). Every stalled MID or LONG goal produces
   "analyze_progress" -- MID and LONG even collapse to the identical value.
   At most 2 distinct action_types are structurally possible from this
   source, ever, and neither depends on what the goal is actually about.

2. `core/loop/autonomous_loop.py::_think_tick()`'s `_TAG_TO_ACTION` dict (14
   tag->action_type mappings: kiit->check_attendance, git->git_status,
   coding->code_task, ml->search_arxiv, etc.) is DEAD CODE in production.
   It remaps based on `a.get("tags", [])` -- but the dicts
   `generate_immediate_actions()` returns never include a "tags" key at
   all (confirmed directly: a real dict from real production code has
   `tags: None`). The remapping loop therefore never fires; `action_type =
   a["action"]` (the GOAL_ACTION_MAP value) is what is always actually used.

3. `core/loop/autonomous_loop.py::_get_plan_candidates()` CAN produce
   genuinely diverse action_types (each plan step carries its own real
   action_type from real plan decomposition) -- but confirmed, by directly
   querying the real production PlanStore right now, that there are
   **0 active plans**. This source currently contributes nothing.

4. Querying the real, live GoalSystem right now:
   `generate_immediate_actions(limit=10)` returns exactly **1** action,
   `action_type="analyze_progress"`. A single evaluate() call today, using
   only real production inputs, has NOTHING to compete against -- not even
   the weak 2-value (research_topic vs analyze_progress) diversity is
   currently present, because no SHORT-horizon goal happens to be active
   alongside a stalled MID/LONG one at this exact moment.

CONCLUSION: real, content-driven candidate diversity does not exist in
production. The 2-value horizon-only diversity is the theoretical ceiling of
today's architecture, and even that is not always realized. This IS the
learning bottleneck this whole R1-E5 pipeline has been building toward
identifying, per this task's own explicit escape hatch:
"NATIVE CANDIDATE COMPETITION IS THE CURRENT LEARNING BOTTLENECK."

PER THE TASK'S OWN INSTRUCTION: this was NOT implemented tonight
("IF NATIVE COMPETITION DOES NOT EXIST: DO NOT IMPLEMENT IT TONIGHT").
GOAL_ACTION_MAP was not expanded, no tag-based routing was wired up, no
new candidate generator was added. This file's tests are audit
verification only -- they PROVE the above findings against real code, they
do not fix anything.

LEVEL A (LAB) vs LEVEL B (NATIVE), per this task's own anti-cheating rules:
Every "candidate diversity" behavioral proof this whole overnight pipeline
has produced (R6, R7, E1, E4) used hand-constructed Candidate objects
(`make_candidate("A", ...)`, `make_candidate("B", ...)`) -- this is
explicitly LEVEL A / LAB evidence, and every one of those reports already
says so. Nothing in this pipeline has ever claimed, or may claim, LEVEL B
production validity for candidate diversity. This file makes that
LAB-vs-NATIVE distinction explicit and testable, one final time, using the
REAL DecisionEngine.
"""
import datetime
from unittest.mock import MagicMock

import pytest

from core.loop.decision_engine import Candidate, DecisionEngine
from core.memory.policy import PolicyMemory


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# NATIVE audit: prove the findings directly against real production code
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestNativeCandidateGenerationAudit:

    def test_goal_action_map_has_at_most_two_distinct_values(self):
        """Direct proof: GOAL_ACTION_MAP structurally cannot produce more
        than 2 distinct action_types, regardless of how many goals exist or
        what they are about."""
        from core.brain.goal_system import GOAL_ACTION_MAP
        assert set(GOAL_ACTION_MAP.values()) == {"research_topic", "analyze_progress"}
        assert GOAL_ACTION_MAP["MID"] == GOAL_ACTION_MAP["LONG"], (
            "MID and LONG horizons collapse to the identical action_type"
        )

    def _isolated_goal_system(self):
        """Real GoalSystem, but with persistence fully neutralized and its
        in-memory goal list replaced by test-controlled fake entries --
        NEVER writes to the real/live goal store. generate_immediate_actions()
        itself (the method under test) is called completely for real.

        R12-H (2026-09-09): constructing via GoalSystem() would run __init__ ->
        _load_or_seed() -> _merge_new_seeds() -> _persist() against the REAL
        production goal store BEFORE this method's own overrides below ever run
        -- safe only by accident, as long as PRESEEDED_GOALS never gains an id
        this store doesn't already have. Bypassing __init__ via __new__ removes
        the real-DB touch entirely rather than racing to override it after."""
        from core.brain.goal_system import GoalSystem
        gs = GoalSystem.__new__(GoalSystem)
        gs._memory = None
        gs._persist = lambda: None  # safety net: no real write, ever
        gs._goals = []  # replace real loaded goals with a fully test-controlled set
        return gs

    def test_generate_immediate_actions_never_includes_tags(self):
        """Direct proof that _TAG_TO_ACTION's remapping loop is unreachable:
        the real production dict shape has no 'tags' key at all."""
        gs = self._isolated_goal_system()
        gs._goals.append({
            "id": "g_e6_probe", "title": "E6 audit probe goal", "horizon": "SHORT",
            "priority": 5, "status": "active", "progress": 0.0, "tags": [],
            "created_at": _now_iso(),
        })
        actions = gs.generate_immediate_actions(limit=10)
        assert len(actions) >= 1
        for action in actions:
            assert "tags" not in action, (
                "generate_immediate_actions()'s real output must not carry a 'tags' "
                "key -- if this ever starts failing, _TAG_TO_ACTION may have become "
                "reachable and this report's finding needs re-verification"
            )

    def test_all_short_horizon_actions_share_the_identical_action_type(self):
        """Direct behavioral proof: 3 SHORT-horizon goals with completely
        different, unrelated content ALL produce the same action_type."""
        gs = self._isolated_goal_system()
        for i, title in enumerate([
            "Check KIIT attendance portal",
            "Commit today's code changes",
            "Read an arxiv paper on transformers",
        ]):
            gs._goals.append({
                "id": f"g_e6_probe_{i}", "title": title, "horizon": "SHORT",
                "priority": 5, "status": "active", "progress": 0.0, "tags": [],
                "created_at": _now_iso(),
            })
        actions = gs.generate_immediate_actions(limit=10)
        short_actions = [a for a in actions if a["source"] == "SHORT_goal"]
        assert len(short_actions) == 3
        distinct_types = {a["action_type"] for a in short_actions}
        assert distinct_types == {"research_topic"}, (
            f"expected all SHORT-horizon goals to collapse to the same "
            f"action_type regardless of content, got {distinct_types}"
        )

    def test_think_tick_no_longer_contains_the_dead_tag_mapping(self):
        """UPDATED by R11: direct source proof that the dead _TAG_TO_ACTION
        dict + its unreachable remap loop are GONE from _think_tick() --
        they moved to core.brain.goal_system (see
        test_r11_native_goal_strategy_candidates.py for proof the mapping
        is now genuinely reachable there, not just relocated-but-still-dead)."""
        import inspect
        import core.loop.autonomous_loop as al
        src = inspect.getsource(al.AutonomousLoop._think_tick)
        assert "_TAG_TO_ACTION" not in src
        assert 'tags = a.get("tags", [])' not in src
        assert 'action_type=a["action_type"]' in src, (
            "the candidate-building loop must now use generate_immediate_actions()'s "
            "already-resolved action_type directly"
        )


# ═══════════════════════════════════════════════════════════════════════════
# LEVEL A (LAB): existing DecisionEngine CAN adapt given two valid candidates
# — explicitly labeled LAB, not a production claim
# ═══════════════════════════════════════════════════════════════════════════

def make_candidate(action_type, confidence=0.6, urgency=0.5, params=None):
    return Candidate(action_type=action_type, params=params or {}, confidence=confidence, urgency=urgency)


@pytest.fixture
def engine():
    e = DecisionEngine()
    e._get_goals = MagicMock()
    e._get_goals().get_active_goals.return_value = []
    e._get_memory = MagicMock()
    e._get_memory().store.return_value = None
    e._get_epistemic = MagicMock()
    e._get_epistemic().get_belief.return_value = None
    e._get_reasoning_bank = MagicMock(return_value=None)
    e._get_neural_trainer = MagicMock(return_value=None)
    e._get_context_engine = MagicMock()
    e._get_context_engine().get_world_state.return_value = {}
    e._get_metacognition = MagicMock(return_value=None)
    e._get_correction_learner = MagicMock(return_value=None)
    return e


@pytest.mark.unit
class TestLevelALabOnly:
    """LAB evidence: the real DecisionEngine, given two hand-constructed
    candidates (never produced by real candidate generation), can adapt its
    ranking based on real, persisted PolicyMemory learning. This is the
    SAME mechanism E1/R6/R7 already exercised -- restated here, explicitly
    labeled, as this task's own final LAB-level checkpoint. It does NOT
    demonstrate, and must never be cited as demonstrating, that real
    production candidate generation ever presents the DecisionEngine with
    this situation."""

    async def test_lab_decision_engine_adapts_given_hand_constructed_candidates(self, engine):
        import uuid
        action_a = f"e6_lab_a_{uuid.uuid4().hex[:8]}"
        action_b = f"e6_lab_b_{uuid.uuid4().hex[:8]}"
        params = {}

        # LAB candidates -- explicitly NOT produced by real candidate generation.
        baseline = await engine.evaluate([
            make_candidate(action_a, confidence=0.62, params=params),
            make_candidate(action_b, confidence=0.60, params=params),
        ])
        assert baseline.winner.action_type == action_a  # sanity check

        pm = engine._get_policy()
        h_a = pm.make_situation_hash(action_a, params)
        for _ in range(8):
            pm.update_from_outcome(action_a, h_a, 0.0)  # real, repeated bad outcome

        after_learning = await engine.evaluate([
            make_candidate(action_a, confidence=0.62, params=params),
            make_candidate(action_b, confidence=0.60, params=params),
        ])
        assert after_learning.winner.action_type == action_b, (
            "LAB: DecisionEngine correctly adapts given two hand-constructed candidates "
            "-- this is Level A only, not a claim about production candidate diversity"
        )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
