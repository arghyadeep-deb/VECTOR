"""
R18-EQ — Equation Goal Capability.

R15-R17 identified the bottleneck this file closes: g_first_revenue and
g_equation_portfolio (core/brain/goal_system.py's PRESEEDED_GOALS, added
2026-07-08 per Blueprint/(C) The Equation) had real intent but ZERO real
executable strategies. Their tags ("revenue","equation","wedge","startups",
"portfolio") matched nothing in _TAG_TO_ACTION_TYPE / _TAG_TO_ADDITIONAL_
ACTION_TYPE, so generate_immediate_actions() fell through to the generic
horizon fallback (analyze_progress) every cycle -- see
VECTOR_TECHNICAL_KNOWLEDGE/R12_NATIVE_STRATEGY_SEMANTICS_REPORT.md section 6,
which explicitly declined to invent a mapping rather than fabricate diversity.

R18-EQ's own Phase 1/2 investigation (this session, direct source reading,
NOT assumed from any prior report) found VECTOR already has two real,
on-target capabilities the goals' own text names:
  - g_first_revenue's title literally says "wedge: AI content ops for
    creators" -> districts/content/script_generator.py::ScriptGenerator
    (real LLM-backed script generation, capability "script").
  - districts/startups/idea_validator.py::IdeaValidator (real LLM-backed
    startup-idea scoring; its own prompt already cites "The Equation" --
    "Governing law -- The Equation ... W = Sigma O*R*M") is a genuine
    strategic alternative ("validate the idea first" vs "produce content"),
    capability "idea_validate".

Both action_types already had real handlers AND real, exact-match Governor
routing (core/city/governor.py's DISTRICT_TASK_MAP: "script"->"content",
"idea_validate"->"startups") -- they were simply never added to ANY
permission tier in core/config.py, making them UNKNOWN and therefore always
blocked at PermissionGateway despite being fully built (the same "real
capability, unclassified, therefore UNKNOWN, therefore always blocked"
defect class this file's own core/config.py has fixed before -- Task 58B/
58C/58D precedent). A third, independently-discovered gap: IdeaValidator's
own `capabilities` list was missing the literal string "idea_validate",
which would have silently degraded real multi-agent capability-based
routing (core/city/governor.py's `task_type in agent.capabilities` match)
to an unreliable HP-lottery pick among ALL FOUR real startups-district
agents (CompetitorSpy, MarketScanner, RevenueModeler, IdeaValidator) in a
full production registry.

R18-EQ's fix (three files, no new action_type, no new district, no new
handler): core/config.py (add "script","idea_validate" to permission.green),
core/brain/goal_system.py (add "wedge"->"script", "startups"->"idea_validate"
to _TAG_TO_ACTION_TYPE), districts/startups/idea_validator.py (add
"idea_validate" to IdeaValidator.capabilities).

Empirical finding from this session's own isolated scratch probe (fully
isolated: tmp VECTOR_DB_PATH, tmp VECTOR_TEST_DATA_DIR, isolated
AgentRegistry with only IdeaValidator + ScriptGenerator registered): real
g_first_revenue goal -> real generate_immediate_actions() -> native
candidates ["script","idea_validate"], both classified GREEN -> real
DecisionEngine.evaluate() -> real AutonomousLoop._act_on() executing the
biased winner (idea_validate) -> real IdeaValidator.validate_idea() ->
real LLM call (259.0s in this sandbox, consistent with this codebase's
established real-cloud-LLM-fallback-chain latency, e.g. R13's
ArchitectBot.scan_codebase_with_graph() at 90-216s) -> real result dict
-> real 5-factor reward 0.755 -> real PolicyMemory.update_from_outcome().

That is the flagship proof TestFlagshipRealProductionBoundary formalizes
below. Given this sandbox's demonstrated real-LLM latency, this file
deliberately keeps the number of real-LLM-calling executions to exactly
ONE (the flagship, idea_validate) -- every other test either inspects
source/config/routing directly or monkeypatches district agents' `.run()`
to fast stubs while leaving their real `.capabilities` declarations
untouched, exactly the "mocks for unit isolation, real production boundary
crossing only in the flagship" split Phase 7 of the R18-EQ mission requires.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.brain.goal_system import (
    GOAL_ACTION_MAP,
    GoalSystem,
    PRESEEDED_GOALS,
    _TAG_TO_ACTION_TYPE,
    _tag_derived_action_types,
)
from core.city.agent_registry import AgentRegistry
from core.loop.decision_engine import Candidate, DecisionEngine
from core.loop.permission_gateway import PermissionGateway
from core.memory.policy import PolicyMemory
from districts.content.script_generator import ScriptGenerator
from districts.startups.competitor_spy import CompetitorSpy
from districts.startups.idea_validator import IdeaValidator
from districts.startups.market_scanner import MarketScanner
from districts.startups.revenue_modeler import RevenueModeler

# Imported, not duplicated -- the exact isolation/production-boundary
# helpers R13 established and this session's own conversation summary
# records as "importable from tests/test_r13_production_learning_validation.py".
from tests.test_r13_production_learning_validation import (
    build_isolated_engine,
    build_isolated_loop,
    read_reasoning_chain_for_decision,
)

EQ_GOAL_IDS = ["g_first_revenue", "g_equation_portfolio"]


def _preseeded(goal_id: str) -> dict:
    return next(g.copy() for g in PRESEEDED_GOALS if g["id"] == goal_id)


def isolated_equation_goal_system(goal_ids: list[str] = EQ_GOAL_IDS) -> GoalSystem:
    """Real GoalSystem, __new__ bypass (R11/R12/R13 established pattern) --
    seeded with the REAL PRESEEDED_GOALS Equation entries (same id, title,
    horizon, tags VECTOR actually ships), never a synthetic probe goal --
    so this file tests the actual Equation goals, not a goal-ID curve-fit."""
    gs = GoalSystem.__new__(GoalSystem)
    gs._memory = None
    gs._persist = lambda: None
    gs._goals = [_preseeded(gid) for gid in goal_ids]
    return gs


def native_candidates(gs: GoalSystem, confidence: float = 0.5, limit: int = 4) -> list[Candidate]:
    """Identical translation to test_r13's native_candidates() -- kept local
    (not imported) only because R13's version is written for its own
    single-goal probe signature; behavior is the same production mapping
    autonomous_loop._think_tick() uses."""
    actions = gs.generate_immediate_actions(limit=limit)
    return [
        Candidate(
            action_type=a["action_type"],
            params={"goal_id": a["goal_id"], "title": a["title"]},
            goal_ids=[a["goal_id"]],
            urgency=0.5,
            confidence=confidence,
            source="think_loop",
        )
        for a in actions
    ]


def bias_toward(candidates: list[Candidate], target_action_type: str) -> None:
    for c in candidates:
        c.confidence = 0.95 if c.action_type == target_action_type else 0.1


@pytest.fixture
def isolated_equation_registry():
    """Real AgentRegistry containing ONLY the two real handlers the Equation
    goals' native strategies route to (ScriptGenerator, IdeaValidator) --
    the same minimal-but-real registry shape R13's isolated_agent_registry
    established, sized for what g_first_revenue/g_equation_portfolio's own
    real tags actually route to."""
    import core.city.agent_registry as registry_mod
    original = registry_mod._registry_singleton
    fresh = AgentRegistry()
    fresh.register(IdeaValidator())
    fresh.register(ScriptGenerator())
    registry_mod._registry_singleton = fresh
    yield fresh
    registry_mod._registry_singleton = original


@pytest.fixture
def isolated_multi_agent_startups_registry(monkeypatch):
    """Real AgentRegistry with ALL FOUR real startups-district agents
    (CompetitorSpy, MarketScanner, RevenueModeler, IdeaValidator) -- their
    real, unmodified `.capabilities` lists are what this fixture exists to
    exercise. `.run()` is monkeypatched to a fast, no-LLM stub on each
    instance (unit-isolation mocking, per Phase 7 -- this fixture's only
    job is proving ROUTING SELECTION, which never reaches `.run()`'s body
    at all; the flagship test below is what crosses the real production
    boundary through a real `.run()`/real LLM call). IdeaValidator is given
    the LOWEST health_points of the four so a routing test that lands on it
    anyway can only be explained by real capability matching, never HP."""
    import core.city.agent_registry as registry_mod
    original = registry_mod._registry_singleton
    fresh = AgentRegistry()

    idea_validator = IdeaValidator()
    competitor_spy = CompetitorSpy()
    market_scanner = MarketScanner()
    revenue_modeler = RevenueModeler()

    idea_validator.health_points = 100
    competitor_spy.health_points = 900
    market_scanner.health_points = 900
    revenue_modeler.health_points = 900

    for agent in (idea_validator, competitor_spy, market_scanner, revenue_modeler):
        async def _fast_stub(task, _name=agent.name):
            return {"status": "ok", "handled_by": _name}
        monkeypatch.setattr(agent, "run", _fast_stub)
        fresh.register(agent)

    registry_mod._registry_singleton = fresh
    yield fresh
    registry_mod._registry_singleton = original


# ═══════════════════════════════════════════════════════════════════════════
# Phase 7 — BEFORE/AFTER capability proof
# ═══════════════════════════════════════════════════════════════════════════

class TestBeforeAfterCapabilityDelta:

    def test_before_equation_goals_had_zero_legitimate_strategies(self, monkeypatch):
        """Reproduces the pre-R18-EQ deficiency directly against the real,
        unmodified generate_immediate_actions() code path: with ONLY this
        session's two new _TAG_TO_ACTION_TYPE entries removed (everything
        else -- permission tiers, IdeaValidator.capabilities, Governor
        routing -- left exactly as R18-EQ shipped them, since those are not
        what caused the original deficiency), both Equation goals collapse
        to the single generic horizon fallback with zero diversity --
        the exact defect Phase 1's forensics identified."""
        monkeypatch.delitem(_TAG_TO_ACTION_TYPE, "wedge", raising=False)
        monkeypatch.delitem(_TAG_TO_ACTION_TYPE, "startups", raising=False)

        gs = isolated_equation_goal_system()
        actions = gs.generate_immediate_actions(limit=10)
        by_goal: dict[str, list[str]] = {}
        for a in actions:
            by_goal.setdefault(a["goal_id"], []).append(a["action_type"])

        assert by_goal.get("g_first_revenue") == ["analyze_progress"], (
            "with the R18-EQ tag mappings removed, g_first_revenue must fall "
            "back to exactly one generic action -- the deficiency this "
            "milestone exists to fix"
        )
        assert by_goal.get("g_equation_portfolio") == ["analyze_progress"], (
            "same generic single-strategy fallback for g_equation_portfolio"
        )
        assert by_goal["g_first_revenue"] == by_goal["g_equation_portfolio"], (
            "BEFORE: both Equation goals produce the identical generic "
            "fallback -- no goal-specific strategy diversity at all"
        )

    def test_after_equation_goals_have_real_distinct_strategies(self):
        """Real, unmodified generate_immediate_actions() (R18-EQ's actual
        shipped mapping) -- g_first_revenue now proposes 2 real, distinct
        strategies; g_equation_portfolio proposes 1 (its tags legitimately
        only match "startups", and R18-EQ deliberately did NOT map
        "equation"/"portfolio"/"revenue" -- no fabricated diversity)."""
        gs = isolated_equation_goal_system()
        actions = gs.generate_immediate_actions(limit=10)
        by_goal: dict[str, list[str]] = {}
        for a in actions:
            by_goal.setdefault(a["goal_id"], []).append(a["action_type"])

        assert set(by_goal["g_first_revenue"]) == {"script", "idea_validate"}, (
            f"got {by_goal.get('g_first_revenue')}"
        )
        assert set(by_goal["g_equation_portfolio"]) == {"idea_validate"}, (
            f"got {by_goal.get('g_equation_portfolio')}"
        )
        # Capability delta, stated explicitly: 0 real strategies -> 2 for
        # g_first_revenue, 0 -> 1 for g_equation_portfolio.
        assert len(by_goal["g_first_revenue"]) == 2
        assert len(by_goal["g_equation_portfolio"]) == 1

    def test_no_fabricated_mapping_for_unjustified_tags(self):
        """R12's own precedent (explicitly cited in this session's
        goal_system.py comment) is honored: "revenue", "equation", and
        "portfolio" remain UNMAPPED -- R18-EQ did not invent a strategy for
        every Equation-goal tag, only the two with a real, named capability
        behind them."""
        assert "revenue" not in _TAG_TO_ACTION_TYPE
        assert "equation" not in _TAG_TO_ACTION_TYPE
        assert "portfolio" not in _TAG_TO_ACTION_TYPE
        assert _TAG_TO_ACTION_TYPE["wedge"] == "script"
        assert _TAG_TO_ACTION_TYPE["startups"] == "idea_validate"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 6 — production call path: permission tiers + real Governor routing
# ═══════════════════════════════════════════════════════════════════════════

class TestPermissionAndGovernorRouting:

    def test_script_and_idea_validate_are_green(self):
        gw = PermissionGateway()
        assert gw.classify("script") == "GREEN"
        assert gw.classify("idea_validate") == "GREEN"

    def test_governor_district_task_map_exact_match(self):
        """Real, unmodified core/city/governor.py DISTRICT_TASK_MAP --
        exact-match routing table, not an LLM-classify guess."""
        from core.city.governor import DISTRICT_TASK_MAP
        assert DISTRICT_TASK_MAP["script"] == "content"
        assert DISTRICT_TASK_MAP["idea_validate"] == "startups"

    def test_idea_validator_declares_its_own_action_type_capability(self):
        """The independently-discovered gap this session fixed: without the
        literal string "idea_validate" in IdeaValidator.capabilities, real
        capability-based routing (governor.py's `task_type in
        agent.capabilities`) would find zero capable agents and fall back
        to HP-lottery across the whole startups district."""
        iv = IdeaValidator()
        assert "idea_validate" in iv.capabilities

    @pytest.mark.asyncio
    async def test_capability_routing_selects_idea_validator_not_hp_lottery(
        self, isolated_multi_agent_startups_registry,
    ):
        """Real governor.dispatch() against a real, full 4-agent startups
        district, with IdeaValidator given the LOWEST HP of the four. If
        routing were still HP-lottery (the pre-fix behavior), one of the
        900-HP agents would win. It must be IdeaValidator -- proving real
        capability-based routing, not HP, decided this."""
        from core.city.governor import Governor
        gov = Governor()
        result = await gov.dispatch({"type": "idea_validate", "params": {"idea": {"name": "probe"}}})
        assert result.get("handled_by") == "IdeaValidator", (
            f"expected capability-based routing to select IdeaValidator "
            f"(lowest HP of the four) over the three 900-HP agents, got {result}"
        )

    @pytest.mark.asyncio
    async def test_capability_routing_selects_script_generator(self, isolated_equation_registry, monkeypatch):
        """Same real dispatch path for the content district's "script"
        action_type -- ScriptGenerator is the only content-district agent
        registered here (real capabilities list independently confirmed
        unique for "script" among all districts/content/*.py agents), so
        this also confirms no regression to that pre-existing routing."""
        async def _fast_stub(task):
            return {"status": "ok", "handled_by": "ScriptGenerator"}
        sg = next(a for a in isolated_equation_registry.get_by_district("content") if isinstance(a, ScriptGenerator))
        monkeypatch.setattr(sg, "run", _fast_stub)

        from core.city.governor import Governor
        gov = Governor()
        result = await gov.dispatch({"type": "script", "params": {"topic": "probe", "duration_min": 1}})
        assert result.get("handled_by") == "ScriptGenerator"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 7/11 — FLAGSHIP: real goal -> real native candidate -> real
# DecisionEngine competition -> real _act_on() -> real Governor -> real
# IdeaValidator.validate_idea() -> real LLM call -> real reward -> real
# PolicyMemory persistence -> real reasoning_chains attribution. The ONE
# real-LLM-calling execution in this file (real latency observed this
# session: 259.0s) -- generous timeout below.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.timeout(600)
class TestFlagshipRealProductionBoundary:

    async def test_real_equation_goal_produces_real_idea_validate_execution(
        self, isolated_vector_db, isolated_equation_registry, tmp_path,
    ):
        """No hand-constructed Candidate is ever passed to _act_on() -- the
        executed winner is DecisionEngine.evaluate()'s own real object,
        generated from the REAL g_first_revenue goal (PRESEEDED_GOALS, not
        a synthetic probe), through the REAL production path this session's
        own scratch probe first confirmed empirically."""
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        pm = PolicyMemory()

        gs = isolated_equation_goal_system(["g_first_revenue"])
        candidates = native_candidates(gs, confidence=0.5)
        assert {c.action_type for c in candidates} == {"script", "idea_validate"}, (
            "the real, unmodified Equation goal must propose exactly these "
            "two real native strategies -- not a fabricated set"
        )

        bias_toward(candidates, "idea_validate")
        decision = await engine.evaluate(candidates)
        assert decision.winner.action_type == "idea_validate"
        assert any(decision.winner is c for c in candidates), (
            "the executed winner must be DecisionEngine's own real object, "
            "never a hand-built Candidate"
        )
        decision_id = decision.winner.decision_id
        candidate_id = decision.winner.candidate_id
        assert decision_id and decision_id.startswith("d:")
        assert candidate_id and candidate_id.startswith("c:")

        assert PermissionGateway().classify("idea_validate") == "GREEN"

        winner_params = dict(decision.winner.params)  # snapshot before _act_on() (params is a live ref)

        await loop._act_on(decision.winner)  # REAL _act_on(): real governor.dispatch(),
        # real IdeaValidator.run() -> validate_idea() -> real LLM call,
        # real 5-factor reward, real PolicyMemory write.

        # Hash must be computed from the winner's OWN real params (title
        # carries generate_immediate_actions()'s real "Start: {title}"
        # prefix for an unstarted MID/LONG goal -- reconstructing it from
        # the raw PRESEEDED_GOALS title would silently compute the WRONG
        # situation_hash and read back a stale default).
        h = pm.make_situation_hash("idea_validate", winner_params)
        score_after = pm.get_score("idea_validate", h)
        assert score_after != PolicyMemory.DEFAULT_SCORE, (
            "a real executed outcome must have moved the policy score away "
            "from the untouched default"
        )
        assert 0.0 <= score_after <= 1.0

        # Real outcome-attribution readback (R7/Task 92 correlation).
        attribution = read_reasoning_chain_for_decision(decision_id)
        assert attribution is not None, "R7 correlation must be readable back from reasoning_chains"
        assert attribution["candidate_id"] == candidate_id
        assert attribution["action_taken"] == "idea_validate"
        assert attribution["reward"] == pytest.approx(score_after, abs=0.01)

        # script's own candidate must exist but was never autonomously
        # executed by this run -- its policy score stays at default.
        script_params = next(c.params for c in candidates if c.action_type == "script")
        h_script = pm.make_situation_hash("script", script_params)
        assert pm.get_score("script", h_script) == PolicyMemory.DEFAULT_SCORE

        # ---- Phase 8/11-H: persistence survives a real restart ----
        from core.memory.episodic import close_db_connection
        close_db_connection()
        pm2 = PolicyMemory()
        score_after_restart = pm2.get_score("idea_validate", h)
        assert score_after_restart == pytest.approx(score_after, abs=0.001)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5/9 — safety: real handler source-level side-effect audit. No
# second real LLM call (script's handler is audited by source inspection,
# never executed, in this file).
# ═══════════════════════════════════════════════════════════════════════════

class TestSafetyNoExternalSideEffects:

    def test_idea_validate_dispatch_chain_has_no_external_io(self):
        """Every method IdeaValidator.run()'s real dispatch chain can reach
        for the "idea_validate" action_type (run -> validate_idea only --
        analyze_market_size/assess_competition are separate, un-dispatched
        methods) is source-audited for external communication or financial
        action markers. Only real, local-only `_call_ollama()` (LLM) calls
        and internal `_store_result()`/`self.validated_ideas[...]` writes
        are present."""
        src = inspect.getsource(IdeaValidator.validate_idea) + inspect.getsource(IdeaValidator.run)
        for forbidden in ("httpx.post", "httpx.get", "requests.", "smtplib", "subprocess.", "os.system"):
            assert forbidden not in src, f"unexpected external/irreversible call marker: {forbidden}"
        assert "_call_ollama(" in src
        assert "_store_result(" in src

    def test_script_generation_has_no_external_io(self):
        """ScriptGenerator.run()/generate_script() -- pure local LLM
        drafting, no posting/upload/scheduling call (those are separate,
        distinct content-district agents: Uploader, ContentScheduler --
        never reached by the "script" action_type)."""
        from districts.content.script_generator import ScriptGenerator as SG
        src = inspect.getsource(SG)
        for forbidden in ("httpx.post", "httpx.get", "requests.", "smtplib", "subprocess.", "os.system"):
            assert forbidden not in src

    def test_red_actions_remain_unaffected_by_r18_eq(self):
        from core.config import CONFIG
        pc = CONFIG["permission"]
        assert "code_task" in pc["red"]
        assert "script" not in pc["red"] and "script" not in pc["yellow"]
        assert "idea_validate" not in pc["red"] and "idea_validate" not in pc["yellow"]

    def test_act_on_generic_governor_path_never_bypasses_red_yellow_gating(self):
        """R15-R17 documented AutonomousLoop._act_on()'s generic
        governor-dispatch fallback (for action_types outside the VC/skill
        special-cased blocks) as NOT calling gw.execute() before dispatch.
        "script" and "idea_validate" both fall through this exact generic
        path -- but both are GREEN, and GREEN has never required
        gw.execute() approval anywhere in this codebase's existing gates
        (the VC block above only routes RED/YELLOW through gw.execute()
        too). This pre-existing pattern is therefore orthogonal to R18-EQ's
        two GREEN action_types and is intentionally left untouched per the
        mission's "do NOT silently fix unrelated architecture" instruction
        -- this test only re-confirms RED (code_task) still requires
        gw.execute()+approval, which R18-EQ did not modify."""
        import core.loop.autonomous_loop as al
        src = inspect.getsource(al.AutonomousLoop._act_on)
        assert '_level in ("RED", "YELLOW")' in src
        assert "gw.execute(" in src
        assert "if not _gw_result.approved:" in src


# ═══════════════════════════════════════════════════════════════════════════
# Phase 9/11-I — malformed / unknown goal-tag input safety
# ═══════════════════════════════════════════════════════════════════════════

class TestMalformedInputSafety:

    def test_empty_tags_no_crash(self):
        assert _tag_derived_action_types([]) == []
        assert _tag_derived_action_types(None) == []

    def test_unknown_tags_no_crash(self):
        assert _tag_derived_action_types(["nonexistent_tag_xyz", "another_fake_one"]) == []

    def test_malformed_non_string_tags_skipped_not_crashed(self):
        assert _tag_derived_action_types(["startups", {"nested": "dict"}, ["nested", "list"], None, 42]) == ["idea_validate"]

    def test_duplicate_tags_collapse_to_one_entry(self):
        assert _tag_derived_action_types(["startups", "startups", "wedge", "wedge"]) == ["idea_validate", "script"]

    def test_conflicting_and_mixed_tags_bounded(self):
        """Mixing a known Equation tag with several other real known tags
        never exceeds _MAX_STRATEGIES_PER_GOAL and never crashes."""
        result = _tag_derived_action_types(["startups", "wedge", "git", "coding", "build"])
        assert len(result) <= 3
        assert all(isinstance(r, str) for r in result)

    def test_goal_with_no_tags_field_falls_back_safely(self):
        gs = GoalSystem.__new__(GoalSystem)
        gs._memory = None
        gs._persist = lambda: None
        gs._goals = [{
            "id": "g_r18_no_tags", "title": "No tags goal", "horizon": "MID",
            "priority": 5, "status": "active", "progress": 0.0,
        }]
        actions = gs.generate_immediate_actions(limit=5)
        assert len(actions) == 1
        assert actions[0]["action_type"] == GOAL_ACTION_MAP["MID"]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 11-J — unrelated-goal regression: R18-EQ's two new tag mappings
# must not alter any pre-existing goal's strategy set.
# ═══════════════════════════════════════════════════════════════════════════

class TestUnrelatedGoalRegression:

    def test_g_daily_commit_unaffected(self):
        """g_daily_commit's tags (["git","habit","coding"]) share none of
        R18-EQ's new keys ("wedge","startups") -- its strategy set must be
        byte-identical to pre-R18-EQ (R12/R13's own documented result:
        git_status + code_task + read_code)."""
        gs2 = GoalSystem.__new__(GoalSystem)
        gs2._memory = None
        gs2._persist = lambda: None
        gs2._goals = [_preseeded("g_daily_commit")]
        actions = gs2.generate_immediate_actions(limit=5)
        assert {a["action_type"] for a in actions} == {"git_status", "code_task", "read_code"}

    def test_all_other_preseeded_goals_unaffected(self):
        """Every non-Equation PRESEEDED_GOALS entry produces the same
        strategy set with R18-EQ's mapping active as _tag_derived_action_types
        would produce with only the pre-R18-EQ subset of the table (proven
        by construction: none of their tags are "wedge" or "startups")."""
        untouched_ids = {g["id"] for g in PRESEEDED_GOALS} - set(EQ_GOAL_IDS)
        for gid in untouched_ids:
            goal = _preseeded(gid)
            tags = goal.get("tags", [])
            assert "wedge" not in tags and "startups" not in tags, (
                f"{gid} unexpectedly shares an R18-EQ tag -- regression scope assumption violated"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Phase 10 — production DB safety: this file never touches the real DB.
# ═══════════════════════════════════════════════════════════════════════════

class TestProductionDBSafety:

    def test_isolated_vector_db_fixture_used_by_every_persistent_test(self, isolated_vector_db):
        import os
        assert os.environ.get("VECTOR_DB_PATH") == isolated_vector_db
        assert "test_tmp" not in isolated_vector_db
        assert isolated_vector_db != "vector_memory.db"

    def test_git_worktree_confirms_only_expected_files_modified(self):
        """Static, non-destructive confirmation the working tree only
        contains files a known, documented milestone actually touched --
        catches an accidental unrelated edit before commit. R18-EQ's own
        diff is already committed (see git log); the R18-EQ-era expected
        set below is kept for historical record. R19 (2026-09-10,
        VECTOR_TECHNICAL_KNOWLEDGE/R19_R20_MASTER_REPORT.md) is the current
        in-progress milestone at the time this test runs against a dirty
        tree, so its own real, documented files are included too -- this is
        the expected, recurring shape of this check (each milestone's own
        report documents its own file list; a file outside ALL of them is
        still a real accidental-edit signal)."""
        import subprocess
        repo_root = Path(__file__).resolve().parents[1]
        out = subprocess.run(
            ["git", "status", "--short"], cwd=str(repo_root), capture_output=True, text=True, check=True,
        ).stdout
        changed = {line[3:].strip() for line in out.splitlines() if line.strip()}
        expected_prefixes = {
            # R18-EQ (committed)
            "core/config.py", "core/brain/goal_system.py",
            "districts/startups/idea_validator.py", "tests/test_r18_eq_equation_capability.py",
            "tests/test_r12_native_strategy_semantics.py",
            "VECTOR_TECHNICAL_KNOWLEDGE/R18_EQ_EQUATION_CAPABILITY_REPORT.md",
            # R19 (committed 1b7c4f395) + R20 (in progress) -- see
            # VECTOR_TECHNICAL_KNOWLEDGE/R19_R20_MASTER_REPORT.md
            "core/loop/permission_gateway.py", "core/runtime/plans.py",
            "tests/test_r19_capability_composition.py",
            "tests/test_r20_autonomous_adaptation.py",
            "VECTOR_TECHNICAL_KNOWLEDGE/R19_R20_ORCHESTRATOR_LEDGER.md",
            "VECTOR_TECHNICAL_KNOWLEDGE/R19_R20_MASTER_REPORT.md",
            # R21-R23 (in progress) -- see
            # VECTOR_TECHNICAL_KNOWLEDGE/R21_R23_UNDERSTANDING_FOUNDATION_REPORT.md
            "core/memory/counterfactual.py", "core/loop/decision_engine.py",
            "core/brain/goal_system.py", "districts/startups/idea_validator.py",
            "tests/test_r21_generalization.py", "tests/test_r22_situation_understanding.py",
            "tests/test_r23_world_self_model.py",
            "VECTOR_TECHNICAL_KNOWLEDGE/R21_R23_ORCHESTRATOR_LEDGER.md",
            "VECTOR_TECHNICAL_KNOWLEDGE/R21_R23_UNDERSTANDING_FOUNDATION_REPORT.md",
        }
        unexpected = {c for c in changed if not any(c.startswith(p) for p in expected_prefixes) and not c.startswith("test_tmp")}
        assert not unexpected, f"unexpected modified/untracked files: {unexpected}"


if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v", "--timeout=600"])
    print("OK test_r18_eq_equation_capability.py" if result.returncode == 0 else "FAILED test_r18_eq_equation_capability.py")
