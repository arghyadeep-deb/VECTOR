import sys
import json
import uuid
import datetime
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG


# Maps goal horizon to a gateway-registered action type so every generated
# action passes the GREEN/YELLOW gate without being classified as UNKNOWN.
# SHORT → "research_topic" (GREEN, safe read-only query)
# MID   → "analyze_progress" (GREEN, analysis only)
# LONG  → "analyze_progress" (GREEN, analysis only)
# This remains the FALLBACK for a goal whose tags map to no known strategy
# below — every goal always gets at least this one candidate.
GOAL_ACTION_MAP: dict[str, str] = {
    "SHORT": "research_topic",
    "MID":   "analyze_progress",
    "LONG":  "analyze_progress",
}

# R11 (Native Goal Strategy Candidate Generation) — the trustworthy subset of
# goal tags this codebase already knows how to route to a real, concrete
# action_type. This dict used to live in core/loop/autonomous_loop.py's
# _think_tick(), where it was genuinely DEAD CODE: generate_immediate_actions()
# never propagated a goal's own "tags" field into the returned action dicts,
# so the remap loop that consumed it could never fire (see
# VECTOR_TECHNICAL_KNOWLEDGE/R11_NATIVE_GOAL_STRATEGY_CANDIDATE_GENERATION_REPORT.md
# for the full audit trail). It has moved here because "which action_type(s)
# genuinely apply to this goal's content" is goal semantics (RULE 6), not
# orchestration -- and this is the one place that can decide to propose
# MULTIPLE distinct candidates for one goal, which a single-pass remap loop
# structurally cannot (it can only ever replace one action_type with
# another).
#
# Every VALUE below is an already-existing, already-permission-classified
# action_type (core/config.py's PermissionConfig.green/yellow/red) with an
# already-wired Governor route (core/city/governor.py's DISTRICT_TASK_MAP) --
# moving this table does not invent a single new action type, permission
# tier, or execution path. Candidate generation only ever creates OPTIONS;
# it has no bearing on what tier an action_type is classified at.
_TAG_TO_ACTION_TYPE: dict[str, str] = {
    "kiit": "check_attendance", "attendance": "check_attendance",
    "git": "git_status", "coding": "code_task", "build": "code_task",
    "research": "daily_digest", "ml": "search_arxiv", "karpathy": "search_arxiv",
    "learning": "search_arxiv", "finance": "monthly_report", "health": "check_fatigue",
    "placement": "search_web", "interview": "search_web", "dsa": "search_web",
    "memory": "consolidate", "reflection": "daily_review", "debug": "code_task",
    "fix": "code_task", "implement": "code_task", "write_code": "code_task",
    "code_review": "code_review_vc", "refactor": "code_task",
    # R18-EQ (2026-09-10) — the Equation/wealth goals (g_first_revenue,
    # g_equation_portfolio) previously had ZERO real strategies: none of
    # their tags ("revenue","equation","wedge","startups","portfolio")
    # mapped to anything, so both fell through to the generic horizon
    # fallback (analyze_progress) every cycle -- see
    # VECTOR_TECHNICAL_KNOWLEDGE/R12_NATIVE_STRATEGY_SEMANTICS_REPORT.md
    # section 6, which explicitly (and correctly) refused to invent a
    # mapping for these tags rather than fabricate fake diversity.
    # This adds exactly two, deliberately narrow, semantically-grounded
    # mappings -- not "revenue -> arbitrary action" (which R12 rejected),
    # but tags that name a REAL, ALREADY-EXISTING VECTOR capability the
    # goal's own text already points at:
    #   "wedge" -> script: g_first_revenue's own title literally says
    #     'wedge: AI content ops for creators' -- districts/content/
    #     script_generator.py::ScriptGenerator is real, already-shipped
    #     content-ops machinery, not invented for this mapping.
    #   "startups" -> idea_validate: districts/startups/idea_validator.py
    #     ::IdeaValidator is real, pre-existing venture-validation
    #     machinery ("Validate this startup idea... Governing law -- The
    #     Equation" -- its own prompt already cites the same Equation
    #     doctrine these goals are governed by). "produce content" vs
    #     "validate the idea first" is a genuine strategic choice with
    #     different real consequences, not a cosmetic rephrasing.
    # Both action_types already existed, already had real handlers, and
    # already had real, exact-match Governor routing (DISTRICT_TASK_MAP)
    # -- they were simply never added to any permission tier (see
    # core/config.py's R18-EQ comment), making them UNKNOWN-and-therefore-
    # always-blocked despite being fully built. No new action type, no new
    # handler, no new district was created.
    "wedge": "script", "startups": "idea_validate",
}

# R12 (Native Strategy Semantics, 2026-09-09) — legitimate SECOND strategies
# for tags that, via _TAG_TO_ACTION_TYPE alone, would collapse an entire
# goal to exactly one action_type even when several of its tags are known
# (e.g. a goal tagged ["coding","build"] previously produced only
# "code_task" twice-over, not two distinct options). A separate, additive
# table -- rather than widening _TAG_TO_ACTION_TYPE's own values from `str`
# to `str | list[str]` -- was chosen deliberately: it makes zero changes to
# the existing, already-adversarially-tested primary table (R11's own tests
# assume scalar values, e.g. `set(_TAG_TO_ACTION_TYPE.values())`), and it
# keeps "the one canonical action for this tag" (R11) structurally distinct
# from "an additional legitimate alternative" (R12).
#
# Each mapping below is a genuinely DIFFERENT strategic approach to the
# goal, not a cosmetic rephrasing of the same action -- see
# VECTOR_TECHNICAL_KNOWLEDGE/R12_NATIVE_STRATEGY_SEMANTICS_REPORT.md
# section 7 for the full semantic justification behind each one:
#
#   "coding"/"build" -> read_code: read/verify the code (GREEN, read-only,
#     routed to the "coding" district, real handlers in
#     districts/coding/coding_tools.py + architect_bot.py) is a genuinely
#     distinct alternative to code_task (RED, modify/implement, routed via
#     the VectorCode execution bridge) -- "look before touching" is a real
#     strategic choice with different cost/risk/urgency, not a relabeling.
#   "karpathy" -> code_task: the Karpathy playlist is explicitly a
#     hands-on coding curriculum (districts/karpathy_lab/code_typer.py
#     exists specifically to type along with it) -- "practice by writing
#     code" is a real alternative to "search_arxiv" (research more before
#     practicing), not the same action under a different name.
#   "dsa" -> code_task: DSA interview prep fundamentally means solving
#     problems by writing code -- "practice" is a real alternative to
#     "search_web" (research prep material).
#
# Every value here, like every value in _TAG_TO_ACTION_TYPE, is an
# already-existing, already-permission-classified, already-Governor-routed
# action_type. No new action type, permission tier, or execution path is
# introduced by this table.
_TAG_TO_ADDITIONAL_ACTION_TYPE: dict[str, str] = {
    "coding": "read_code",
    "build": "read_code",
    "karpathy": "code_task",
    "dsa": "code_task",
}

# Bounds how many distinct tag-derived strategies ONE goal can propose in a
# single generate_immediate_actions() call, independent of the caller's own
# `limit` (which caps the TOTAL across all goals). Protects against a goal
# tagged with many distinct-action-type tags flooding the decision with an
# unbounded candidate set for a single goal alone. 3 comfortably covers every
# real PRESEEDED_GOALS case (richest today, post-R12: 3 distinct types, for
# g_daily_commit's ["git","habit","coding"] -> git_status + code_task +
# read_code) with zero headroom to spare -- widen deliberately, not by
# accident, if a future goal legitimately needs a 4th.
_MAX_STRATEGIES_PER_GOAL = 3


def _tag_derived_action_types(tags) -> list[str]:
    """Return the distinct, order-stable, KNOWN action_types this goal's own
    tags legitimately map to via `_TAG_TO_ACTION_TYPE` (the one canonical
    action per tag) and `_TAG_TO_ADDITIONAL_ACTION_TYPE` (R12's genuinely
    distinct second strategy for a subset of those tags) -- or `[]` if none
    of its tags are in either trustworthy table (the caller then falls back
    to `GOAL_ACTION_MAP`).

    Safety, by construction (no try/except needed for any of these):
    - Unknown tags are silently ignored (plain dict `.get()`).
    - Non-string / malformed / unhashable tags (a nested list or dict
      accidentally stored as a "tag") are silently skipped via the
      `isinstance(tag, str)` guard -- `tag in _TAG_TO_ACTION_TYPE` is never
      attempted on anything that could raise.
    - `tags` itself being `None`, missing, or a non-list is tolerated
      (`tags or []`) -- iterating a stray string here only ever hits its
      individual characters, none of which can collide with a real
      multi-character tag key, so this degrades to "no known tags", never a
      crash or a false match.
    - Duplicate tags, several different tags that map to the SAME
      action_type, or a tag whose additional strategy duplicates another
      tag's primary one, all collapse to exactly ONE entry: a
      dict-as-ordered-set is used (not a plain `set`) so the result is
      deterministic across runs for the same goal, rather than depending on
      hash-randomized set iteration order.
    - Bounded to `_MAX_STRATEGIES_PER_GOAL` distinct types.
    """
    seen: dict[str, None] = {}
    for tag in (tags or []):
        if not isinstance(tag, str):
            continue
        action_type = _TAG_TO_ACTION_TYPE.get(tag)
        if action_type is not None:
            seen[action_type] = None
        additional = _TAG_TO_ADDITIONAL_ACTION_TYPE.get(tag)
        if additional is not None:
            seen[additional] = None
    return list(seen)[:_MAX_STRATEGIES_PER_GOAL]

PRESEEDED_GOALS = [
    {
        "id": "g_kiit_attendance",
        "title": "Maintain KIIT attendance above 75%",
        "horizon": "LONG",
        "priority": 10,
        "status": "active",
        "progress": 0.0,
        "tags": ["kiit", "academic"],
    },
    {
        "id": "g_karpathy_30",
        "title": "Complete Karpathy playlist — 30 min/day",
        "horizon": "MID",
        "priority": 9,
        "status": "active",
        "progress": 0.0,
        "tags": ["learning", "ml", "karpathy"],
    },
    {
        "id": "g_vector_phase1",
        "title": "Complete VECTOR Phase 1 — 8 core districts",
        "horizon": "MID",
        "priority": 10,
        "status": "active",
        "progress": 0.25,
        "tags": ["vector", "coding", "build"],
    },
    {
        "id": "g_placement_prep",
        "title": "KIIT placement preparation — DSA + System Design",
        "horizon": "LONG",
        "priority": 8,
        "status": "active",
        "progress": 0.0,
        "tags": ["placement", "dsa", "interview"],
    },
    {
        "id": "g_daily_commit",
        "title": "Commit code every single day — no exceptions",
        "horizon": "SHORT",
        "priority": 7,
        "status": "active",
        "progress": 0.0,
        "tags": ["git", "habit", "coding"],
    },
    # The Equation (added 2026-07-08) — W = Σ O×R×M, see Brain vault Blueprint/(C) The Equation — Top 100 Wealth Pattern.md
    {
        "id": "g_first_revenue",
        "title": "First ₹1 of product revenue from a stranger — wedge: AI content ops for creators (customer #1: father's accounts)",
        "horizon": "MID",
        "priority": 10,
        "status": "active",
        "progress": 0.0,
        "tags": ["revenue", "equation", "wedge", "startups"],
    },
    {
        "id": "g_equation_portfolio",
        "title": "Equation portfolio: graduate product 1 (₹1L+/month × 3 months, ≤5 hrs/week owner time, churn <10%) before starting product 2",
        "horizon": "LONG",
        "priority": 9,
        "status": "active",
        "progress": 0.0,
        "tags": ["equation", "portfolio", "startups"],
    },
]


class GoalSystem:
    """
    3-horizon goal management: LONG (months), MID (weeks), SHORT (days).
    RULE 6 — planner.py reads generate_immediate_actions(). Not world state. Goals.
    Pre-seeded with Arghyadeep's real goals on first run.
    """

    def __init__(self):
        self._goals: list[dict] = []
        self._memory = None
        self._load_or_seed()
        logger.info(f"[VECTOR][goal_system] initialized — {len(self._goals)} goals")

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    def _load_or_seed(self):
        """Load goals from semantic memory. Seed with pre-seeded goals if empty."""
        try:
            mem = self._get_memory()
            stored = mem.recall_fact("goals_v1")
            if stored and stored.get("value"):
                self._goals = json.loads(stored["value"])
                merged = self._merge_new_seeds()
                if merged:
                    logger.info(f"[VECTOR][goal_system] merged {merged} new seed goals into stored set")
                logger.info(f"[VECTOR][goal_system] loaded {len(self._goals)} goals from memory")
                return
        except Exception as e:
            logger.warning(f"[VECTOR][goal_system] load failed, using seeds: {e}")

        self._goals = [g.copy() for g in PRESEEDED_GOALS]
        self._persist()
        logger.info(f"[VECTOR][goal_system] seeded {len(self._goals)} goals")

    def _merge_new_seeds(self) -> int:
        """Append PRESEEDED_GOALS added after first seeding (matched by id), so
        already-persisted installs pick up new seed goals instead of ignoring them."""
        existing_ids = {g.get("id") for g in self._goals}
        new = [g.copy() for g in PRESEEDED_GOALS if g["id"] not in existing_ids]
        if new:
            self._goals.extend(new)
            self._persist()
        return len(new)

    def _persist(self):
        try:
            mem = self._get_memory()
            mem.remember("goals_v1", json.dumps(self._goals), "goals", 1.0)
        except Exception as e:
            logger.error(f"[VECTOR][goal_system] persist failed: {e}")

    # Max days without a progress update before a goal is auto-expired
    _STALE_DAYS: dict[str, int] = {"SHORT": 7, "MID": 30, "LONG": 90}

    def _prune_expired(self) -> int:
        """Mark stale and past-due goals as expired. Returns count pruned."""
        now = datetime.datetime.now(datetime.timezone.utc)
        pruned = 0
        for goal in self._goals:
            if goal.get("status") != "active":
                continue
            # Explicit due_date past → expire
            due = goal.get("due_date")
            if due:
                try:
                    due_dt = datetime.datetime.fromisoformat(due)
                    if due_dt.tzinfo is None:
                        due_dt = due_dt.replace(tzinfo=datetime.timezone.utc)
                    if now > due_dt:
                        goal["status"] = "expired"
                        goal["expired_at"] = now.isoformat()
                        logger.info(
                            "[VECTOR][goal_system] goal expired (past due): {} — {}",
                            goal["id"], goal["title"],
                        )
                        pruned += 1
                        continue
                except Exception as e:
                    logger.warning("[VECTOR][goal_system] due_date parse failed for goal {}: {}", goal.get("id"), e)
            # Stale: no update in horizon-appropriate days with zero progress
            last = goal.get("last_updated") or goal.get("created_at")
            if last:
                try:
                    last_dt = datetime.datetime.fromisoformat(last)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=datetime.timezone.utc)
                    stale_days = self._STALE_DAYS.get(goal.get("horizon", "LONG"), 90)
                    if (now - last_dt).days > stale_days and goal.get("progress", 0) == 0.0:
                        goal["status"] = "expired"
                        goal["expired_at"] = now.isoformat()
                        logger.info(
                            "[VECTOR][goal_system] goal expired (stale {}d): {} — {}",
                            stale_days, goal["id"], goal["title"],
                        )
                        pruned += 1
                except Exception as e:
                    logger.warning("[VECTOR][goal_system] staleness check failed for goal {}: {}", goal.get("id"), e)
        if pruned:
            self._persist()
        return pruned

    def _enforce_completion_invariant(self) -> int:
        """RR-2 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
        RR2_MEANINGFUL_UTILITY_REPORT.md): `update_goal_progress()`'s own
        unconditional rule -- progress >= 1.0 forces status="completed" --
        IS this class's own, already-intended completion semantics (see
        that method's docstring; untouched here). RG-D/RR-0 found
        `g_daily_commit` persisted with progress=1.0 while status remained
        "active", a combination `update_goal_progress()` itself can never
        produce in a single call, and `goals_v1` (`self._persist()`) is the
        only writer anywhere in this codebase (confirmed by exhaustive
        grep, both at Task 89C and again for RR-2) -- so this state can
        only have arisen from a historical runtime sequence, not from any
        currently-reachable code path. See the report's own Section 7 for
        the forensic trace (best-effort; not fully reconstructable from
        git history alone, which tracks code, not past runtime DB writes).

        Rather than silently patch the database with a one-off script,
        this defensively re-applies the EXISTING, authoritative writer's
        own rule at the authoritative read boundary every active-goal
        lookup already goes through -- self-healing any goal found in
        this exact state via the same sanctioned method that would have
        produced a consistent result had it been the sole path all along.
        Never a raw field mutation; never a new writer.
        """
        healed = 0
        for goal in self._goals:
            if goal.get("status") == "active" and float(goal.get("progress", 0.0) or 0.0) >= 1.0:
                gid, progress = goal["id"], float(goal["progress"])
                logger.warning(
                    "[VECTOR][goal_system] completion invariant violated: '{}' had "
                    "progress={} status=active -- correcting via update_goal_progress() (RR-2)",
                    gid, progress,
                )
                self.update_goal_progress(gid, progress, note="RR-2 completion invariant enforcement")
                healed += 1
        return healed

    def get_active_goals(self, horizon: str | None = None) -> list[dict]:
        """Return active goals sorted by priority. Prunes expired goals first."""
        self._prune_expired()
        self._enforce_completion_invariant()
        goals = [g for g in self._goals if g.get("status") == "active"]
        if horizon:
            goals = [g for g in goals if g.get("horizon") == horizon.upper()]
        return sorted(goals, key=lambda g: g.get("priority", 0), reverse=True)

    def get_expired_goals(self) -> list[dict]:
        """Return all expired goals for observability. No side effects."""
        return [g for g in self._goals if g.get("status") == "expired"]

    def generate_immediate_actions(self, limit: int = 5) -> list[dict]:
        """
        RULE 6 — Planner reads this. Not world state. Not user commands. Goals.
        Returns SHORT-horizon actions and kickstarters for stalled LONG/MID goals.

        R11 (Native Goal Strategy Candidate Generation): when a goal's own
        `tags` field maps to one or more KNOWN, legitimate action_types (via
        `_tag_derived_action_types()` — see that function's own docstring
        for the exact trust/safety rules), one action dict is emitted PER
        distinct strategy — e.g. a goal tagged `["git", "coding"]` proposes
        BOTH a `git_status` check and a `code_task`, giving DecisionEngine a
        genuine choice instead of a single horizon-derived default. A goal
        whose tags map to nothing known falls back to the original
        `GOAL_ACTION_MAP` horizon default, exactly as before this change —
        this is a strict superset of the prior behavior (every goal that
        previously produced exactly one action dict still does, unless its
        tags are now recognized), never a narrower one.
        """
        actions = []

        for goal in self.get_active_goals("SHORT"):
            strategies = _tag_derived_action_types(goal.get("tags")) or [
                GOAL_ACTION_MAP.get("SHORT", "research_topic")
            ]
            for action_type in strategies:
                actions.append({
                    "goal_id": goal["id"],
                    "title": goal["title"],
                    "action": action_type,
                    "action_type": action_type,
                    "urgency": "high",
                    "source": "SHORT_goal",
                })

        for goal in self.get_active_goals():
            if goal.get("progress", 0) == 0.0 and goal["horizon"] in ("LONG", "MID"):
                strategies = _tag_derived_action_types(goal.get("tags")) or [
                    GOAL_ACTION_MAP.get(goal["horizon"], "analyze_progress")
                ]
                for action_type in strategies:
                    actions.append({
                        "goal_id": goal["id"],
                        "title": f"Start: {goal['title']}",
                        "action": action_type,
                        "action_type": action_type,
                        "urgency": "medium",
                        "source": f"{goal['horizon']}_unstarter",
                    })

        return actions[:limit]

    def update_goal_progress(self, goal_id: str, progress: float, note: str = "") -> bool:
        """Update progress (0.0-1.0). Auto-completes at 1.0."""
        for goal in self._goals:
            if goal["id"] == goal_id:
                goal["progress"] = max(0.0, min(1.0, progress))
                if progress >= 1.0:
                    goal["status"] = "completed"
                    logger.info(f"[VECTOR][goal_system] GOAL COMPLETED: {goal['title']}")
                goal["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                if note:
                    goal["last_note"] = note
                self._persist()
                return True
        logger.warning(f"[VECTOR][goal_system] goal not found: {goal_id}")
        return False

    def add_goal(
        self,
        title: str,
        horizon: str,
        priority: int = 5,
        tags: list[str] | None = None,
        due_date: str | None = None,
    ) -> str:
        """Add a new goal. Returns goal_id. due_date: ISO-8601 string (optional)."""
        goal_id = f"g_{uuid.uuid4().hex[:8]}"
        entry: dict = {
            "id": goal_id,
            "title": title,
            "horizon": horizon.upper(),
            "priority": priority,
            "status": "active",
            "progress": 0.0,
            "tags": tags or [],
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if due_date:
            entry["due_date"] = due_date
        self._goals.append(entry)
        self._persist()
        logger.info(f"[VECTOR][goal_system] new goal: {goal_id} — {title}")

        # Trigger plan decomposition for MID/LONG goals (fire-and-forget)
        if horizon.upper() in ("MID", "LONG"):
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                if loop is not None:
                    loop.create_task(self._decompose_to_plan(goal_id, title))
            except RuntimeError:
                pass  # no running loop — plan will be created on next think tick

        return goal_id

    async def _decompose_to_plan(self, goal_id: str, title: str) -> None:
        """Decompose a goal into a multi-step plan. Called when MID/LONG goals are added."""
        try:
            from core.runtime.plans import decompose_goal_to_plan, get_plan_store
            plan = await decompose_goal_to_plan(goal_id, title, proposed_by="goal_system")
            if plan is not None:
                plan.status = "active"
                plan.record_event("activated", f"Auto-activated for goal {goal_id}")
                get_plan_store().add(plan)
                logger.info(f"[VECTOR][goal_system] plan {plan.id} created for goal {goal_id} ({len(plan.steps)} steps)")
        except Exception as e:
            logger.warning(f"[VECTOR][goal_system] plan decomposition failed for {goal_id}: {e}")

    def complete_goal(self, goal_id: str) -> bool:
        return self.update_goal_progress(goal_id, 1.0)

    def get_goal_summary(self) -> str:
        """Formatted goal summary for session hydration context."""
        lines = []
        for h in ("SHORT", "MID", "LONG"):
            goals = self.get_active_goals(h)
            if goals:
                titles = ", ".join(g["title"][:40] for g in goals[:2])
                lines.append(f"{h}: {titles}")
        return " | ".join(lines) if lines else "No active goals"


if __name__ == "__main__":
    import os
    import tempfile

    sys.stdout.reconfigure(encoding="utf-8")

    # R12 (2026-09-09): this self-test used to construct a real GoalSystem()
    # and call mutating methods (update_goal_progress, add_goal) against
    # whatever goal store VECTOR_DB_PATH resolved to -- which, without this
    # override, is the OWNER'S REAL PRODUCTION goal store (core.config's
    # module-level dotenv load, triggered by the `from core.config import
    # CONFIG` at the top of this very file, already sets os.environ
    # ["VECTOR_DB_PATH"] from .env's own real "vector_memory.db" default
    # by the time this __main__ block runs -- an `if "VECTOR_DB_PATH" not
    # in os.environ` guard here is therefore always false and a no-op; the
    # override below must be UNCONDITIONAL). Running this file directly
    # already polluted real goal data TWICE during this program (R11's own
    # incident, and a second one caused by an earlier, insufficiently
    # verified version of this exact guard -- see
    # VECTOR_TECHNICAL_KNOWLEDGE/COGNITIVE_EVOLUTION_ORCHESTRATOR.md M1b
    # for the full disclosure). Forcing an isolated DB here keeps this a
    # REAL, unmocked end-to-end test of GoalSystem's own logic per this
    # repo's code-style convention, without that hazard.
    _tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    _tmp_db.close()
    os.environ["VECTOR_DB_PATH"] = _tmp_db.name
    os.environ["VECTOR_DB_KEY"] = "self-test-only-key-not-for-production"

    from core.memory.db_utils import configured_db_path
    assert str(configured_db_path()) == _tmp_db.name, (
        "isolation override did not take effect -- refusing to construct "
        "GoalSystem() against a possibly-real DB path"
    )

    gs = GoalSystem()
    active = gs.get_active_goals()
    actions = gs.generate_immediate_actions()
    gs.update_goal_progress("g_daily_commit", 0.5, "committed today")
    summary = gs.get_goal_summary()
    new_id = gs.add_goal("Learn Bengali by August", "MID", priority=6, tags=["language"])
    ok = (
        len(active) >= 5
        and len(actions) >= 1
        and "VECTOR" in summary
        and new_id.startswith("g_")
    )
    print(
        f"✅ goal_system OK — {len(active)} goals, {len(actions)} actions"
        if ok else "❌ FAILED"
    )