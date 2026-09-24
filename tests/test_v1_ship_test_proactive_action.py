"""V1 ship-test #1 (README.md's original "three tests for shipped"):
proactive, unprompted autonomous action.

Stages 1-7 of the V1 completion program (VECTOR_TECHNICAL_KNOWLEDGE/
STAGE_*.md) proved #3 (restart/persistence, Stage 5) and the underlying
mechanism of #2 (real policy/goal-progress adaptation, Stages 2/3), but
never exercised #1 directly: VECTOR taking a genuine, unprompted, and
SUCCESSFUL action with ZERO owner trigger anywhere in the call chain (no
voice, no API command, no typed message) -- purely from its own
GoalSystem, through the real end-to-end tick.

2026-09-23 rewrite (round 2, after independent re-review): the first
rewrite drove the real `_think_tick()` but had four real isolation gaps a
second review round caught:

1. It only checked `GoalSystem.generate_immediate_actions()` for ambient
   competition, but `_think_tick()` ALSO gathers candidates from the
   process-wide, file-backed `PlanStore` -- an active real plan step could
   have won instead and coincidentally satisfied the same causal-edge
   assertion. Fixed: `loop._plan_store` is pointed at an isolated, empty
   temp-file store (same technique as tests/test_stage3_goal_progress.py).
2. It mutated global `CONFIG` directly instead of through `monkeypatch`,
   leaking the change into every test that ran afterward in this process.
   Fixed: `monkeypatch.setitem`.
3. `isolated_vector_db` isolates episodic memory but not
   `EpistemicTracker`'s own separate SQLite file -- the test's real
   `DecisionEngine` was reading (and writing) the shared, unisolated,
   default epistemic database, which is what actually explained the low
   score this test works around by pre-seeding PolicyMemory (a real,
   accurate, but previously mis-attributed effect -- the docstring said
   "epistemic staleness dampening on a stone-cold instance", which isn't
   right; a stone-cold instance has ZERO belief, not a dampened one -- the
   penalty was coming from stale, unisolated, real belief data). Fixed:
   `EpistemicTracker`'s default DB path is pointed at an isolated temp
   file too, and the docstring now describes what's actually happening.
4. The `outcome:ok` CausalGraph-edge assertion is a NORMALIZED label, and
   because of a separate, now-fixed bug (see core/loop/autonomous_loop.py's
   own 2026-09-23 comment on _act_on()'s read-only-result handling) a real
   Git FAILURE could previously have been mislabeled the same way. Fixed:
   this test also spies on the real `GitBot.run()` (never replaced) to
   independently confirm the real underlying result actually carried
   concrete evidence (a real `branch` value), not just the downstream
   normalized status label.

Per .claude/rules/testing.md, `permission_gateway.py` and
`session_hydration_prompt()` are never mocked. The real gateway genuinely
is not invoked for this specific action (git_status is GREEN, and
_act_on()'s generic dispatch fallback only routes RED/YELLOW candidates
through the gateway -- see that method's own 2026-09-23 comment); this
test asserts that honestly via a spy, rather than claiming otherwise.
Everything else (GoalSystem, DecisionEngine, ContinueGate, Governor,
GitBot) runs for real against the real repo's own git_status (read-only,
safe, and already this project's own established live-verification probe
action from Stage 4/5). The ONLY boundary mocked is `git.Repo(...)` itself
-- the actual subprocess/filesystem git call -- same established boundary
as tests/test_rgd2a_probe_stability.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.city.agent_registry import AgentRegistry
from core.loop.autonomous_loop import AutonomousLoop
from core.loop.permission_gateway import PermissionGateway
from core.runtime.plans import PlanStore
from districts.coding.git_bot import GitBot


def _fake_git_status_repo() -> MagicMock:
    """Same real-handler-boundary shape as tests/test_rgd2a_probe_stability.py's
    own established fixture: just enough of gitpython's `Repo` surface for
    the real `GitBot.get_status()` to run its own real branch/diff/untracked
    logic against, without touching a real repository on disk."""
    repo = MagicMock()
    repo.head.is_detached = False
    repo.active_branch.name = "main"
    repo.active_branch.tracking_branch.return_value = None
    repo.index.diff.return_value = []
    repo.untracked_files = []
    return repo


@pytest.mark.asyncio
async def test_unprompted_goal_derived_action_really_succeeds(isolated_vector_db, tmp_path, monkeypatch):
    # 1. Isolate from GoalSystem's real hardcoded preseeded owner goals so
    # this test's own goal is the only real GoalSystem-derived candidate.
    import core.brain.goal_system as goal_system_mod
    monkeypatch.setattr(goal_system_mod, "PRESEEDED_GOALS", [])

    # 2. CONFIG mutation via monkeypatch (auto-restored), not a direct write.
    from core.config import CONFIG
    monkeypatch.setitem(CONFIG["sensing"], "defer_llm_while_owner_codes", False)

    # 3. EpistemicTracker has its own separate SQLite file, not covered by
    # isolated_vector_db -- point its default path at an isolated temp file
    # so this test's real DecisionEngine reads/writes zero unisolated,
    # shared belief history.
    import core.brain.epistemic_tracker as epistemic_mod
    monkeypatch.setattr(epistemic_mod, "_DEFAULT_DB", tmp_path / "epistemic_shiptest.db")

    # 3b (round 8 finding): _think_tick() -> _run_soft_safety_checks() lazily
    # constructs a real CounterfactualMemory(), which defaults its SQLite
    # path via core.runtime_paths.data_path() -- a real, shared,
    # process-wide database accumulating real rejection history across
    # every test run, not covered by isolated_vector_db. VECTOR_TEST_DATA_DIR
    # is the supported override (core/runtime_paths.py get_data_root());
    # set it before any CounterfactualMemory() is constructed.
    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(tmp_path))

    # 3c (round 9 finding): Governor.dispatch() logs every real dispatch to
    # the real, home-directory MerkleAuditChain (core/audit/merkle_chain.py
    # -- module-level `_chain` singleton, hardcoded path under
    # ~/.vector_ca/audit, NOT covered by VECTOR_TEST_DATA_DIR). Left
    # unpatched, this test appends a real permanent audit entry to the
    # owner's actual audit trail on every run. Isolate the same way as the
    # PlanStore singleton above.
    import core.audit.merkle_chain as merkle_chain_mod
    monkeypatch.setattr(
        merkle_chain_mod, "_chain",
        merkle_chain_mod.MerkleAuditChain(chain_file=tmp_path / "audit_chain.jsonl"),
    )

    # Real, single-agent AgentRegistry scoped to this test (same
    # established pattern as tests/test_rgd2a_probe_stability.py) so
    # Governor.dispatch() has a real GitBot to route to -- a bare test run
    # bootstraps nothing into the process-wide registry, so without this
    # the dispatch would legitimately (and correctly) report "no_agents".
    registry = AgentRegistry()
    real_gitbot = GitBot()
    registry.register(real_gitbot)
    monkeypatch.setattr("core.city.agent_registry.get_registry", lambda: registry)

    loop = AutonomousLoop()
    # 1 (continued): also isolate PlanStore -- _think_tick() gathers
    # candidates from it independently of GoalSystem, and the default
    # construction reads a real, process-wide, file-backed store.
    #
    # Round 8 (Codex) finding: setting loop._plan_store alone does NOT
    # isolate DecisionEngine._get_plan_store() (core/loop/decision_engine.py
    # 188-195), which independently calls the module-level
    # core.runtime.plans.get_plan_store() singleton and is used by
    # DecisionEngine._workload_factor() for its own candidate scoring. Both
    # readers must point at the SAME isolated store.
    isolated_plan_store = PlanStore(path=tmp_path / "plans.json")
    loop._plan_store = isolated_plan_store
    import core.runtime.plans as plans_mod
    monkeypatch.setattr(plans_mod, "_PLAN_STORE", isolated_plan_store)

    gs = loop._get_goals()
    goal_title = "Proactive ship-test probe: real repo status"
    goal_id = gs.add_goal(goal_title, horizon="SHORT", tags=["git"])

    real_actions = gs.generate_immediate_actions(limit=10)
    assert len(real_actions) == 1, (
        f"expected exactly this test's own goal-derived candidate with no "
        f"ambient competition, got {real_actions}"
    )
    assert real_actions[0]["action_type"] == "git_status"

    # The actual claim under test: confirm there is NO owner-originated
    # trigger anywhere before the tick runs.
    assert loop._pending_voice is None

    # With EpistemicTracker now genuinely isolated (see point 3 above), a
    # freshly constructed instance has NO belief at all about git_status
    # (neutral, not dampened) -- but PolicyMemory (also freshly isolated
    # via isolated_vector_db, since it's backed by the same episodic DB)
    # legitimately starts at a neutral 0.5 default too, and goal_alignment
    # for a SHORT-horizon goal with default priority isn't enough on its
    # own to clear ContinueGate's real 0.4 coherence floor. Same real,
    # established technique as Stage 4's long-horizon-autonomy
    # verification: a mature VECTOR instance would already carry real
    # policy history for its own goals; supplying it directly through the
    # real, unmodified PolicyMemory API fills a real gap in the test's OWN
    # starting conditions, not touching DecisionEngine, ContinueGate, or
    # any scoring formula.
    from core.memory.policy import PolicyMemory
    pm = PolicyMemory()
    situation_hash = pm.make_situation_hash("git_status", {"goal_id": goal_id, "title": goal_title})
    for _ in range(5):
        pm.update_from_outcome("git_status", situation_hash, 0.95)

    # Spy (not mock) on the real gateway so we can prove/disprove it was
    # invoked, without replacing its real approve/execute/audit behavior.
    real_execute = PermissionGateway.execute
    gateway_calls: list[str] = []

    async def _spy_execute(self, action):
        gateway_calls.append(action.action_type)
        return await real_execute(self, action)

    monkeypatch.setattr(PermissionGateway, "execute", _spy_execute)

    # Spy (not mock) on the real GitBot.run() so this test can independently
    # confirm the REAL underlying result -- not just the downstream
    # normalized status label a separate bug could otherwise mislabel.
    real_run = GitBot.run
    captured_results: list[dict] = []

    async def _spy_run(self, task):
        res = await real_run(self, task)
        captured_results.append(res)
        return res

    monkeypatch.setattr(GitBot, "run", _spy_run)

    # The real per-tick method, unmodified: real candidate gathering, real
    # DecisionEngine.evaluate() scoring + threshold, real ContinueGate,
    # real _act_on() dispatch, real Governor routing, real GitBot handler.
    with patch("git.Repo", return_value=_fake_git_status_repo()):
        await loop._think_tick()

    # git_status is GREEN -- _act_on()'s generic dispatch fallback (see its
    # own 2026-09-23 comment) only routes RED/YELLOW candidates through
    # PermissionGateway.execute(); GREEN dispatches straight to
    # Governor.dispatch(), same as before that fix. Stated honestly, not
    # claimed otherwise.
    assert gateway_calls == [], (
        "git_status is GREEN and is not expected to reach the gateway via "
        f"this path; got {gateway_calls}"
    )

    # Independent, concrete proof the real handler produced real success
    # evidence -- not just a normalized label.
    assert captured_results, "expected GitBot.run() to have actually been called"
    assert captured_results[0].get("branch") == "main", (
        f"expected the real GitBot.get_status() result to carry real branch "
        f"evidence; got {captured_results}"
    )

    # Real, root proof of SUCCESSFUL execution recorded via RULE 7 --
    # _act_on()'s own real `action:git_status@<state>` -> `outcome:ok`
    # CausalGraph edge.
    from core.memory.causal_graph import CausalGraph
    cg = CausalGraph()
    git_status_action_nodes = [
        n["id"] for n in cg.get_all_nodes() if str(n.get("id", "")).startswith("action:git_status@")
    ]
    assert git_status_action_nodes, "expected a real action:git_status@... CausalGraph node"

    ok_edges = [
        e for action_id in git_status_action_nodes
        for e in cg.get_outcomes(action_id)
        if e.get("to") == "outcome:ok"
    ]
    print(
        f"[behavioral evidence] unprompted git_status candidate ran through the real "
        f"_think_tick() with zero owner input and succeeded; real branch="
        f"{captured_results[0].get('branch')!r}; action nodes={git_status_action_nodes}; "
        f"outcome:ok edges={len(ok_edges)}"
    )
    assert ok_edges, (
        "expected a real action:git_status -> outcome:ok edge proving the "
        "unprompted candidate didn't just run, but genuinely SUCCEEDED "
        f"(no such edge found among: {cg.get_all_edges()})"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-s"]))
