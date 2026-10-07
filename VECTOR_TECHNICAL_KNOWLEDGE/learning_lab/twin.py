"""
VECTOR Digital Twin Lab — the twin itself.

Wires together REAL, unmodified production classes —
`core.loop.decision_engine.DecisionEngine`/`Candidate`,
`core.memory.policy.PolicyMemory`, `core.memory.episodic.EpisodicMemory`,
`core.brain.goal_system.GoalSystem`, `core.brain.epistemic_tracker.EpistemicTracker`,
`core.memory.counterfactual.CounterfactualMemory` — against the isolated
storage `isolation.IsolatedVectorEnv` provides, and produces a `DecisionTrace`.

DEPENDENCY MAP (Phase 1 of Task 78's brief — see 78_DIGITAL_TWIN_LAB.md §5 for
the full write-up):

  DIRECTLY IMPORTABLE, REAL, UNMODIFIED, ISOLATED VIA VECTOR_DB_PATH:
    - core.memory.episodic.EpisodicMemory
    - core.memory.policy.PolicyMemory
    - core.brain.goal_system.GoalSystem

  DIRECTLY IMPORTABLE, REAL, UNMODIFIED, ISOLATED VIA explicit db_path=:
    - core.brain.epistemic_tracker.EpistemicTracker
    - core.memory.counterfactual.CounterfactualMemory

  DIRECTLY IMPORTABLE, REAL, UNMODIFIED, deterministic, no LLM/network calls
  anywhere in its own evaluate()/_score_candidate() path:
    - core.loop.decision_engine.DecisionEngine / Candidate / Decision

  DELIBERATELY DISABLED (documented simplification, not a scoring mock —
  each is provably either score-irrelevant or a separate learning channel):
    - DecisionEngine._reasoning_bank  (RULE 8 text injection only; file-backed,
      non-deterministic content; never touches the 5-factor formula)
    - DecisionEngine._neural_trainer  (a SEPARATE RL side-channel fed by
      record_outcome(); never read by _score_candidate())
    - DecisionEngine._metacognition   (bias_penalty degrades to 0.0 when
      unavailable — identical to the real class's own fallback behavior)
    - DecisionEngine._context_engine  (get_world_state() output only populates
      candidate.context_snapshot, which decision_engine.py's own comment
      states "does NOT currently change the score formula itself")

  SMALL DETERMINISTIC ADAPTER (NOT part of DecisionEngine — this is real
  orchestration glue from core/loop/autonomous_loop.py that cannot safely be
  imported wholesale — see counterfactual_veto() below and
  auto_candidates_from_goals() below, each a faithful line-for-line port of
  one narrow, cited slice of that file):
    - autonomous_loop.py:1090-1126  → counterfactual_veto()
    - autonomous_loop.py:894-918    → auto_candidates_from_goals() (UPDATED
      2026-09-09 by R11 — see that function's own comment; the goal→action
      tag resolution it used to (faithfully, deliberately) reproduce as
      dead code now lives, and genuinely runs, in
      core.brain.goal_system.GoalSystem.generate_immediate_actions() —
      this adapter is now a straight pass-through of that method's output)

  EXCLUDED (out of scope for "the smallest meaningful decision surface" —
  see 78_DIGITAL_TWIN_LAB.md §5 for why each is excluded):
    - PlanStore / PlanRunner plan-step candidates (autonomous_loop.py:881-887)
    - Avatar mood nudge (autonomous_loop.py:890-899)
    - SwarmCoordinator consensus veto (autonomous_loop.py:1057-1085)
    - ThreatDetector scan (autonomous_loop.py:1128-1133)
    - The entire autonomous_loop.py observe/sense/act/reflect tick machinery,
      event bus, scheduler, websockets, hardware sensing
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from isolation import IsolatedVectorEnv
from scenario import Scenario, CandidateSpec, GoalSpec
from trace import CandidateTrace, DecisionTrace


class _NullContextEngine:
    """Stand-in for DecisionEngine._context_engine. See module docstring —
    get_world_state() output does not affect the score formula, so a
    deterministic empty dict removes wall-clock non-determinism from every
    trace with zero effect on any score component."""
    def get_world_state(self, query: str | None = None) -> dict:
        return {}


def make_situation_hash(action_type: str, params: dict) -> str:
    """The same hash a real Candidate's policy lookup would get, computable
    here as a free function without needing a DecisionEngine instance.

    M1e (2026-09-09): this used to be a hand-duplicated re-implementation of
    the formula (`f"{action_type}:{sorted(params.items())}"`), which fell
    silently out of sync when Task 89 (D2) introduced PolicyMemory's own
    canonical `"v2:"`-prefixed hash. Every write through this lab function
    landed under a key `DecisionEngine`'s real scoring path never looks up,
    so `get_score()` always returned `DEFAULT_SCORE` regardless of any real
    write -- root-caused as the cause of
    `test_policy_reward_moves_score_in_the_expected_direction`'s failure and
    of `level4_experiment.py`'s own "FAIL at RETRIEVAL" verdict, both
    documented in
    VECTOR_TECHNICAL_KNOWLEDGE/M1E_DEVELOPMENT_FOUNDATION_REPORT.md. Now
    delegates to the real function directly, so it can never drift again."""
    from core.memory.policy import PolicyMemory
    return PolicyMemory.make_situation_hash(action_type, params)


# ── Adapter 1: goal actions -> real Candidates (autonomous_loop.py:894-918) ──
#
# UPDATED 2026-09-09 (R11 — Native Goal Strategy Candidate Generation; see
# VECTOR_TECHNICAL_KNOWLEDGE/R11_NATIVE_GOAL_STRATEGY_CANDIDATE_GENERATION_REPORT.md):
# this used to deliberately reproduce a dead `_TAG_TO_ACTION` lookup here
# (per the original 78_DIGITAL_TWIN_LAB.md §7 note this comment replaces),
# because `generate_immediate_actions()`'s own returned dicts never carried
# a "tags" key in production at the time, so the twin's job — faithfully
# reproducing REAL behavior, not a hand-fixed version of it — meant
# reproducing that dead-code path too.
#
# R11 fixed the underlying bottleneck: `core.brain.goal_system.
# GoalSystem.generate_immediate_actions()` now resolves each goal's own
# tags into one or more concrete action_type strategies ITSELF (see that
# method's docstring), so every action dict's `"action_type"` key already
# carries the final, correct value — including, for a goal like
# `g_daily_commit` (tags=["git","habit","coding"]), MULTIPLE distinct
# action dicts for the ONE goal (git_status AND code_task), which is
# exactly the genuine candidate diversity this whole lab exists to help
# verify. Reproducing the OLD dead remap loop here would now be reproducing
# behavior that no longer exists in production — the opposite of this
# function's stated purpose — so it has been removed, matching the
# equivalent, identically-motivated change in
# `core/loop/autonomous_loop.py::_think_tick()`.
def auto_candidates_from_goals(goal_system) -> list[CandidateSpec]:
    """Real `GoalSystem.generate_immediate_actions()` + the exact
    autonomous_loop.py `_think_tick()` action-dict → Candidate-field
    translation (now a straight 1:1 pass-through, since
    `generate_immediate_actions()` already resolves the final action_type
    per strategy — see the module comment above)."""
    actions = goal_system.generate_immediate_actions(limit=4)
    out: list[CandidateSpec] = []
    for a in actions:
        out.append(CandidateSpec(
            action_type=a["action_type"],
            params={"goal_id": a["goal_id"], "title": a["title"]},
            goal_ids=[a["goal_id"]],
            urgency={"high": 0.9, "medium": 0.5, "low": 0.2}.get(a.get("urgency", "low"), 0.5),
            confidence=0.7,
            source="think_loop",
        ))
    return out


# ── Adapter 2: post-selection counterfactual veto (autonomous_loop.py:1090-1126) ──

@dataclass
class VetoResult:
    vetoed: bool
    score: float
    reason: str
    caution: bool = False


def counterfactual_veto(cf_memory, winner_action_type: str, winner_params: dict,
                         threshold: float = 0.7) -> VetoResult:
    """Faithful port of autonomous_loop.py:1090-1126. Not part of
    DecisionEngine.evaluate() in production either — this runs AFTER a
    winner is already selected, which is exactly why a paired experiment
    must check ranking-before-veto separately from action-taken-after-veto
    (see experiments.py). Also reproduces the real reward=0.05 hardcoded
    policy penalty on a veto (autonomous_loop.py:1115, already documented
    in Task 71/72 — cited, not rediscovered)."""
    import json
    proposal = f"{winner_action_type} {json.dumps(winner_params, default=str)}"
    should_avoid, score, reason = cf_memory.should_avoid(proposal, threshold=threshold)
    if should_avoid and score > threshold:
        cf_memory.record_rejection(
            decision_id=winner_action_type,
            proposal=proposal,
            reason=f"auto-blocked: similar to past rejection (score={score:.2f})",
        )
        return VetoResult(vetoed=True, score=score, reason=reason)
    if 0.4 < score <= threshold and reason:
        return VetoResult(vetoed=False, score=score, reason=reason, caution=True)
    return VetoResult(vetoed=False, score=score, reason="")


# ── The twin itself ──────────────────────────────────────────────────────────

def build_isolated_engine(env: IsolatedVectorEnv):
    """Construct a REAL DecisionEngine wired to isolated storage. See the
    module docstring's dependency map for exactly what is real vs disabled
    and why."""
    from core.loop.decision_engine import DecisionEngine
    from core.memory.policy import PolicyMemory
    from core.memory.episodic import EpisodicMemory
    from core.brain.goal_system import GoalSystem
    from core.brain.epistemic_tracker import EpistemicTracker
    from core.runtime.plans import PlanStore

    engine = DecisionEngine()
    engine._policy = PolicyMemory()
    engine._memory = EpisodicMemory()
    engine._goals = GoalSystem()
    engine._epistemic = EpistemicTracker(db_path=env.paths.epistemic_db)
    engine._plan_store = PlanStore(path=env.paths.plan_store)
    engine._reasoning_bank = False
    engine._neural_trainer = False
    engine._metacognition = False
    engine._context_engine = _NullContextEngine()
    return engine


def build_isolated_counterfactual(env: IsolatedVectorEnv):
    from core.memory.counterfactual import CounterfactualMemory
    return CounterfactualMemory(db_path=str(env.paths.counterfactual_db))


def _apply_goal_overrides(engine, goals: list[GoalSpec]) -> None:
    """Replace GoalSystem's seeded goal set with an explicit, deterministic
    one, then persist (mirrors GoalSystem's own _persist() convention)."""
    engine._goals._goals = [
        {
            "id": g.id, "title": g.title, "horizon": g.horizon,
            "priority": g.priority, "status": g.status, "progress": g.progress,
            "tags": list(g.tags),
        }
        for g in goals
    ]
    engine._goals._persist()


def _apply_policy_updates(engine, updates) -> list[dict]:
    applied = []
    for u in updates:
        sit_hash = make_situation_hash(u.action_type, u.params)
        engine._policy.update_from_outcome(u.action_type, sit_hash, u.reward)
        applied.append({
            "action_type": u.action_type, "params": u.params,
            "situation_hash": sit_hash, "reward": u.reward, "note": u.note,
        })
    return applied


def _apply_counterfactual_rejections(cf_memory, rejections) -> dict:
    import datetime
    applied = []
    for r in rejections:
        rid = cf_memory.record_rejection(
            decision_id=r.decision_id, proposal=r.proposal,
            reason=r.reason, context=r.context,
        )
        if r.created_at_days_ago > 0:
            backdated = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=r.created_at_days_ago)
            ).isoformat()
            with cf_memory._lock:
                cf_memory._conn.execute(
                    "UPDATE rejections SET created_at=? WHERE id=?", (backdated, rid)
                )
                cf_memory._conn.commit()
        applied.append({"id": rid, "proposal": r.proposal, "reason": r.reason,
                         "days_ago": r.created_at_days_ago})
    return {"count": len(applied), "rejections": applied}


def _apply_epistemic_beliefs(engine, beliefs) -> list[dict]:
    import datetime
    applied = []
    for b in beliefs:
        engine._epistemic.update_belief(b.claim_id, b.value, b.confidence, b.source, b.ttl_hours)
        if b.age_hours_override is not None:
            backdated = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(hours=b.age_hours_override)
            ).isoformat()
            engine._epistemic._conn.execute(
                "UPDATE claims SET created_at=?, last_seen_at=? WHERE id=?",
                (backdated, backdated, b.claim_id),
            )
            engine._epistemic._conn.commit()
            # keep the in-process cache in sync with the row we just backdated
            if b.claim_id in engine._epistemic._beliefs:
                engine._epistemic._beliefs[b.claim_id]["created_at"] = backdated
        applied.append({"claim_id": b.claim_id, "confidence": b.confidence,
                         "age_hours_override": b.age_hours_override})
    return applied


class DigitalTwin:
    """Runs one Scenario against a freshly isolated environment and returns
    a DecisionTrace. Use `run()` for a self-contained single run; use
    `run_in_env()` when the caller needs to control env lifetime across
    multiple runs (persistence/restart experiments, paired comparisons that
    must share pre-seeded state, etc.)."""

    def run(self, scenario: Scenario, run_id: str | None = None) -> DecisionTrace:
        with IsolatedVectorEnv(run_id=run_id) as env:
            return self.run_in_env(env, scenario)

    def run_in_env(self, env: IsolatedVectorEnv, scenario: Scenario) -> DecisionTrace:
        import asyncio
        from core.loop.decision_engine import Candidate

        try:
            engine = build_isolated_engine(env)
            cf_memory = build_isolated_counterfactual(env)

            if scenario.goals is not None:
                _apply_goal_overrides(engine, scenario.goals)

            policy_inputs = _apply_policy_updates(engine, scenario.policy_updates)
            counterfactual_inputs = _apply_counterfactual_rejections(
                cf_memory, scenario.counterfactual_rejections
            )
            epistemic_inputs = _apply_epistemic_beliefs(engine, scenario.epistemic_beliefs)

            if scenario.candidates == "auto":
                specs = auto_candidates_from_goals(engine._goals)
            else:
                specs = scenario.candidates

            real_candidates = [
                Candidate(
                    action_type=s.action_type, params=s.params, goal_ids=s.goal_ids,
                    confidence=s.confidence, urgency=s.urgency, timing_score=s.timing_score,
                    estimated_cost_inr=s.estimated_cost_inr, source=s.source,
                )
                for s in specs
            ]
            generated_candidates = [
                {"action_type": c.action_type, "params": c.params, "goal_ids": c.goal_ids,
                 "confidence": c.confidence, "urgency": c.urgency,
                 "timing_score": c.timing_score, "estimated_cost_inr": c.estimated_cost_inr,
                 "source": c.source}
                for c in real_candidates
            ]

            decision = asyncio.run(engine.evaluate(real_candidates))

            veto = VetoResult(vetoed=False, score=0.0, reason="")
            if scenario.apply_counterfactual_veto and decision.evaluated:
                veto = counterfactual_veto(
                    cf_memory, decision.winner.action_type, decision.winner.params
                )

            candidate_traces = [
                CandidateTrace(
                    action_type=c.action_type, params=c.params, goal_ids=c.goal_ids,
                    confidence=c.confidence, urgency=c.urgency, timing_score=c.timing_score,
                    estimated_cost_inr=c.estimated_cost_inr, source=c.source,
                    goal_alignment=c.goal_alignment, policy_score=c.policy_score,
                    total_score=c.total_score, score_components=c.reasoning_chain,
                    reasoning_steps=c.reasoning_steps,
                    rejected=(c is not decision.winner) if decision.all_candidates else True,
                    rejection_reason=(veto.reason if (c is decision.winner and veto.vetoed) else ""),
                )
                for c in decision.all_candidates
            ]

            selected_action = decision.winner.action_type if decision.evaluated else None
            selected_params = decision.winner.params if decision.evaluated else {}
            rejected_actions = [c.action_type for c in candidate_traces if c.rejected]

            return DecisionTrace(
                run_id=env.run_id,
                scenario_label=scenario.label,
                situation=scenario.situation,
                active_goals=engine._goals.get_active_goals(),
                generated_candidates=generated_candidates,
                memory_inputs={"episodic_store_calls": len(decision.all_candidates)},
                policy_inputs=policy_inputs,
                counterfactual_inputs=counterfactual_inputs,
                epistemic_inputs=epistemic_inputs,
                candidates=candidate_traces,
                selected_action=selected_action,
                selected_params=selected_params,
                rejected_actions=rejected_actions,
                decision_reason=decision.reasoning,
                counterfactual_vetoed=veto.vetoed,
                veto_reason=veto.reason,
            )
        except Exception as e:
            import traceback
            return DecisionTrace(
                run_id=env.run_id, scenario_label=scenario.label, situation=scenario.situation,
                active_goals=[], generated_candidates=[], memory_inputs={}, policy_inputs=[],
                counterfactual_inputs={}, epistemic_inputs=[], candidates=[],
                selected_action=None, selected_params={}, rejected_actions=[],
                decision_reason="", counterfactual_vetoed=False, veto_reason="",
                error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )
