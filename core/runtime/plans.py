"""Multi-step plan system for VECTOR autonomous loop.

Extends the MissionRunner pattern with DAG dependencies (borrowed from
WorkflowRunner's _toposort), per-step expected outcomes, verification,
fallbacks, and replanning on failure.

Plans are decomposed from MID/LONG goals, persisted as JSON, and wired into
_think_tick() so plan steps compete as Candidates alongside goal actions.

Design doc: docs/design/multi_step_planning.md
"""
from __future__ import annotations

import asyncio
import datetime
import json
import uuid
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from core.runtime_paths import data_path


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PlanStepFallback:
    """Alternative step to try if the primary step fails."""

    action_type: str
    params: dict[str, Any] = field(default_factory=dict)
    trigger: str = "failure"  # "failure" | "timeout" | "low_confidence"
    # 2026-09-24 (external review, Phase 3 / Stage 4 finding #2): the
    # fallback is usually a DIFFERENT action than the step it replaces, but
    # _try_fallback_step() used to copy the failed step's verification onto
    # it unconditionally -- so an unsatisfiable or action-specific check
    # (e.g. a confidence_threshold the original could never meet) cascaded
    # identically onto the fallback, forcing a second replan even though
    # the fallback itself worked. A fallback may now declare its own
    # acceptance criteria; None keeps the old behavior (inherit).
    verification: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlanStepFallback:
        return cls(
            action_type=str(d.get("action_type") or "respond"),
            params=d.get("params") if isinstance(d.get("params"), dict) else {},
            trigger=str(d.get("trigger") or "failure"),
            verification=d.get("verification") if isinstance(d.get("verification"), dict) else None,
        )


@dataclass
class PlanStep:
    """One step in a multi-step plan.

    Supports DAG dependencies (depends_on), expected outcome verification,
    fallback alternatives, and confidence tracking.
    """

    id: str
    action_type: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    # R19: explicit, declared references to a real prior step's real output
    # field -- {target_param_key: "<dep_step_id>.<output_field>"}. Resolved
    # at dispatch time in PlanRunner.execute_step() (only once every id in
    # depends_on is guaranteed "completed" -- see next_ready_steps()'s own
    # gating), never stored back into `params`, never read from any global/
    # implicit state. This is real data handoff (structured field lookup on
    # the dependency's actual_outcome["result"] dict), not string-scraping.
    param_bindings: dict[str, str] = field(default_factory=dict)
    expected_outcome: str = ""
    verification: dict[str, Any] = field(default_factory=lambda: {"type": "status_check"})
    status: str = "planned"  # planned|ready|running|completed|failed|skipped|blocked
    priority: int = 1
    estimated_time_sec: float = 60.0
    estimated_cost_inr: float = 0.0
    confidence: float = 0.5
    fallback: Optional[PlanStepFallback] = None
    actual_outcome: Optional[dict[str, Any]] = None
    retry_info: Optional[dict[str, Any]] = None
    completed_at: Optional[str] = None
    report: Optional[dict[str, Any]] = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # asdict handles nested dataclasses; fallback is already a dataclass
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlanStep:
        fb = d.get("fallback")
        fallback = PlanStepFallback.from_dict(fb) if isinstance(fb, dict) else None
        return cls(
            id=str(d.get("id") or f"step-{uuid.uuid4().hex[:6]}"),
            action_type=str(d.get("action_type") or "respond"),
            params=d.get("params") if isinstance(d.get("params"), dict) else {},
            depends_on=list(d.get("depends_on") or []),
            param_bindings=d.get("param_bindings") if isinstance(d.get("param_bindings"), dict) else {},
            expected_outcome=str(d.get("expected_outcome") or ""),
            verification=d.get("verification") if isinstance(d.get("verification"), dict) else {"type": "status_check"},
            status=str(d.get("status") or "planned"),
            priority=int(d.get("priority", 1) or 1),
            estimated_time_sec=float(d.get("estimated_time_sec", 60.0) or 60.0),
            estimated_cost_inr=float(d.get("estimated_cost_inr", 0.0) or 0.0),
            confidence=float(d.get("confidence", 0.5) or 0.0),
            fallback=fallback,
            actual_outcome=d.get("actual_outcome") if isinstance(d.get("actual_outcome"), dict) else None,
            retry_info=d.get("retry_info") if isinstance(d.get("retry_info"), dict) else None,
            completed_at=d.get("completed_at") if isinstance(d.get("completed_at"), str) else None,
            report=d.get("report") if isinstance(d.get("report"), dict) else None,
            reason=str(d.get("reason") or ""),
        )


@dataclass
class PlanEvent:
    """Timestamped audit event for a plan."""

    id: str
    type: str  # step_started|step_completed|step_failed|replan|completed|abandoned|outcome_mismatch
    timestamp: str
    message: str
    step_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlanEvent:
        return cls(
            id=str(d.get("id") or uuid.uuid4().hex[:10]),
            type=str(d.get("type") or "event"),
            timestamp=str(d.get("timestamp") or _now()),
            message=str(d.get("message") or ""),
            step_id=str(d.get("step_id") or ""),
            data=d.get("data") if isinstance(d.get("data"), dict) else {},
        )


@dataclass
class Plan:
    """A persistent, DAG-ordered multi-step plan linked to a goal.

    Steps execute in dependency order. Steps with all dependencies completed
    become 'ready' and generate Candidates in the autonomous loop's _think_tick.
    """

    id: str
    goal_id: str
    objective: str
    status: str  # planned|active|paused|completed|failed|abandoned
    steps: list[PlanStep]
    created_at: str
    updated_at: str
    proposed_by: str = "goal_system"
    progress: float = 0.0
    confidence: float = 0.5
    replan_count: int = 0
    events: list[PlanEvent] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    review_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "objective": self.objective,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "proposed_by": self.proposed_by,
            "progress": self.progress,
            "confidence": self.confidence,
            "replan_count": self.replan_count,
            "events": [e.to_dict() for e in self.events],
            "artifacts": self.artifacts,
            "review_required": self.review_required,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Plan:
        steps_data = d.get("steps") if isinstance(d.get("steps"), list) else []
        steps = [PlanStep.from_dict(s) for s in steps_data if isinstance(s, dict)]
        if not steps:
            steps = [PlanStep(id="step-1", action_type="respond")]
        events_data = d.get("events") if isinstance(d.get("events"), list) else []
        events = [PlanEvent.from_dict(e) for e in events_data if isinstance(e, dict)]
        return cls(
            id=str(d.get("id") or f"plan-{uuid.uuid4().hex[:10]}"),
            goal_id=str(d.get("goal_id") or ""),
            objective=str(d.get("objective") or ""),
            status=str(d.get("status") or "planned"),
            steps=steps,
            created_at=str(d.get("created_at") or _now()),
            updated_at=str(d.get("updated_at") or _now()),
            proposed_by=str(d.get("proposed_by") or "goal_system"),
            progress=float(d.get("progress", 0.0) or 0.0),
            confidence=float(d.get("confidence", 0.5) or 0.0),
            replan_count=int(d.get("replan_count", 0) or 0),
            events=events,
            artifacts=list(d.get("artifacts") or []),
            review_required=bool(d.get("review_required", False)),
        )

    # -- DAG resolution -------------------------------------------------------

    def next_ready_steps(self, limit: int = 3) -> list[PlanStep]:
        """Return steps whose dependencies are all completed and status is 'planned'.

        Respects DAG: a step is ready only when every step in depends_on has
        status == 'completed'. Returns up to `limit` steps sorted by priority.
        """
        completed_ids = {s.id for s in self.steps if s.status == "completed"}
        ready = []
        for step in self.steps:
            if step.status != "planned":
                continue
            if all(dep_id in completed_ids for dep_id in step.depends_on):
                ready.append(step)
        ready.sort(key=lambda s: s.priority)
        return ready[:limit]

    def has_circular_deps(self) -> bool:
        """Detect circular dependencies using Kahn's algorithm (topological sort)."""
        step_ids = {s.id for s in self.steps}
        in_deg = {s.id: 0 for s in self.steps}
        out_edges: dict[str, list[str]] = defaultdict(list)
        for s in self.steps:
            for dep in s.depends_on:
                if dep not in step_ids:
                    continue
                in_deg[s.id] += 1
                out_edges[dep].append(s.id)
        queue = deque([sid for sid, d in in_deg.items() if d == 0])
        seen = 0
        while queue:
            sid = queue.popleft()
            seen += 1
            for child in out_edges[sid]:
                in_deg[child] -= 1
                if in_deg[child] == 0:
                    queue.append(child)
        return seen != len(self.steps)

    # -- Progress / events ----------------------------------------------------

    def update_progress(self) -> None:
        """Recalculate progress and confidence from step statuses."""
        total = max(1, len(self.steps))
        completed = sum(1 for s in self.steps if s.status in ("completed", "skipped"))
        self.progress = round(completed / total, 3)
        confidences = [s.confidence for s in self.steps if s.confidence > 0]
        self.confidence = round(sum(confidences) / max(1, len(confidences)), 3) if confidences else 0.5

    def record_event(
        self,
        event_type: str,
        message: str,
        step_id: str = "",
        data: dict[str, Any] | None = None,
    ) -> PlanEvent:
        event = PlanEvent(
            id=uuid.uuid4().hex[:10],
            type=event_type,
            timestamp=_now(),
            message=message,
            step_id=step_id,
            data=data or {},
        )
        self.events.append(event)
        self.updated_at = _now()
        return event

    def is_complete(self) -> bool:
        return all(s.status in ("completed", "skipped") for s in self.steps)

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _is_safe_to_auto_resume(action_type: str) -> bool:
    """True only for action types the existing permission-gateway tier
    classifies GREEN (read-only / idempotent-by-nature — search, status
    checks, respond, etc.). Reuses the SAME classification VECTOR already
    applies before ANY action executes (core/loop/permission_gateway.py) —
    no new safety taxonomy is introduced here. YELLOW/RED/FORBIDDEN/UNKNOWN
    action types (send_email, execute_code, financial_transaction,
    push_github, ...) are never auto-resumed: after a crash we cannot know
    whether the real-world side effect already happened, so silently
    re-running them risks a duplicate send/write/spend. See
    _recover_stale_running_steps() for what happens to those instead."""
    try:
        from core.loop.permission_gateway import GREEN
        return action_type in GREEN
    except Exception:
        # Import failure — the gate module is somehow unavailable. Fail
        # closed: treat as unsafe to auto-resume rather than guessing.
        return False


def _recover_stale_running_steps(plan: "Plan") -> bool:
    """Crash/restart recovery for plan steps stuck at status='running'.

    Called exactly once per plan, the first time it is loaded into a fresh
    PlanStore (see PlanStore._ensure_loaded()). Any step still 'running' at
    that moment was persisted by execute_step() (plans.py) immediately
    before calling the executor, in a PREVIOUS process that never reached
    the terminal status write a few lines later — i.e. the process crashed,
    was killed, or the host restarted mid-step. Within a single process,
    execute_step() always resolves a step to a terminal status
    (completed/failed/blocked) before the next tick can start a different
    step, so this situation cannot arise from anything still legitimately
    in flight in the CURRENT process.

    Recovery decision (deterministic, per action_type's existing
    GREEN/YELLOW/RED/FORBIDDEN classification — see
    _is_safe_to_auto_resume()):
      - GREEN (read-only/idempotent): reset status -> "planned" so the
        step is naturally re-offered by next_ready_steps() and re-executed
        via the normal decision cycle, which itself re-applies the
        permission gate — recovery does not bypass anything the step would
        have gone through on its first attempt.
      - YELLOW/RED/FORBIDDEN/UNKNOWN: NEVER auto-resumed. Marked "failed"
        with an explicit reason, then given the SAME chance a normal
        failure gets to route around itself via the step's declared
        fallback (_try_fallback_step() — the exact synchronous logic
        replan_plan()'s own Strategy 1 uses; no LLM call, so it's safe to
        run here in a sync context). If there's no fallback,
        plan.review_required is set True so the interruption is visible
        plan-wide, not just in one step's event log. The LLM-restructure
        strategy (replan_plan()'s Strategy 2) is deliberately NOT attempted
        during recovery — it requires an async LLM call this sync
        load-time hook cannot safely make; a plan that needs that level of
        replanning surfaces via review_required instead of being silently
        force-async'd out of this hook.

    Every recovered step's retry_info records what happened (interrupted,
    when, what decision was made) for audit — retry_info is a pre-existing
    PlanStep field that was declared but never written to before this
    change (see PlanStep dataclass), so no new persisted field is added.

    Returns True if any step in this plan was touched (caller uses this to
    decide whether the plan store needs re-saving).
    """
    touched = False
    for step in plan.steps:
        if step.status != "running":
            continue
        touched = True
        interrupted_at = _now()
        if _is_safe_to_auto_resume(step.action_type):
            step.status = "planned"
            step.retry_info = {
                "recovered_at": interrupted_at,
                "recovery_decision": "reset_to_planned",
                "reason": (
                    f"Process restart found step '{step.id}' (action_type="
                    f"'{step.action_type}', GREEN-tier) stuck at status="
                    "'running' — safe to re-execute from scratch, reset to "
                    "'planned'."
                ),
            }
            plan.record_event(
                "step_recovered",
                f"Step {step.id} ({step.action_type}) recovered after crash — "
                "GREEN-tier, reset to 'planned' for re-execution",
                step_id=step.id,
            )
            logger.warning(
                "[VECTOR][plans] recovered crashed step {} in plan {} "
                "(action_type={}, GREEN-tier — reset to planned)",
                step.id, plan.id, step.action_type,
            )
        else:
            interrupted_reason = (
                f"Interrupted by process restart while status='running' "
                f"(action_type='{step.action_type}' is not GREEN-tier — "
                "not safe to auto-resume; a real-world side effect may "
                "already have occurred)."
            )
            step.status = "failed"
            step.reason = interrupted_reason
            step.completed_at = interrupted_at
            step.actual_outcome = {
                "status": "interrupted",
                "summary": interrupted_reason,
                "verification_passed": False,
            }
            step.retry_info = {
                "recovered_at": interrupted_at,
                "recovery_decision": "marked_failed_not_auto_resumed",
                "reason": interrupted_reason,
            }
            plan.record_event(
                "step_recovered",
                f"Step {step.id} ({step.action_type}) found interrupted after "
                "crash — NOT GREEN-tier, not auto-resumed",
                step_id=step.id,
            )
            logger.warning(
                "[VECTOR][plans] step {} in plan {} was interrupted by a "
                "crash while action_type={!r} was running — NOT auto-resumed "
                "(not GREEN-tier)",
                step.id, plan.id, step.action_type,
            )
            # Give the plan the same chance to route around this that a
            # normal (non-crash) failure gets: try the step's declared
            # fallback (same synchronous logic replan_plan() uses for its
            # own Strategy 1 — see _try_fallback_step()). Only a step with
            # NO fallback and NOT GREEN-tier ends up requiring owner review;
            # dependent steps stay blocked either way until this resolves,
            # exactly like any other real failure (this is the plan
            # system's existing, unchanged behavior for a failed step with
            # no fallback — not a new stall introduced by recovery).
            if not _try_fallback_step(plan, step):
                plan.review_required = True
    if touched:
        plan.update_progress()
        plan.updated_at = _now()
    return touched


# ---------------------------------------------------------------------------
# PlanStore — JSON-file persistence (mirrors MissionStore pattern)
# ---------------------------------------------------------------------------


class PlanStore:
    """Restart-safe plan registry backed by a JSON file.

    Pattern identical to MissionStore: atomic write with .tmp + rename,
    Windows PermissionError retry.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._plans: dict[str, Plan] = {}
        self._path = path
        self._loaded = False

    @property
    def path(self) -> Path:
        return self._path or data_path("plans", "plans.json")

    def add(self, plan: Plan) -> Plan:
        self._ensure_loaded()
        self._plans[plan.id] = plan
        self.save()
        return plan

    def get(self, plan_id: str) -> Plan | None:
        self._ensure_loaded()
        return self._plans.get(plan_id)

    def active_plans(self) -> list[Plan]:
        """Return plans with status 'active' or 'planned'."""
        self._ensure_loaded()
        return [p for p in self._plans.values() if p.status in ("active", "planned")]

    def plans_for_goal(self, goal_id: str) -> list[Plan]:
        self._ensure_loaded()
        return [p for p in self._plans.values() if p.goal_id == goal_id]

    def list(self, limit: int = 20) -> list[Plan]:
        self._ensure_loaded()
        plans = sorted(self._plans.values(), key=lambda p: p.updated_at, reverse=True)
        return plans[: max(1, min(limit, 100))]

    def clear(self, persist: bool = False) -> None:
        self._plans.clear()
        self._loaded = True
        if persist:
            self.save()

    def save(self) -> None:
        payload = {
            "version": 1,
            "plans": [plan.to_dict() for plan in self._plans.values()],
        }
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        # Windows PermissionError retry (same pattern as MissionStore)
        import time as _time
        for _attempt in range(5):
            try:
                tmp_path.replace(path)
                return
            except PermissionError:
                if _attempt == 4:
                    raise
                _time.sleep(0.05)

    def reload(self) -> None:
        self._plans.clear()
        self._loaded = False
        self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = self.path
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw.get("plans", []) if isinstance(raw, dict) else []
            if not isinstance(items, list):
                return
            recovered_any = False
            for item in items:
                if not isinstance(item, dict):
                    continue
                plan = Plan.from_dict(item)
                self._plans[plan.id] = plan
                # Crash/restart recovery — a step is "running" here only because
                # it was persisted mid-execution by a PROCESS THAT NO LONGER
                # EXISTS: this is the very first load of this plan into this
                # process's memory (this whole branch only runs once, guarded by
                # self._loaded above), and execute_step() is the only writer of
                # status="running" (plans.py:689) — always followed, in the same
                # process, by a terminal status write a few lines later
                # (plans.py:722-734) before the next tick can start a different
                # step. So a "running" step surviving to the next _ensure_loaded()
                # call is unconditionally orphaned, not a live in-flight step.
                if _recover_stale_running_steps(plan):
                    recovered_any = True
            if recovered_any:
                self.save()
        except Exception:
            logger.warning("[VECTOR][plans] PlanStore load failed — starting empty", exc_info=True)
            self._plans.clear()


# Module-level singleton (lazy — first access loads from disk)
_PLAN_STORE: PlanStore | None = None


def get_plan_store() -> PlanStore:
    global _PLAN_STORE
    if _PLAN_STORE is None:
        _PLAN_STORE = PlanStore()
    return _PLAN_STORE


# ---------------------------------------------------------------------------
# R19: step-to-step real data handoff
# ---------------------------------------------------------------------------


def _resolve_step_params(plan: "Plan", step: PlanStep) -> dict[str, Any]:
    """Build the real params dict to dispatch `step` with, resolving any
    declared `param_bindings` against its real, already-completed
    dependencies' real stored output.

    Called only from execute_step(), i.e. only once next_ready_steps()'s
    own DAG gating has already guaranteed every id in step.depends_on has
    status == "completed" -- so every binding's dependency step is real and
    resolvable here, not merely hoped to be.

    Returns a NEW dict (step.params is never mutated) -- `params` stays the
    plan's own static, persisted, human-auditable declaration; the resolved
    values are transient, computed fresh at dispatch time from the
    dependency's real actual_outcome["result"] dict (see execute_step()'s
    own comment on why that field now exists). An unresolvable binding
    (missing dependency, missing field, or the dependency's own result not
    a dict) is silently skipped -- the step then dispatches with whatever
    static params.get(key) already provided (or none), rather than crashing
    the whole step on a malformed/stale binding; a step whose GENUINELY
    required field failed to resolve will simply fail its own real
    downstream handler validation / verify_step_outcome() check, which is
    the same honest failure mode any other bad real input already gets.
    """
    resolved = dict(step.params)
    for target_key, source_ref in (step.param_bindings or {}).items():
        if not isinstance(source_ref, str) or "." not in source_ref:
            continue
        dep_id, _, field_name = source_ref.partition(".")
        dep_step = plan.get_step(dep_id)
        if dep_step is None or dep_step.status != "completed" or not dep_step.actual_outcome:
            continue
        dep_result = dep_step.actual_outcome.get("result")
        found, value = _lookup_path(dep_result, field_name)
        if found:
            resolved[target_key] = value
    return resolved



def _lookup_path(data: Any, path: str) -> tuple[bool, Any]:
    """Look `path` up in `data`: a literal top-level key first (the original binding form), otherwise a dotted walk
    through nested dicts and list indexes ("fields.detail_url", "links.0.href"). Returns (found, value)."""
    if not isinstance(data, dict) or not path:
        return False, None
    if path in data:
        return True, data[path]
    cur: Any = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.lstrip("-").isdigit() and -len(cur) <= int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return False, None
    return True, cur


# ---------------------------------------------------------------------------
# Outcome verification
# ---------------------------------------------------------------------------


def verify_step_outcome(step: PlanStep, report_status: str, report_result: Any = None) -> bool:
    """Check if actual outcome matches expected.

    Verification types:
    - status_check: report.status == "executed" (default)
    - file_exists: check if a file path exists
    - confidence_threshold: epistemic confidence >= threshold
    - always: always passes (for steps where execution = success)
    """
    vtype = step.verification.get("type", "status_check")

    if vtype == "always":
        return True

    if vtype == "status_check":
        return report_status == "executed"

    # Content verification (shared outcome assessment, 2026-09-26): the step's own REAL result payload is checked against
    # criteria the plan declared up front, independent of whatever the handler claimed about itself. A step can only pass
    # if it was executed AND the evidence is there.
    if vtype == "all_of":
        checks = step.verification.get("criteria", {}).get("checks", [])
        if not isinstance(checks, list) or not checks:
            return False  # an empty conjunction must not silently pass
        return all(
            verify_step_outcome(
                PlanStep(id=step.id, action_type=step.action_type, verification=c if isinstance(c, dict) else {}),
                report_status, report_result,
            )
            for c in checks
        )

    if vtype == "result_field":
        if report_status != "executed":
            return False
        return _result_field_matches(step.verification.get("criteria", {}), report_result)

    if vtype == "file_exists":
        fpath = step.verification.get("criteria", {}).get("path", "")
        if not fpath:
            return report_status == "executed"
        return Path(fpath).exists()

    if vtype == "confidence_threshold":
        min_conf = step.verification.get("criteria", {}).get("min_confidence", 0.5)
        try:
            from core.brain.epistemic_tracker import EpistemicTracker
            tracker = EpistemicTracker()
            # R9: was tracker.get_confidence(step.action_type) -- a bare
            # action_type ("check_attendance") never matches any real claim
            # id, since every actual epistemic writer/reader in this codebase
            # (core/loop/decision_engine.py's _epistemic_penalty() /
            # record_epistemic_belief()) keys claims as
            # "action_domain:<action_type.split('_')[0]>". A bare-action_type
            # lookup always returned 0.0 (unknown claim), so this branch
            # could never pass for any positive min_confidence -- a dead
            # reader/writer identity mismatch, not a design choice. Reuses
            # the exact same domain-derivation convention decision_engine.py
            # already uses, rather than inventing a second one.
            domain = step.action_type.split("_")[0]
            current_conf = tracker.get_confidence(f"action_domain:{domain}")
            tracker.close()
            return current_conf >= min_conf
        except Exception:
            return report_status == "executed"

    # Unknown verification type — fall back to status check
    return report_status == "executed"


def _result_field_matches(criteria: dict[str, Any], payload: Any) -> bool:
    """criteria: {"field": "fields.title", plus exactly the tests wanted:
        "equals": v | "contains": s | "regex": p | "non_empty": true | "min_items": n | "in": [..]}.
    All given tests must hold. A missing field, a missing payload, or a criteria dict with no test at all fails."""
    import re as _re

    found, value = _lookup_path(payload, str(criteria.get("field", "")))
    if not found:
        return False
    tested = False
    if "equals" in criteria:
        tested = True
        if value != criteria["equals"]:
            return False
    if "contains" in criteria:
        tested = True
        if str(criteria["contains"]) not in (value if isinstance(value, str) else str(value)):
            return False
    if "regex" in criteria:
        tested = True
        try:
            if _re.search(str(criteria["regex"]), value if isinstance(value, str) else str(value)) is None:
                return False
        except _re.error:
            return False
    if "in" in criteria:
        tested = True
        if not isinstance(criteria["in"], list) or value not in criteria["in"]:
            return False
    if criteria.get("non_empty"):
        tested = True
        if value is None or (hasattr(value, "__len__") and len(value) == 0) or (isinstance(value, str) and not value.strip()):
            return False
    if "min_items" in criteria:
        tested = True
        if not isinstance(value, (list, tuple, dict)) or len(value) < int(criteria["min_items"]):
            return False
    return tested


# ---------------------------------------------------------------------------
# Plan decomposition
# ---------------------------------------------------------------------------


async def decompose_goal_to_plan(
    goal_id: str,
    objective: str,
    proposed_by: str = "goal_system",
) -> Plan | None:
    """Decompose a goal into a multi-step Plan.

    Strategy:
    1. Try LLM-based decomposition via MissionPlanAdvisor
    2. Fall back to rule-based ObjectiveDecomposer
    3. If both fail, return None (goal stays as single-action)

    Each step gets: expected_outcome, verification, fallback, confidence.
    """
    steps: list[PlanStep] = []

    # Try LLM decomposition first
    try:
        from core.runtime.missions import MissionPlanAdvisor
        advisor = MissionPlanAdvisor()
        # advise() is sync — wrap in to_thread so we don't block the loop
        llm_result = await asyncio.to_thread(advisor.advise, objective)
        if llm_result and isinstance(llm_result, dict):
            # advise() returns {"steps": [...], ...} or a dict with step data
            raw_steps = llm_result.get("steps", llm_result if isinstance(llm_result, list) else [])
            if isinstance(raw_steps, list):
                for i, step_data in enumerate(raw_steps):
                    if isinstance(step_data, dict):
                        steps.append(PlanStep(
                            id=f"step-{i + 1}",
                            action_type=str(step_data.get("action_type", step_data.get("action", "respond"))),
                            params=step_data.get("params", {}),
                            depends_on=step_data.get("depends_on", []),
                            expected_outcome=step_data.get("expected_outcome", ""),
                            confidence=_get_epistemic_confidence(
                                step_data.get("action_type", step_data.get("action", "respond"))
                            ),
                        ))
            if steps:
                logger.info(f"[VECTOR][plans] LLM decomposed '{objective}' into {len(steps)} steps")
    except Exception as e:
        logger.debug(f"[VECTOR][plans] LLM decomposition failed: {e}")

    # Fall back to rule-based decomposition
    if not steps:
        try:
            from core.runtime.missions import ObjectiveDecomposer
            decomposer = ObjectiveDecomposer()
            result = decomposer.decompose(objective)
            raw_steps = result.get("steps", []) if isinstance(result, dict) else []
            for i, ms in enumerate(raw_steps):
                if isinstance(ms, dict):
                    steps.append(PlanStep(
                        id=f"step-{i + 1}",
                        action_type=ms.get("action_type", "respond"),
                        params=ms.get("params", {}),
                        depends_on=[f"step-{i}"] if i > 0 else [],  # sequential fallback
                        expected_outcome=f"Step {i + 1} completes: {ms.get('action_type', 'respond')}",
                        confidence=float(ms.get("confidence", 0.5)),
                    ))
            if steps:
                logger.info(f"[VECTOR][plans] Rule-based decomposed '{objective}' into {len(steps)} steps")
        except Exception as e:
            logger.debug(f"[VECTOR][plans] Rule-based decomposition failed: {e}")

    if not steps:
        logger.debug(f"[VECTOR][plans] Could not decompose '{objective}' — no plan created")
        return None

    # Enhance steps with defaults
    for i, step in enumerate(steps):
        if not step.verification or step.verification == {"type": "status_check"}:
            step.verification = {"type": "status_check"}
        if not step.fallback and i < len(steps) - 1:
            # Add a lightweight fallback for non-terminal steps
            step.fallback = PlanStepFallback(
                action_type="respond",
                params={"message": f"Fallback for {step.action_type}"},
                trigger="failure",
            )

    plan = Plan(
        id=f"plan-{uuid.uuid4().hex[:10]}",
        goal_id=goal_id,
        objective=objective,
        status="planned",
        steps=steps,
        created_at=_now(),
        updated_at=_now(),
        proposed_by=proposed_by,
    )

    # Check for circular deps — if found, flatten to sequential
    if plan.has_circular_deps():
        logger.warning(f"[VECTOR][plans] Circular deps detected in plan {plan.id} — flattening to sequential")
        for i, step in enumerate(plan.steps):
            step.depends_on = [f"step-{i}"] if i > 0 else []
        plan.record_event("circular_deps_flattened", "Circular dependencies detected and flattened to sequential")

    plan.record_event("created", f"Plan created with {len(steps)} steps for goal {goal_id}")
    return plan


def build_wedge_content_plan(
    goal_id: str,
    topic: str,
    platforms: list[str] | None = None,
    duration_min: float = 5.0,
) -> Plan:
    """R19: deterministic (NO LLM call) 2-step real composition --
    `script` (real ScriptGenerator LLM call, produces a real "content"
    field) -> `schedule_post` (real ContentScheduler local job creation,
    consumes that real "content" field as its actual payload via
    PlanStep.param_bindings).

    Deliberately NOT built through decompose_goal_to_plan()'s LLM path
    (MissionPlanAdvisor): that path can invent a non-existent action_type
    (a real, observed risk in this codebase, per this function's sibling
    `_get_epistemic_confidence`'s own callers) -- both action_types here are
    already real, already-permission-classified, already-Governor-routed
    (see core/config.py and core/city/governor.py's DISTRICT_TASK_MAP), so
    a hand-declared, deterministic step list is the honest, non-fabricated
    choice, not a shortcut around real decomposition.

    Only "script"'s params are static (topic/duration_min come from the
    caller, not invented); "schedule_post"'s "content" is deliberately
    ABSENT from its static params -- it is resolved at dispatch time,
    real-to-real, via param_bindings (see _resolve_step_params()), never a
    hard-coded test value."""
    step1 = PlanStep(
        id="step-1",
        action_type="script",
        params={"topic": topic, "duration_min": duration_min},
        depends_on=[],
        expected_outcome="A real video script is generated for the topic",
        verification={"type": "status_check"},
    )
    step2 = PlanStep(
        id="step-2",
        action_type="schedule_post",
        params={"title": topic, "platforms": platforms or ["devto"]},
        depends_on=["step-1"],
        param_bindings={"content": "step-1.content"},
        expected_outcome="The real script generated in step-1 is scheduled as a local post job",
        verification={"type": "status_check"},
    )
    plan = Plan(
        id=f"plan-{uuid.uuid4().hex[:10]}",
        goal_id=goal_id,
        objective=f"Wedge content pipeline: script -> schedule_post for '{topic}'",
        status="planned",
        steps=[step1, step2],
        created_at=_now(),
        updated_at=_now(),
        proposed_by="r19_wedge_content_composition",
    )
    plan.record_event("created", f"Deterministic wedge-content plan created (2 steps) for goal {goal_id}")
    return plan


def _get_epistemic_confidence(action_type: str) -> float:
    """Get epistemic confidence for an action type. Returns 0.5 (neutral) on failure."""
    try:
        from core.brain.epistemic_tracker import EpistemicTracker
        tracker = EpistemicTracker()
        conf = tracker.get_confidence(action_type)
        tracker.close()
        return conf
    except Exception:
        return 0.5


# ---------------------------------------------------------------------------
# Replanning
# ---------------------------------------------------------------------------

MAX_REPLANS = 2


def _try_fallback_step(plan: Plan, failed_step: PlanStep) -> bool:
    """Strategy 1 of replanning: swap the failed step for its declared
    fallback, in place, preserving its id (so downstream depends_on links
    stay valid). Fully synchronous — no LLM call, no I/O beyond the
    epistemic-confidence lookup already used elsewhere in this module.

    Extracted from replan_plan() so BOTH the normal execute_step() failure
    path (via replan_plan(), async) and PlanStore's synchronous crash-
    recovery path (_recover_stale_running_steps(), which cannot safely call
    the async replan_plan() from inside a sync _ensure_loaded()) share the
    exact same fallback logic rather than duplicating it.

    Returns True if a fallback was applied, False if the step had none.
    """
    if not failed_step.fallback:
        return False
    replacement = PlanStep(
        id=failed_step.id,  # keep same ID to preserve downstream deps
        action_type=failed_step.fallback.action_type,
        params=failed_step.fallback.params,
        depends_on=failed_step.depends_on,
        expected_outcome=failed_step.expected_outcome,
        verification=(failed_step.fallback.verification
                      if failed_step.fallback.verification is not None
                      else failed_step.verification),
        status="planned",
        priority=failed_step.priority,
        confidence=_get_epistemic_confidence(failed_step.fallback.action_type),
    )
    for i, s in enumerate(plan.steps):
        if s.id == failed_step.id:
            plan.steps[i] = replacement
            break
    plan.record_event(
        "fallback_activated",
        f"Step {failed_step.id} failed — fallback to {replacement.action_type}",
        step_id=failed_step.id,
    )
    plan.updated_at = _now()
    return True


async def replan_plan(plan: Plan, failed_step: PlanStep) -> Plan:
    """Restructure remaining steps after a failure.

    Strategy order:
    1. Try fallback if available
    2. Ask LLM to restructure (up to MAX_REPLANS times)
    3. Abandon plan if replan budget exhausted
    """
    plan.replan_count += 1

    # Strategy 1: Try fallback
    if _try_fallback_step(plan, failed_step):
        return plan

    # A step verified against objective evidence (result_field / all_of) carries the plan's contract for what "done" means.
    # The LLM restructure below rebuilds steps WITHOUT their verification (they default to status_check) and without
    # param_bindings, so letting it replace such a step would let the plan finish "verified" by a weaker check than the
    # one it failed. Fallbacks the plan declared up front (Strategy 1, above) are fine; an invented replacement is not:
    # the plan is abandoned and the failure stays visible instead.
    content_verified = failed_step.verification.get("type") in ("result_field", "all_of")

    # Strategy 2: LLM restructure (if budget allows)
    if plan.replan_count <= MAX_REPLANS and not content_verified:
        try:
            from core.runtime.missions import MissionPlanAdvisor
            advisor = MissionPlanAdvisor()
            completed = [s for s in plan.steps if s.status == "completed"]
            remaining = [s for s in plan.steps if s.status == "planned"]
            context = (
                f"Objective: {plan.objective}\n"
                f"Completed steps: {', '.join(s.action_type for s in completed) or 'none'}\n"
                f"Failed step: {failed_step.action_type} — {failed_step.reason}\n"
                f"Remaining steps: {', '.join(s.action_type for s in remaining) or 'none'}\n"
                f"Please suggest replacement steps as JSON array."
            )
            # advise() is sync — wrap in to_thread
            raw_result = await asyncio.to_thread(advisor.advise, context)
            raw_steps = raw_result.get("steps", []) if isinstance(raw_result, dict) else []
            if raw_steps and isinstance(raw_steps, list):
                new_steps = []
                base_idx = len(completed) + 1
                for j, sd in enumerate(raw_steps):
                    if isinstance(sd, dict):
                        new_steps.append(PlanStep(
                            id=f"step-{base_idx + j}",
                            action_type=str(sd.get("action_type", sd.get("action", "respond"))),
                            params=sd.get("params", {}),
                            depends_on=sd.get("depends_on", []),
                            expected_outcome=sd.get("expected_outcome", ""),
                            confidence=_get_epistemic_confidence(
                                sd.get("action_type", sd.get("action", "respond"))
                            ),
                        ))
                if new_steps:
                    # Replace remaining planned steps with new ones
                    plan.steps = completed + new_steps
                    plan.record_event(
                        "replan",
                        f"Replan {plan.replan_count}: replaced {len(remaining)} steps with {len(new_steps)} new steps",
                        step_id=failed_step.id,
                    )
                    plan.updated_at = _now()
                    return plan
        except Exception as e:
            logger.warning(f"[VECTOR][plans] LLM replan failed: {e}")

    # Strategy 3: Abandon
    plan.status = "failed"
    plan.record_event(
        "abandoned",
        (f"Step {failed_step.id} failed its objective verification and has no declared fallback; not restructured "
         f"(replan_count={plan.replan_count})") if content_verified
        else f"Replan budget exhausted (replan_count={plan.replan_count})",
        step_id=failed_step.id,
    )
    plan.updated_at = _now()
    return plan


# ---------------------------------------------------------------------------
# PlanRunner — execution orchestrator (used by autonomous loop)
# ---------------------------------------------------------------------------


class PlanRunner:
    """Executes plan steps through the permission gateway.

    Unlike MissionRunner (which runs all steps in one shot), PlanRunner
    executes ONE step at a time — the autonomous loop calls it per tick
    when a plan step wins the decision.
    """

    def __init__(self, store: PlanStore | None = None) -> None:
        self.store = store or get_plan_store()
        self._executor = None
        logger.info("[VECTOR][plans] PlanRunner initialized")

    def _get_executor(self):
        if self._executor is None:
            from core.runtime.executor import AutonomousExecutor
            self._executor = AutonomousExecutor()
        return self._executor

    async def execute_step(self, plan: Plan, step: PlanStep) -> dict[str, Any]:
        """Execute a single plan step through the permission gateway.

        Returns a report dict with status, outcome, verification result.
        """
        step.status = "running"
        plan.record_event("step_started", f"Step {step.id} started: {step.action_type}", step_id=step.id)
        self.store.save()

        executor = self._get_executor()
        exec_error = None
        try:
            report = await executor.execute(
                action_type=step.action_type,
                params=_resolve_step_params(plan, step),
                proposed_by=f"plan:{plan.id}",
            )
        except Exception as e:
            logger.error(f"[VECTOR][plans] Step {step.id} execution error: {e}")
            exec_error = e
            report = None

        report_status = report.status if report else "failed"
        report_reason = report.reason if report else (str(exec_error) if exec_error else "unknown error")
        report_result = report.result if report else None

        # Verify outcome
        passed = verify_step_outcome(step, report_status, report_result)

        step.report = {"status": report_status, "reason": report_reason} if report else {"status": "failed", "reason": report_reason}
        step.reason = report_reason
        step.actual_outcome = {
            "status": report_status,
            "summary": report_reason,
            "verification_passed": passed,
            # R19: the real handler's real structured result (e.g.
            # ScriptGenerator's {"content":..., "topic":..., ...}) used to
            # be discarded here -- only status/summary/verification_passed
            # were kept, leaving no real way for a dependent step to
            # consume this step's real output. Preserved (additively, no
            # existing key removed) so param_bindings resolution
            # (_resolve_step_params()) has a real, structured value to read.
            "result": report_result if isinstance(report_result, dict) else {},
        }
        step.completed_at = _now()

        if report_status == "executed" and passed:
            step.status = "completed"
            plan.record_event("step_completed", f"Step {step.id} verified", step_id=step.id)
        elif report_status == "executed" and not passed:
            step.status = "failed"
            step.reason = "Outcome verification failed"
            plan.record_event("outcome_mismatch", f"Step {step.id} outcome didn't match expected", step_id=step.id)
        elif report_status == "blocked":
            step.status = "blocked"
            plan.record_event("step_blocked", f"Step {step.id} blocked by gateway", step_id=step.id)
        else:
            step.status = "failed"
            plan.record_event("step_failed", f"Step {step.id} failed: {report_reason}", step_id=step.id)

        # Handle failure — replan
        if step.status == "failed":
            await replan_plan(plan, step)

        # Update plan state
        plan.update_progress()

        # Check completion
        if plan.status not in ("failed", "abandoned") and plan.is_complete():
            plan.status = "completed"
            plan.record_event("completed", "All steps completed and verified")

        plan.updated_at = _now()
        self.store.save()

        return {
            "step_id": step.id,
            "status": step.status,
            "verification_passed": passed,
            "reason": step.reason,
            "plan_status": plan.status,
            "plan_progress": plan.progress,
        }

    async def create_and_activate_plan(
        self,
        goal_id: str,
        objective: str,
        proposed_by: str = "goal_system",
    ) -> Plan | None:
        """Decompose a goal into a plan and activate it."""
        plan = await decompose_goal_to_plan(goal_id, objective, proposed_by)
        if plan is None:
            return None
        plan.status = "active"
        plan.record_event("activated", f"Plan activated with {len(plan.steps)} steps")
        self.store.add(plan)
        logger.info(f"[VECTOR][plans] Plan {plan.id} active — {len(plan.steps)} steps for goal {goal_id}")
        return plan


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import sys
    import tempfile

    sys.stdout.reconfigure(encoding="utf-8")

    # Test 1: PlanStep serialization
    step = PlanStep(
        id="step-1",
        action_type="search_web",
        params={"query": "test"},
        depends_on=[],
        expected_outcome="Results found",
        confidence=0.7,
    )
    d = step.to_dict()
    step2 = PlanStep.from_dict(d)
    assert step2.id == "step-1"
    assert step2.action_type == "search_web"
    assert step2.confidence == 0.7

    # Test 2: Plan with DAG
    plan = Plan(
        id="plan-test",
        goal_id="g_test",
        objective="Test plan",
        status="active",
        steps=[
            PlanStep(id="step-1", action_type="a"),
            PlanStep(id="step-2", action_type="b", depends_on=["step-1"]),
            PlanStep(id="step-3", action_type="c", depends_on=["step-1"]),
            PlanStep(id="step-4", action_type="d", depends_on=["step-2", "step-3"]),
        ],
        created_at=_now(),
        updated_at=_now(),
    )
    # Initially only step-1 is ready
    ready = plan.next_ready_steps()
    assert len(ready) == 1
    assert ready[0].id == "step-1"

    # After completing step-1, step-2 and step-3 are ready
    plan.steps[0].status = "completed"
    ready = plan.next_ready_steps()
    assert len(ready) == 2
    assert {r.id for r in ready} == {"step-2", "step-3"}

    # Test 3: Circular dependency detection
    circular_plan = Plan(
        id="plan-circular",
        goal_id="g_test",
        objective="Circular",
        status="active",
        steps=[
            PlanStep(id="s1", action_type="a", depends_on=["s2"]),
            PlanStep(id="s2", action_type="b", depends_on=["s1"]),
        ],
        created_at=_now(),
        updated_at=_now(),
    )
    assert circular_plan.has_circular_deps() is True

    # Test 4: PlanStore round-trip
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmppath = Path(f.name)
    try:
        store = PlanStore(path=tmppath)
        store.add(plan)
        store2 = PlanStore(path=tmppath)
        loaded = store2.get("plan-test")
        assert loaded is not None
        assert loaded.objective == "Test plan"
        assert len(loaded.steps) == 4
        assert loaded.steps[1].depends_on == ["step-1"]
    finally:
        tmppath.unlink(missing_ok=True)

    # Test 5: verify_step_outcome
    step_ok = PlanStep(id="s1", action_type="test", verification={"type": "status_check"})
    assert verify_step_outcome(step_ok, "executed") is True
    assert verify_step_outcome(step_ok, "failed") is False

    step_always = PlanStep(id="s2", action_type="test", verification={"type": "always"})
    assert verify_step_outcome(step_always, "failed") is True

    # Test 6: Plan serialization round-trip
    plan_dict = plan.to_dict()
    plan_restored = Plan.from_dict(plan_dict)
    assert plan_restored.id == "plan-test"
    assert len(plan_restored.steps) == 4
    assert plan_restored.steps[3].depends_on == ["step-2", "step-3"]

    print("✅ plans.py OK — all self-tests passed")
