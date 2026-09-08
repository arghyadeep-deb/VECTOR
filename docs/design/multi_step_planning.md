# VECTOR Multi-Step Planning System — Design Document

> Status: DRAFT — awaiting validation before implementation
> Date: 2026-08-13
> Author: Claude Code (design phase)

---

## 1. Current Architecture

VECTOR's planning landscape has **three separate systems** that each solve part of the problem but none are wired together:

### 1.1 Goal System (`core/brain/goal_system.py`, 309 LOC)
- 3-horizon model: LONG (90d), MID (30d), SHORT (7d)
- 7 pre-seeded goals covering all districts
- `generate_immediate_actions()` → returns **flat list of single actions**
- `GOAL_ACTION_MAP`: SHORT→"research_topic", MID/LONG→"analyze_progress"
- Persisted via `episodic_memory.remember("goals_v1", ...)`
- **Limitation**: Goals produce single actions. No ordered sequences. No dependencies.

### 1.2 Planner (`core/loop/planner.py`, 99 LOC)
- Trivial pass-through: `plan()` → `goal_system.generate_immediate_actions(limit=4)`
- `plan_for_energy()` filters by energy level (high/medium/low)
- `get_next_action()` → single highest-priority action
- **Limitation**: No plan state. No step ordering. No verification. No memory of past plans.

### 1.3 WorkflowRunner (`core/loop/workflow_runner.py`, 424 LOC)
- **DAG-based** multi-step orchestration with `depends_on`
- `_toposort()` → parallel-executable layers
- `{{task_id.field}}` template substitution between steps
- `WorkflowResult` tracks per-task status, duration
- **Limitation**: NOT wired into autonomous loop. No persistence. No replanning. No confidence tracking. No expected outcomes. Triggered externally only via `trigger_workflow()`.

### 1.4 MissionRunner (`core/runtime/missions.py`, 900+ LOC)
- `Mission` + `MissionStep` + `MissionStore` (JSON-file persisted)
- Sequential step execution via `AutonomousExecutor.execute()`
- `ObjectiveDecomposer`: rule-based decomposition (split by "then"/"and"/";")
- `MissionPlanAdvisor`: LLM-based decomposition via ollama_safe.chat()
- `MissionRecoveryPolicy`: max_retries, retry_count, rollback_status
- `retry()`: resets failed step to "planned", bumps retry_count
- **Limitation**: Steps are sequential (no DAG). No expected_outcome per step. No replanning on failure — just hard stop. Not integrated into autonomous loop's think/act cycle.

### 1.5 Decision Engine (`core/loop/decision_engine.py`)
- 5-factor scoring: goal(30%) + confidence(25%) + policy(20%) + urgency(15%) + timing(10%) - cost(5%)
- Epistemic dampening (recently integrated)
- Evaluates candidates → picks single winner
- **Limitation**: Scores single actions, not plan steps. No awareness of plan context.

### 1.6 Autonomous Loop (`core/loop/autonomous_loop.py`)
- `_think_tick()`: goals → candidates → score → winner → `_act_on(winner)` — **one action per tick**
- `_act_on()`: routes through governor/permission_gateway
- No plan context in either method
- `trigger_workflow()` exists but is externally-triggered only

### 1.7 Summary of What Exists

| Capability | Goal System | Planner | WorkflowRunner | MissionRunner | Autonomous Loop |
|---|:---:|:---:|:---:|:---:|:---:|
| Multi-step | ✗ | ✗ | ✓ (DAG) | ✓ (seq) | ✗ |
| Persistence | ✓ (goals) | ✗ | ✗ | ✓ (JSON) | N/A |
| Dependencies | ✗ | ✗ | ✓ (depends_on) | ✗ | ✗ |
| Expected outcome | ✗ | ✗ | ✗ | ✗ | ✗ |
| Replanning | ✗ | ✗ | ✗ | ✗ (hard stop) | ✗ |
| Confidence | ✗ | ✗ | ✗ | ✓ (per-step) | ✓ (epistemic) |
| In think/act loop | ✓ (single) | ✓ (single) | ✗ | ✗ | ✓ |
| Retry/recovery | ✗ | ✗ | ✗ | ✓ (basic) | ✗ |

---

## 2. Exact Gap

**The fundamental gap is not a missing planner — it's the missing connection between planning and the autonomous loop.**

VECTOR can:
- Set goals ✓
- Score single actions ✓
- Execute single actions through permission gateway ✓
- Run multi-step workflows (externally triggered) ✓
- Persist missions to JSON ✓

VECTOR **cannot**:
1. **Decompose a goal into a persistent, ordered plan with dependencies**
   - `ObjectiveDecomposer` exists but is rule-based and crude (splits on "then"/"and")
   - No LLM-driven decomposition wired into the autonomous loop
   - WorkflowRunner has DAG deps but no persistence; MissionRunner has persistence but no DAG deps

2. **Pick up the next executable step from an active plan during `_think_tick()`**
   - The loop only generates candidates from goals → single actions
   - No awareness of in-progress plans or their next ready steps

3. **Verify step outcomes against expected results**
   - No `expected_outcome` field on any step type
   - `ExecutionReport.status` is just "executed"/"blocked"/"failed" — no outcome comparison

4. **Replan when a step fails**
   - MissionRunner just stops and marks "failed"
   - No mechanism to substitute a fallback step or restructure remaining steps

5. **Track confidence across plan steps**
   - EpistemicTracker tracks per-action-domain confidence
   - No per-step confidence or per-plan confidence trajectory

**Root cause statement**: The autonomous loop's `_think_tick()` only considers `goal → single action`. There is no code path that says "there is an active plan; here is the next ready step; score it as a candidate; execute it; verify the outcome; advance the plan."

---

## 3. Proposed Design

### 3.1 Core Principle: Extend, Don't Replace

**Do NOT create a second goal system, second decision engine, or bypass permission gateway.**

The design:
- Extends `MissionRunner` (already has persistence + step execution)
- Adds DAG dependency support (borrowed from WorkflowRunner's `_toposort()`)
- Adds expected_outcome, confidence, fallback to each step
- Wires into `_think_tick()` so plan steps become candidates alongside goal actions
- Uses existing `DecisionEngine.evaluate()` to score plan steps vs. goal actions
- Permission gateway remains the ONLY execution path

### 3.2 New Entity: `Plan` (extends Mission)

```
Plan
├── id: str (UUID)
├── goal_id: str (links to goal_system goal)
├── objective: str
├── status: planned | active | paused | completed | failed | abandoned
├── created_at, updated_at
├── steps: List[PlanStep]
├── progress: float (0.0–1.0)
├── confidence: float (rolling average of step confidences)
├── replan_count: int
├── events: List[PlanEvent]
└── artifacts: List[dict]
```

### 3.3 New Entity: `PlanStep` (extends MissionStep)

```
PlanStep
├── id: str (e.g., "step-1")
├── action_type: str
├── params: dict
├── depends_on: List[str] (step IDs — DAG, not just sequential)
├── expected_outcome: str (human-readable description of success)
├── verification: dict (machine-checkable outcome criteria)
│   ├── type: "status_check" | "api_check" | "file_exists" | "confidence_threshold"
│   └── criteria: dict (type-specific)
├── status: planned | ready | running | completed | failed | skipped | blocked
├── priority: int (1=highest)
├── estimated_time_sec: float
├── estimated_cost_inr: float
├── confidence: float (0.0–1.0, from epistemic tracker for this action_type)
├── fallback: Optional[PlanStepFallback]
│   ├── action_type: str
│   ├── params: dict
│   └── trigger: "failure" | "timeout" | "low_confidence"
├── actual_outcome: Optional[dict]
│   ├── status: str
│   ├── summary: str
│   └── verification_passed: bool
├── retry_info: Optional[dict]
│   ├── attempts: int
│   ├── last_error: str
│   └── next_retry_at: Optional[str]
└── completed_at: Optional[str]
```

### 3.4 Plan Lifecycle

```
                    ┌──────────────────────────────────────┐
                    │                                      │
  goal created ──► plan_decompose() ──► plan(status=active) │
                    │                                      │
                    ▼                                      │
            _think_tick() sees                             │
            plan with ready steps                          │
                    │                                      │
                    ▼                                      │
            next_ready_step() ──► candidate ──► score      │
                    │                                      │
                    ▼                                      │
            _act_on(plan_step) ──► permission_gateway      │
                    │                                      │
            ┌───────┴────────┐                             │
            ▼                ▼                             │
        success          failure                           │
            │                │                             │
            ▼                ▼                             │
     verify_outcome()   has_fallback?──yes──► run_fallback │
            │                │                             │
            ▼                no                            │
     advance_step()        replan()?──yes──► restructure   │
            │                │                             │
            ▼                no                            │
     all_done?──yes──► completed                           │
            │                                              │
            no ────────────────────────────────────────────┘
```

### 3.5 Integration into `_think_tick()`

**Current flow** (unchanged):
```
goals → generate_immediate_actions() → candidates → score → winner → act
```

**New flow** (plan-aware):
```
1. goals → generate_immediate_actions() → goal_candidates
2. active_plans → next_ready_steps() → plan_candidates
3. all_candidates = goal_candidates + plan_candidates
4. score all via decision_engine.evaluate()
5. winner = highest score
6. if winner is a plan_step:
     _act_on_plan_step(winner)  # still goes through permission_gateway
   else:
     _act_on(winner)  # existing single-action path
```

**Plan steps get a scoring bonus**: being part of an active plan adds +0.05 to urgency (plan momentum). This prevents goal-driven single actions from perpetually starving plan steps.

### 3.6 Decomposition Strategy

Reuse existing `MissionPlanAdvisor` (LLM-based) with enhancements:

```python
async def decompose_goal(goal: Goal) -> Plan:
    """Use LLM to decompose a goal into a Plan with ordered steps."""
    # 1. Try LLM decomposition via MissionPlanAdvisor
    advisor = MissionPlanAdvisor()
    llm_steps = await advisor.advise(goal.description)

    # 2. Enhance each step with: expected_outcome, verification, fallback
    for step in llm_steps:
        step.expected_outcome = _infer_expected_outcome(step)
        step.verification = _build_verification(step)
        step.fallback = _build_fallback(step)
        step.confidence = epistemic_tracker.get_confidence(step.action_type)

    # 3. Build dependency graph (LLM specifies depends_on)
    plan = Plan(goal_id=goal.id, objective=goal.description, steps=llm_steps)
    return plan
```

### 3.7 Outcome Verification

After each step executes, verify against expected outcome:

```python
async def verify_step_outcome(step: PlanStep, report: ExecutionReport) -> bool:
    """Check if actual outcome matches expected."""
    if step.verification["type"] == "status_check":
        return report.status == "executed"
    elif step.verification["type"] == "file_exists":
        return Path(step.verification["criteria"]["path"]).exists()
    elif step.verification["type"] == "api_check":
        # lightweight check — did the API return expected structure?
        return _check_api_response(report.result, step.verification["criteria"])
    elif step.verification["type"] == "confidence_threshold":
        new_conf = epistemic_tracker.get_confidence(step.action_type)
        return new_conf >= step.verification["criteria"]["min_confidence"]
    return report.status == "executed"  # fallback
```

### 3.8 Replanning on Failure

```python
async def replan(plan: Plan, failed_step: PlanStep) -> Plan:
    """Restructure remaining steps after a failure."""
    plan.replan_count += 1

    # Strategy 1: Try fallback if available
    if failed_step.fallback:
        replacement = failed_step.fallback.to_step()
        _replace_step(plan, failed_step.id, replacement)
        return plan

    # Strategy 2: Ask LLM to restructure
    if plan.replan_count <= 2:  # max 2 replans
        advisor = MissionPlanAdvisor()
        remaining = [s for s in plan.steps if s.status == "planned"]
        new_steps = await advisor.replan(
            objective=plan.objective,
            completed=[s for s in plan.steps if s.status == "completed"],
            failed=failed_step,
            remaining=remaining,
        )
        _replace_remaining(plan, new_steps)
        return plan

    # Strategy 3: Give up — mark plan as failed
    plan.status = "failed"
    plan.record_event("abandoned", "Replan budget exhausted")
    return plan
```

---

## 4. Database Schema

### 4.1 Storage: JSON File (consistent with existing MissionStore)

Plans persist to `data/plans/plans.json` — same pattern as `data/missions/missions.json`.

No new SQLite tables. JSON file survives restarts. `PlanStore` mirrors `MissionStore`.

### 4.2 Schema (as Python dataclasses)

```python
@dataclass
class PlanStepFallback:
    action_type: str
    params: dict
    trigger: str  # "failure" | "timeout" | "low_confidence"

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "PlanStepFallback": ...

@dataclass
class PlanStep:
    id: str
    action_type: str
    params: dict
    depends_on: list[str]           # default []
    expected_outcome: str           # default ""
    verification: dict              # default {"type": "status_check"}
    status: str                     # "planned" | "ready" | "running" | "completed" | "failed" | "skipped" | "blocked"
    priority: int                   # default 1
    estimated_time_sec: float       # default 60.0
    estimated_cost_inr: float       # default 0.0
    confidence: float               # default 0.5
    fallback: Optional[PlanStepFallback]  # default None
    actual_outcome: Optional[dict]  # default None
    retry_info: Optional[dict]      # default None
    completed_at: Optional[str]     # default None

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "PlanStep": ...

@dataclass
class PlanEvent:
    timestamp: str
    type: str       # "step_started" | "step_completed" | "step_failed" | "replan" | "completed" | "abandoned"
    message: str
    step_id: Optional[str] = None
    data: Optional[dict] = None

@dataclass
class Plan:
    id: str
    goal_id: str
    objective: str
    status: str             # "planned" | "active" | "paused" | "completed" | "failed" | "abandoned"
    steps: list[PlanStep]
    created_at: str
    updated_at: str
    progress: float         # 0.0–1.0
    confidence: float       # rolling avg of step confidences
    replan_count: int       # default 0
    events: list[PlanEvent] # default []
    artifacts: list[dict]   # default []

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "Plan": ...

    def next_ready_steps(self) -> list[PlanStep]:
        """Return steps whose dependencies are all completed and status is planned."""
        completed_ids = {s.id for s in self.steps if s.status == "completed"}
        ready = []
        for step in self.steps:
            if step.status != "planned":
                continue
            if all(dep_id in completed_ids for dep_id in step.depends_on):
                ready.append(step)
        return sorted(ready, key=lambda s: s.priority)

    def record_event(self, type_: str, message: str, step_id=None, data=None):
        self.events.append(PlanEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            type=type_, message=message, step_id=step_id, data=data,
        ))
```

### 4.3 PlanStore (JSON file persistence)

```python
class PlanStore:
    """JSON-file-backed plan persistence. Mirrors MissionStore pattern."""

    def __init__(self, path: Optional[str] = None):
        self._path = path or str(data_path("plans", "plans.json"))
        self.plans: list[Plan] = []
        self._load()

    def _load(self): ...
    def save(self): ...
    def add(self, plan: Plan): ...
    def get(self, plan_id: str) -> Optional[Plan]: ...
    def active_plans(self) -> list[Plan]: ...
    def plans_for_goal(self, goal_id: str) -> list[Plan]: ...
```

---

## 5. Integration Points

### 5.1 `autonomous_loop.py` — `_think_tick()` (MODIFY)

```python
# AFTER generating goal_candidates, add:
plan_candidates = self._get_plan_candidates()
candidates.extend(plan_candidates)

# New method:
def _get_plan_candidates(self) -> list[Candidate]:
    """Get next ready steps from all active plans."""
    plan_store = self._get_plan_store()
    candidates = []
    for plan in plan_store.active_plans():
        for step in plan.next_ready_steps()[:2]:  # max 2 per plan
            c = Candidate(
                action_type=step.action_type,
                params=step.params,
                goal_ids=[plan.goal_id],
                confidence=step.confidence,
                urgency=0.6 + 0.05,  # plan momentum bonus
                timing_score=1.0,
                estimated_cost_inr=step.estimated_cost_inr,
                source=f"plan:{plan.id}:{step.id}",
            )
            candidates.append(c)
    return candidates
```

### 5.2 `autonomous_loop.py` — `_act_on()` (MODIFY)

Add plan-step routing:
```python
async def _act_on(self, winner: Candidate) -> None:
    # NEW: Check if winner is from a plan
    if winner.source and winner.source.startswith("plan:"):
        await self._act_on_plan_step(winner)
        return
    # ... existing code unchanged ...
```

### 5.3 `autonomous_loop.py` — `_act_on_plan_step()` (NEW)

```python
async def _act_on_plan_step(self, winner: Candidate) -> None:
    """Execute a plan step through the normal permission gateway, then verify."""
    plan_id, step_id = winner.source.split(":")[1], winner.source.split(":")[2]
    plan = self._get_plan_store().get(plan_id)
    step = next(s for s in plan.steps if s.id == step_id)

    # Mark running
    step.status = "running"
    plan.record_event("step_started", f"Step {step.id} started", step_id=step.id)
    self._get_plan_store().save()

    # Execute through permission gateway (same as _act_on)
    report = await self._executor.execute(
        action_type=step.action_type,
        params=step.params,
        proposed_by=f"plan:{plan.id}",
    )

    # Verify outcome
    passed = await verify_step_outcome(step, report)
    step.actual_outcome = {
        "status": report.status,
        "summary": report.reason,
        "verification_passed": passed,
    }
    step.completed_at = datetime.now(timezone.utc).isoformat()

    if report.status == "executed" and passed:
        step.status = "completed"
        plan.record_event("step_completed", f"Step {step.id} verified", step_id=step.id)
    elif report.status == "executed" and not passed:
        # Execution succeeded but outcome didn't match expected
        step.status = "failed"
        plan.record_event("outcome_mismatch", f"Step {step.id} outcome didn't match expected", step_id=step.id)
    else:
        step.status = "failed"
        plan.record_event("step_failed", f"Step {step.id} failed: {report.reason}", step_id=step.id)

    # Replan if failed
    if step.status == "failed":
        await replan(plan, step)

    # Update plan progress
    completed = sum(1 for s in plan.steps if s.status == "completed")
    plan.progress = round(completed / max(1, len(plan.steps)), 3)
    plan.confidence = sum(s.confidence for s in plan.steps) / max(1, len(plan.steps))

    # Check completion
    if all(s.status in ("completed", "skipped") for s in plan.steps):
        plan.status = "completed"
        plan.record_event("completed", "All steps completed")

    self._get_plan_store().save()
```

### 5.4 `goal_system.py` (MODIFY — minimal)

When a new goal is created, trigger plan decomposition:
```python
async def add_goal(self, goal: Goal) -> None:
    # ... existing code ...
    # NEW: trigger plan decomposition for non-trivial goals
    if goal.horizon in ("MID", "LONG"):
        asyncio.create_task(self._decompose_to_plan(goal))
```

### 5.5 `decision_engine.py` (NO CHANGE)

Plan steps enter as regular Candidates. The existing scoring works.
The `source` field distinguishes plan steps from goal actions.

### 5.6 `permission_gateway.py` (NO CHANGE)

Plan steps execute through the same gateway as everything else.

### 5.7 `autonomous_loop.py` — `_reflect_tick()` (MODIFY — minor)

Add plan review to 2AM reflection:
```python
# During 2AM reflection, review active plans
for plan in plan_store.active_plans():
    if plan.confidence < 0.3 and plan.replan_count >= 2:
        plan.status = "abandoned"
        plan.record_event("abandoned", "Low confidence after multiple replans")
    # Decay stale plans
    age_days = (now - parse_time(plan.created_at)).days
    if age_days > 30 and plan.status == "active":
        plan.status = "paused"
        plan.record_event("paused", f"Stale plan ({age_days}d old)")
```

---

## 6. Failure Scenarios

| # | Scenario | Detection | Response |
|---|---|---|---|
| F1 | Step execution fails (permission denied, API error) | `report.status != "executed"` | Try fallback → replan (LLM) → abandon after 2 replans |
| F2 | Step succeeds but outcome doesn't match expected | `verify_step_outcome()` returns False | Mark step "failed" → replan |
| F3 | LLM decomposition produces invalid plan (circular deps) | `_toposort()` detects cycle | Fall back to rule-based `ObjectiveDecomposer` |
| F4 | Plan step depends on another step that never completes | `next_ready_steps()` never returns it | Stale detection in 2AM reflect → pause after 30d |
| F5 | Replan loop (keeps failing, keeps replanning) | `replan_count > 2` | Abandon plan, record in episodic memory |
| F6 | Plan decomposition itself fails (LLLM unreachable) | `MissionPlanAdvisor` timeout | Fall back to `ObjectiveDecomposer` (rule-based) |
| F7 | Process restart mid-plan | `PlanStore._load()` on startup | Plans resume from last saved state (JSON persisted) |
| F8 | Plan step timeout | `estimated_time_sec` exceeded | Mark step failed → fallback/replan |
| F9 | Goal expires while plan is active | `_prune_expired()` in goal_system | Plan status → "abandoned" (goal_id no longer valid) |
| F10 | Permission gateway blocks a plan step | `report.status == "blocked"` | Mark step "blocked" → try fallback action |

---

## 7. Safety Implications

### 7.1 Permission Gateway Is Untouched
Every plan step goes through the **same permission gateway** as single actions. No bypass. GREEN/YELLOW/RED rules apply equally. A plan to "exfiltrate data" gets blocked step-by-step exactly as a single action would.

### 7.2 No Second Decision Engine
Plan steps are scored by the **existing** `DecisionEngine.evaluate()` alongside goal actions. The same 5-factor scoring + epistemic dampening applies. Plan steps get a small urgency bonus (+0.05) but this is transparent in the reasoning chain.

### 7.3 Replan Budget
Max 2 replans per plan. Prevents infinite replan loops that could burn resources. After 2 replans, the plan is abandoned and the failure is recorded in episodic memory for future learning.

### 7.4 Plan Decomposition Is Conservative
LLM-generated plans go through the same `MissionPlanAdvisor` safety checks:
- Refined prompt asks for safe, minimal steps
- Rule-based fallback if LLM is unavailable
- Each step is individually scored and permission-gated

### 7.5 Auditability
Every plan event is recorded: step started, outcome, verification result, replan decisions. The `PlanEvent` log provides a full audit trail of why VECTOR took each step and what happened.

### 7.6 No Resource Exhaustion
Each step has `estimated_time_sec` and `estimated_cost_inr`. The decision engine already factors in cost. A plan with 20 expensive steps doesn't bypass the cost factor — each step is independently scored and must win against other candidates.

### 7.7 Human Override
Plans can be paused via the HUD dashboard (`/hud`). A paused plan's steps don't generate candidates.

---

## 8. Test Plan

### 8.1 Unit Tests (`tests/unit/test_planning.py`)

| Test | What It Verifies |
|---|---|
| `test_plan_creation` | Plan dataclass serializes/deserializes correctly |
| `test_plan_step_depends_on` | `next_ready_steps()` respects dependency graph |
| `test_plan_step_parallel_ready` | Independent steps both appear in `next_ready_steps()` |
| `test_plan_progress_calculation` | Progress = completed/total |
| `test_plan_confidence_rolling_avg` | Plan confidence = average of step confidences |
| `test_plan_event_recording` | Events are appended with correct timestamps |
| `test_plan_store_save_load` | Plans survive JSON round-trip |
| `test_plan_store_active_filter` | `active_plans()` returns only active plans |
| `test_plan_step_fallback_serialization` | Fallback round-trips through dict |
| `test_verify_outcome_status_check` | Status check verification works |
| `test_verify_outcome_failure` | Failed verification returns False |
| `test_replan_tries_fallback_first` | Fallback is attempted before LLM replan |
| `test_replan_budget_exhausted` | After 2 replans, plan is abandoned |
| `test_plan_candidates_generated` | `_get_plan_candidates()` returns correct Candidates |
| `test_plan_step_source_tag` | Candidate source = "plan:{plan_id}:{step_id}" |
| `test_plan_momentum_bonus` | Plan step candidates get +0.05 urgency |
| `test_circular_dependency_detection` | Cyclic deps are caught, plan falls back to rules |
| `test_goal_expiry_abandons_plan` | Expired goal → plan abandoned |

### 8.2 Integration Tests (`tests/integration/test_planning_integration.py`)

| Test | What It Verifies |
|---|---|
| `test_plan_decompose_and_execute` | Full: goal → decompose → execute all steps → completed |
| `test_plan_survives_restart` | Plan mid-execution → save → reload → resume from correct step |
| `test_plan_step_failure_triggers_replan` | Step fails → fallback runs → plan continues |
| `test_plan_outcome_verification` | Step succeeds but outcome wrong → replan |
| `test_plan_vs_goal_scoring` | Plan step competes fairly with goal action in decision engine |
| `test_plan_2am_reflect_review` | Stale plans get paused during 2AM reflection |
| `test_permission_gateway_blocks_plan_step` | RED policy → plan step blocked → fallback/replan |
| `test_epistemic_dampening_on_plan_steps` | Low-confidence plan steps get epistemic penalty |
| `test_plan_completed_updates_goal` | All steps done → goal marked progressed |
| `test_multiple_plans_concurrent` | Two plans active simultaneously — steps interleave correctly |

### 8.3 Regression Tests

Ensure existing systems still work:
- `tests/unit/test_goal_system.py` — goals still produce single actions when no plan exists
- `tests/unit/test_decision_engine.py` — scoring unchanged for non-plan candidates
- `tests/unit/test_epistemic_scoring.py` — epistemic dampening still works
- `tests/integration/test_epistemic_integration.py` — full cognitive loop unchanged

### 8.4 Manual Tests

1. Create a MID-horizon goal → verify plan is decomposed
2. Watch plan steps appear as candidates in `_think_tick()` logs
3. Verify plan step goes through permission gateway (check logs)
4. Simulate step failure → verify replan happens
5. Kill VECTOR mid-plan → restart → verify plan resumes
6. Check `/hud` shows active plans with progress

---

## Summary of Changes

| File | Action | Scope |
|---|---|---|
| `core/runtime/plans.py` | **CREATE** | Plan, PlanStep, PlanStore, PlanEvent, PlanRunner |
| `core/loop/autonomous_loop.py` | **MODIFY** | Add plan candidates to _think_tick, add _act_on_plan_step, add plan review to _reflect_tick |
| `core/brain/goal_system.py` | **MODIFY** | Trigger plan decomposition for MID/LONG goals |
| `core/loop/decision_engine.py` | **NO CHANGE** | Plan steps enter as regular Candidates |
| `core/loop/planner.py` | **MODIFY** | Delegate to plan system for multi-step goals |
| `core/runtime/missions.py` | **NO CHANGE** | Existing missions continue to work (API-triggered) |
| `core/loop/workflow_runner.py` | **NO CHANGE** | External DAG workflows continue to work |
| `tests/unit/test_planning.py` | **CREATE** | 18+ unit tests |
| `tests/integration/test_planning_integration.py` | **CREATE** | 10 integration tests |
| `data/plans/` | **CREATE DIR** | Plan JSON storage |
