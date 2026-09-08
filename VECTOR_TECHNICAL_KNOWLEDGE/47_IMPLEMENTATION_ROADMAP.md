# 47 — VECTOR Implementation Roadmap

**Date:** 2026-08-13
**Author:** Principal systems architect analysis, grounded in verified codebase state
**Inputs:** Documents 43 (Remediation), 44 (Unresolved Questions), 45 (JARVIS Gap Analysis), 46 (Cognitive Integration Audit)
**Source of truth:** Actual codebase files and line numbers — not prior audit claims

**Purpose:** Concrete implementation plan for the next 5 cognitive improvements. No new subsystems where existing ones extend. No speculative neural RL. No duplicate memory/context/planning. Preserve autonomous loop and safety boundaries.

---

## Executive Summary

VECTOR's verified cognitive runtime has **58 subsystems**, **7/8 JARVIS gaps wired**, and a functioning policy learning pathway (`policy.py` tabular averaging). The remaining cognitive frontier is not about building new subsystems — it's about **connecting existing, implemented-but-orphaned modules into the runtime loop** and **extending the proven policy.py pathway** with richer signal.

Five improvements are proposed in priority order. Total estimated effort: ~550 LOC. All extend existing modules; only two add new files (and both wrap existing components rather than introducing new state).

| # | Improvement | LOC | Closes | Risk |
|---|-------------|-----|--------|------|
| 1 | Wire EpistemicTracker into scoring | ~40 | JARVIS Gap 3 | Very low |
| 2 | Quantitative evaluation infrastructure | ~150 | Mandatory metric layer | Low |
| 3 | Owner-correction learning | ~60 | Safety + learning depth | Low |
| 4 | Multi-step planning (step_planner) | ~180 | Planning gap | Medium |
| 5 | Tool composition (plan_executor) | ~120 | Workflow gap | Medium |

---

## Verified Current State (Grounding)

These facts were confirmed by reading the actual source files during this analysis — not inherited from prior docs:

| Claim | Verified At | Status |
|-------|-------------|--------|
| EpistemicTracker implemented, orphaned from runtime | `core/brain/epistemic_tracker.py` (260 LOC) + `_get_epistemic()` at `decision_engine.py:191-199` never called | ✅ Confirmed orphaned |
| MetaCognition IS wired into scoring | `decision_engine.py:211-240` (`_bias_penalty()`) | ✅ Active |
| Counterfactual `should_avoid()` wired in `_act_on()` | `autonomous_loop.py:1017-1046` | ✅ Active |
| `record_rejection()` called from permission_gateway | `permission_gateway.py:530-537` (council rejection) | ✅ Active |
| Policy.py is the ONLY behavior-changing learning path | `autonomous_loop.py:973, 1040, 1170` | ✅ Confirmed |
| Neural training (6 RL algorithms) orphaned | `decision_engine.py:136-144, 152-189` has `record_outcome()` wired, but trained weights NEVER affect `_score_candidate()` | ✅ Orphaned |
| No strategic_planner.py or workflow_composer.py | Glob: no matches | ✅ Confirmed absent |
| GoalSystem does NOT decompose goals into sub-steps | `goal_system.py:212-241` returns SHORT-horizon actions only | ✅ Confirmed |
| 2AM reflect already calls MetaCognition monthly report | `autonomous_loop.py:1438-1445` | ✅ Active |
| DecisionEngine scores exactly 4 candidates per tick | `decision_engine.py:50-56` docstring | ✅ Confirmed |

---

## Improvement 1 — Wire EpistemicTracker into Scoring

**Capability gained:** VECTOR dampens confidence on actions touching stale/unknown domains — it "knows what it doesn't know" at decision time. Completes JARVIS Gap 3.

**Current implementation:**
- `core/brain/epistemic_tracker.py` (260 LOC) — SQLite-backed, tracks beliefs with confidence decay, TTL, staleness detection. Full API: `update_belief()`, `get_belief()`, `get_confidence()`, `get_knowledge_summary()`, `decay_all()`, `record_claim()`, `merge_belief()`, `get_stale_claims()`.
- `core/loop/decision_engine.py:191-199` — `_get_epistemic()` instantiates it lazily. **But `_get_epistemic()` is never called anywhere in the file.** The instance is created and discarded.
- `core/loop/autonomous_loop.py` — does not reference epistemic at all.

**Files involved:**
- `core/loop/decision_engine.py` (modify)
- `core/loop/autonomous_loop.py` (modify — reflect tick)
- `core/brain/epistemic_tracker.py` (no changes needed)

**Existing components reused:**
- The full `EpistemicTracker` class — already implemented, already persisted, already has a decay model.
- `_get_epistemic()` lazy init — already written.

**Missing connection:**
1. `_score_candidate()` does not consult epistemic confidence when scoring candidates.
2. `_act_on()` does not record action outcomes as belief updates.
3. `reflect_loop` does not call `decay_all()` to age stale beliefs.

**Proposed architecture:**

```
_score_candidate(candidate):
    ...existing 5-factor formula...
    epistemic = self._get_epistemic()
    if epistemic:
        # Look up confidence on the domain this action touches
        domain_claim = f"action_domain:{candidate.action_type.split('_')[0]}"
        conf = epistemic.get_confidence(domain_claim)
        if conf > 0.0:  # known domain
            # High epistemic confidence → no penalty
            # Low epistemic confidence → dampen total by up to 15%
            epistemic_factor = 0.85 + (0.15 * conf)
            candidate.total_score *= epistemic_factor

_act_on(winner):
    ...existing outcome logic...
    epistemic = self._get_epistemic()
    if epistemic:
        # Record belief about this action domain with outcome-derived confidence
        domain_claim = f"action_domain:{winner.action_type.split('_')[0]}"
        epistemic.merge_belief(domain_claim, f"last_outcome={result.status}", reward, "act_loop")

_reflect_tick():
    ...existing reflect steps...
    epistemic = self._get_epistemic()
    if epistemic:
        epistemic.decay_all()  # age all beliefs; stale ones hit 0
```

**Estimated LOC:** 40 (3 wiring points × ~13 lines each)

**Tests required:**
- Unit test: candidate touching a domain with epistemic confidence 0.3 scores lower than identical candidate with confidence 0.9.
- Unit test: `_act_on()` outcome updates epistemic belief for the relevant domain.
- Unit test: `decay_all()` called in reflect reduces confidence on aged beliefs.
- Integration test: end-to-end, a candidate in a low-confidence domain gets dampened, and over repeated successful actions the domain confidence rises.

**Regression risks:**
- Very low. Pure additive: if epistemic is unavailable, behavior is identical to today.
- EpistemicTracker's SQLite connection is process-local (same as CounterfactualMemory and MetaCognition) — no new concurrency hazard.

**Rollback strategy:**
- Single env flag: `VECTOR_EPISTEMIC_SCORING=0` bypasses all three wiring points.
- If issues arise, the wiring is in 3 isolated try/except blocks — removing them restores prior behavior exactly.

**Expected measurable improvement:**
- JARVIS Gap 3 closed: epistemic awareness goes from "implemented but dead" to "active in every decision."
- Quantitatively: variance in action confidence across domains should decrease over 7 days as epistemic confidence calibrates.
- Observable via the new evaluation infrastructure (Improvement 2): epistemic calibration score.

---

## Improvement 2 — Quantitative Autonomous Evaluation Infrastructure

**Capability gained:** VECTOR can measure its own capability over time — action success rate, learning velocity, goal progress rate, calibration error. Mandatory before any other improvement can be objectively evaluated.

**Current implementation:**
- `core/city/meta_cognition.py:423-485` — `get_monthly_report()` computes calibration, bias, domain breakdown. Called at 2AM reflect. Rich data but no aggregation across time.
- `core/memory/policy.py:125-134` — `get_stats()` returns total entries and avg reward. Never called outside self-test.
- `core/brain/goal_system.py:290-305` — `get_goal_summary()` returns text, not structured metrics.
- No central metrics store, no time-series data, no dashboard endpoint.

**Files involved:**
- `core/metrics/evaluation.py` (new, ~150 LOC)
- `core/loop/autonomous_loop.py` (modify — call `tick()` in reflect)
- `core/api/routers/brain.py` (modify — expose `/metrics` endpoint)

**Existing components reused:**
- `MetaCognition.get_calibration_report()` — already computes calibration error.
- `PolicyMemory.get_stats()` — already returns avg reward and count.
- `GoalSystem.get_active_goals()` — already returns progress values.
- `CounterfactualMemory.get_rejection_patterns()` — already returns rejection stats.
- SQLite for storage (same pattern as other modules, `data/evaluation.db`).

**Missing connection:**
- No module aggregates these existing stats into a time-series or produces daily snapshots.
- No API endpoint exposes metrics to the frontend/HUD.
- No module computes derived metrics (learning velocity, goal progress rate).

**Proposed architecture:**

```python
# core/metrics/evaluation.py

class EvaluationEngine:
    """Rolling quantitative evaluation of VECTOR's cognitive performance.
    Reuses MetaCognition, PolicyMemory, GoalSystem, CounterfactualMemory.
    Stores daily snapshots in SQLite for trend analysis.
    """

    def tick(self) -> dict:
        """Called once per 2AM reflect. Computes daily snapshot, stores it."""
        snapshot = {
            "date": today_iso,
            "action_success_rate": self._success_rate_24h(),
            "avg_reward": self._avg_reward_24h(),
            "policy_learning_rate": self._policy_learning_rate(),
            "goal_progress_velocity": self._goal_velocity(),
            "calibration_error": self._calibration_error(),
            "epistemic_coverage": self._epistemic_coverage(),
            "rejection_rate": self._rejection_rate(),
            "active_goals_count": self._active_goal_count(),
        }
        self._persist_snapshot(snapshot)
        return snapshot

    def get_dashboard(self) -> dict:
        """Current state: latest snapshot + 7d/30d trends."""
        ...

    # Internal methods delegate to existing modules:
    # _success_rate_24h()       → episodic_memory WHERE event_type='act' AND created_at > 24h ago
    # _avg_reward_24h()         → episodic_memory reward field average
    # _policy_learning_rate()   → PolicyMemory: count of entries updated in last 24h
    # _goal_velocity()          → GoalSystem: avg progress delta across active goals
    # _calibration_error()      → MetaCognition.get_calibration_report()['calibration_error']
    # _epistemic_coverage()     → EpistemicTracker.get_knowledge_summary()['fresh_beliefs'] / total
    # _rejection_rate()         → CounterfactualMemory: rejections in 24h / total actions
```

**Estimated LOC:** 150

**Tests required:**
- Unit test: `tick()` returns dict with all required keys, values in [0.0, 1.0].
- Unit test: `get_dashboard()` returns valid JSON-serializable structure.
- Integration test: two consecutive `tick()` calls produce a non-empty trend.
- Endpoint test: `/metrics` returns 200 with expected schema.

**Regression risks:**
- Low. Read-only aggregation over existing data sources. No mutation of policy, goal, or memory state.
- New SQLite file (`data/evaluation.db`) — same pattern as `counterfactual.db`, `meta_cognition.db`, `epistemic.db`.

**Rollback strategy:**
- Remove the `tick()` call from `_reflect_tick()` — the rest of the system is unchanged.
- The evaluation.db can be deleted without affecting any other subsystem.

**Expected measurable improvement:**
- First time VECTOR can answer: "Am I getting better?" with data, not vibes.
- Provides the measurement substrate for evaluating improvements 3, 4, 5.
- Exposes trends via HUD for owner visibility.

---

## Improvement 3 — Owner-Correction Learning

**Capability gained:** When the owner says "no don't do that" or redirects VECTOR in chat, the system records it as a rejection signal that future `should_avoid()` calls consult. Closes the loop from "owner said no" → "policy updated" → "future behavior changes."

**Current implementation:**
- `core/memory/counterfactual.py:177-197` — `record_rejection()` stores (decision_id, proposal, reason, context).
- `core/memory/counterfactual.py:216-228` — `should_avoid()` checks new proposals against stored rejections via Jaccard similarity. Wired in `_act_on()`.
- `core/loop/permission_gateway.py:530-537` — calls `record_rejection()` on council/owner rejection through the HUD.
- `core/loop/autonomous_loop.py:294-306` — `_scan_incoming()` already checks incoming text, but does NOT extract owner corrections.
- Governor's `answer_question()` path processes incoming owner chat — but chat-based corrections ("don't do X", "stop doing Y") are not captured.

**Files involved:**
- `core/memory/counterfactual.py` (modify — add `source` field distinction)
- `core/loop/autonomous_loop.py` (modify — extract corrections from owner chat)
- `core/city/governor.py` (modify — record correction before processing)

**Existing components reused:**
- `CounterfactualMemory.record_rejection()` — already stores rejections.
- `CounterfactualMemory.should_avoid()` — already blocks similar proposals.
- `PolicyMemory.update_from_outcome()` — can be called with reward=0.0 on owner correction to immediately dampen the action.

**Missing connection:**
- Owner chat corrections ("don't send emails like that", "stop posting about X") do not flow into counterfactual or policy.
- `record_rejection()` does not distinguish between "council rejected because dangerous" and "owner rejected because stylistically wrong" — both are useful but have different generalization properties.

**Proposed architecture:**

```python
# counterfactual.py — extend rejections table
# Add column: source TEXT DEFAULT 'council'
# Values: 'council', 'owner', 'owner_correction', 'self_detected'

# governor.py — detect and record owner corrections
def _detect_owner_correction(text: str) -> Optional[str]:
    """Pattern-match owner corrections: 'don't X', 'stop X', 'no X', 'I said no X'."""
    patterns = [
        r"(?:don't|do not|stop|never|no)\s+(.+)",
        r"I (?:said|told you) (?:not to|don't) (.+)",
        r"wrong[,.] (.+)",
    ]
    for p in patterns:
        m = re.search(p, text.lower())
        if m:
            return m.group(1).strip()
    return None

# In governor.answer_question() or dispatch path:
correction = _detect_owner_correction(incoming_text)
if correction:
    CounterfactualMemory().record_rejection(
        decision_id=f"owner_corr_{uuid4().hex[:8]}",
        proposal=correction,
        reason="owner_correction",
        context={"source": "owner_correction", "original_text": incoming_text},
    )
    # Also feed policy immediately: any action_type matching the correction gets dampened
    pm = PolicyMemory()
    h = pm.make_situation_hash({"owner_correction": correction})
    pm.update_from_outcome(correction, h, reward=0.1)  # strong negative signal
```

**Estimated LOC:** 60

**Tests required:**
- Unit test: `_detect_owner_correction("don't send emails like that")` returns "send emails like that".
- Unit test: detected correction flows into counterfactual.rejections with `source='owner_correction'`.
- Unit test: `should_avoid("send similar emails")` returns True after owner correction recorded.
- Integration test: owner sends correction, subsequent similar proposal is blocked by `_act_on()`.

**Regression risks:**
- Low-moderate. Regex-based detection may false-positive on casual "don't" usage. Mitigate by requiring the correction to match an action-like pattern (verb + object).
- If false-positive rate is too high, gate behind confidence threshold: only record if ≥2 signals align (regex + LLM classification).

**Rollback strategy:**
- Env flag: `VECTOR_OWNER_CORRECTION_LEARNING=0` bypasses detection.
- Owner corrections are stored with a distinct `source` — easy to filter them out if they cause problems.

**Expected measurable improvement:**
- Owner corrections go from "forgotten after the chat" to "permanently influence future decisions."
- Safety impact: VECTOR stops repeating rejected behaviors without owner having to reject twice.
- Measurable via evaluation infrastructure: rejection_rate for owner-corrected action types should drop to near-zero within 48h of correction.

---

## Improvement 4 — Multi-Step Planning (step_planner)

**Capability gained:** VECTOR decomposes SHORT-horizon goals into ordered sub-steps, executes them sequentially, and replans on failure. Closes the planning gap (scorecard §6: 45%).

**Current implementation:**
- `core/brain/goal_system.py:212-241` — `generate_immediate_actions()` returns SHORT-horizon goals as single actions. No decomposition.
- `core/loop/decision_engine.py` — scores 4 candidates per tick, picks the winner. No sequencing.
- `core/loop/autonomous_loop.py:_act_on()` — executes one candidate, records outcome. No notion of a plan.
- No `strategic_planner.py` exists (Glob: no matches).

**Files involved:**
- `core/brain/step_planner.py` (new, ~180 LOC)
- `core/loop/autonomous_loop.py` (modify — integrate plan execution into `_act_on()`)

**Existing components reused:**
- `GoalSystem.get_active_goals("SHORT")` — provides the goal to decompose.
- `DecisionEngine` — scores each sub-step as a regular Candidate.
- `PolicyMemory` — tracks outcome per sub-step (same situation_hash mechanism).
- `CounterfactualMemory` — if a plan fails, record it as a rejection so similar plans get avoided.
- `ContextEngine.session_hydration_prompt()` — each sub-step gets hydrated like any other LLM call.

**Missing connection:**
- No module takes a goal and produces an ordered list of sub-steps.
- No execution wrapper sequences multiple `_act_on()` calls and aborts on failure.

**Proposed architecture:**

```python
# core/brain/step_planner.py

class StepPlanner:
    """Decompose SHORT-horizon goals into ordered sub-steps.
    Uses a lightweight LLM call (Ollama, vector-focus) with structured output.
    Does NOT store long-term state — pure function: goal → [sub-step].
    """

    def decompose(self, goal: dict, context: dict) -> list[dict]:
        """Return ordered list of sub-steps: [{action_type, params, description, success_criteria}].
        Falls back to single-step (the goal itself as one action) if decomposition fails.
        """
        ...

    def replan(self, goal: dict, completed_steps: list[dict], failed_step: dict, context: dict) -> list[dict]:
        """Given a failed plan, return remaining steps adjusted for the failure.
        Feeds failed_step to CounterfactualMemory for future avoidance.
        """
        ...

# autonomous_loop.py — plan execution in _act_on()

async def _act_on(self, winner):
    # Check if winner is a plan (has plan_id in params)
    plan = winner.params.get("plan")
    if plan:
        await self._execute_plan(plan)
    else:
        await self._execute_single(winner)  # existing logic

async def _execute_plan(self, plan):
    for i, step in enumerate(plan["steps"]):
        candidate = Candidate(
            action_type=step["action_type"],
            params=step["params"],
            ...
        )
        result = await self._execute_single(candidate)
        if result.get("status") != "ok":
            # Record failure, replan
            CounterfactualMemory().record_rejection(...)
            remaining = self._step_planner.replan(plan["goal"], plan["steps"][:i], step, ...)
            if remaining:
                await self._execute_plan({"goal": plan["goal"], "steps": remaining})
            return
```

**Estimated LOC:** 180

**Tests required:**
- Unit test: `decompose()` returns ≥2 steps for a non-trivial goal, 1 step for a trivial goal.
- Unit test: `replan()` returns adjusted steps after a failure, and records the failure in CounterfactualMemory.
- Integration test: a 3-step plan executes in order, step 2 failure aborts step 3 and triggers replan.
- Integration test: plan execution does not bypass PermissionGateway — each step goes through normal gating.

**Regression risks:**
- Medium. New execution path (_execute_plan) could introduce edge cases around partial-plan execution.
- Mitigate: each step in the plan goes through the SAME `_execute_single()` path with full policy/counterfactual/permission gating. The plan is just a sequencing wrapper.
- LLM-based decomposition may produce malformed plans. Mitigate: strict schema validation, fall back to single-step on parse failure.

**Rollback strategy:**
- Env flag: `VECTOR_STEP_PLANNING=0` bypasses plan detection — all candidates execute as single steps (current behavior).
- The plan execution path is additive — removing it restores the single-candidate flow exactly.

**Expected measurable improvement:**
- Planning scorecard category: 45% → 65% (ordered sub-goal execution exists).
- Goal progress velocity (measured by Improvement 2) should increase for multi-step goals.
- Counterfactual rejection patterns should show plan-level failures, enabling higher-order learning.

---

## Improvement 5 — Tool Composition (plan_executor)

**Capability gained:** Multiple tool calls can be composed into a pipeline with one permission approval, executing in sequence with failure-abort semantics. Current system is one-tool-per-action.

**Current implementation:**
- Governor's `dispatch()` sends one task_type to one agent. No chaining.
- PermissionGateway approves one action at a time. Multi-step workflows require multiple approvals.
- District agents call one tool per action (verified in blog_publisher.py, research agents).

**Files involved:**
- `core/brain/plan_executor.py` (new, ~120 LOC)
- `core/loop/permission_gateway.py` (modify — batch approval for plans)
- `core/city/governor.py` (modify — accept pipeline dispatch)

**Existing components reused:**
- `DecisionEngine` — each pipeline step is scored as a Candidate.
- `PermissionGateway` — extended to approve a plan as a unit (all steps GREEN/YELLOW → one approval).
- `PolicyMemory` — per-step reward tracking.
- `_act_on()` — each step uses the existing execution path.

**Missing connection:**
- No way to declare "these 3 actions form one plan" and get a single approval.
- No execution wrapper sequences steps and aborts on failure.

**Proposed architecture:**

```python
# core/brain/plan_executor.py

class PlanExecutor:
    """Execute a sequence of tool calls as a single approved plan.
    Each step goes through the normal _act_on flow.
    If any step fails, remaining steps are aborted.
    Permission approval is batched: one GREEN/YELLOW check for the whole plan.
    """

    async def execute(self, plan: list[Candidate], context: dict) -> dict:
        results = []
        for i, candidate in enumerate(plan):
            # Each step still goes through full policy + counterfactual + permission
            result = await self._execute_step(candidate, is_plan_step=True)
            results.append(result)
            if result.get("status") != "ok":
                # Abort remaining steps
                for remaining in plan[i+1:]:
                    results.append({"status": "aborted", "reason": f"step {i} failed"})
                break
        return {"results": results, "plan_status": "complete" if all ok else "partial"}

# permission_gateway.py — batch approval
def approve_plan(self, plan: list[Candidate]) -> GatewayResult:
    """Approve a multi-step plan. If ALL steps are GREEN/YELLOW, one approval suffices.
    If ANY step is RED, the plan goes through normal RED flow.
    """
    max_level = max(classify(step.action_type) for step in plan)
    if max_level == 'RED':
        # Fall back to per-step RED approval
        return self.execute(plan[0])  # only first step, rest wait
    # All GREEN/YELLOW → approve as unit
    return GatewayResult(True, max_level, True, {}, 'Plan approved')
```

**Estimated LOC:** 120

**Tests required:**
- Unit test: 3-step GREEN plan gets single approval, executes in order.
- Unit test: step 2 failure aborts step 3, result reflects partial execution.
- Unit test: plan containing a RED step falls back to per-step RED approval.
- Integration test: plan execution does not bypass policy.get_score() or counterfactual.should_avoid() for any step.

**Regression risks:**
- Medium. Batch approval reduces owner oversight for multi-step workflows. Mitigate: plan approval shows ALL steps to the owner before greenlighting.
- Partial execution leaves the system in a mid-plan state. Mitigate: record plan state in episodic_memory so reflect can analyze partial failures.

**Rollback strategy:**
- Env flag: `VECTOR_PLAN_EXECUTION=0` — all plans execute as individual actions with per-action approval.
- PlanExecutor is additive — no existing single-action flow changes.

**Expected measurable improvement:**
- Tool execution scorecard: 80% → 90% (multi-step workflows possible).
- Task completion rate should increase for multi-step owner requests.
- Plan success/failure patterns feed CounterfactualMemory → higher-order learning.

---

## A. Recommended Order

```
1. Wire EpistemicTracker (40 LOC, 1 day)
   └─ Closes JARVIS Gap 3. Zero new modules. Pure connection work.
   └─ Unblocks Improvement 2's epistemic_coverage metric.

2. Evaluation infrastructure (150 LOC, 2-3 days)
   └─ Mandatory substrate: all later improvements need measurement.
   └─ Exposes metrics via HUD immediately.
   └─ No dependency on other improvements (reads existing data only).

3. Owner-correction learning (60 LOC, 1 day)
   └─ Extends proven policy.py pathway with richer signal.
   └─ High safety value: VECTOR stops repeating corrected behavior.
   └─ Depends on Improvement 2 for measurable verification.

4. Multi-step planner (180 LOC, 3-4 days)
   └─ Genuine cognitive leap. Largest single improvement.
   └─ Depends on Improvements 1-3 being stable (plan scoring uses epistemic + policy + counterfactual).
   └─ Moderate risk — new execution path.

5. Tool composition (120 LOC, 2 days)
   └─ Depends on Improvement 4 being stable (plans compose tools).
   └─ Lowest priority because current single-tool execution is adequate for most tasks.
   └─ Becomes critical only when owner regularly requests multi-step workflows.
```

**Rationale for this order:**
- Improvements 1-3 are low-risk, high-value, and extend existing modules. They should land first.
- Improvement 2 is mandatory infrastructure — it's the measuring stick for everything else.
- Improvement 4 is the highest-value cognitive leap but carries the most risk. It benefits from improvements 1-3 being stable because its plan scoring uses epistemic confidence, policy scores, and counterfactual avoidance.
- Improvement 5 is the natural extension of 4 but is not urgent until the owner's workflow patterns demand it.

---

## B. What NOT to Build Yet

| Candidate | Why Not |
|-----------|---------|
| **Neural RL wiring** (6 algorithms in `neural_training.py`) | Weights never reach `_score_candidate()`. `policy.py` tabular averaging is the proven production learning path. No evidence that wiring RL improves over tabular at VECTOR's scale (~100 actions/day). Revisit when evaluation infrastructure (Imp 2) shows policy convergence stalls. |
| **Self-narrative module** (autobiographical memory) | Needs evaluation infrastructure first to measure value. Current `agent_history` + `ghost memory` already provides cross-generational learning. Autobiographical reasoning is a luxury, not a bottleneck. |
| **New memory systems** | 5 core tables + LightRAG + semantic + episodic already exist. Adding another memory layer before consolidating existing ones violates "do not create duplicate memory." |
| **New context engine** | `ContextEngine.session_hydration_prompt()` is working and wired before every LLM call (Rule 1). No evidence of inadequacy. |
| **New world model** | `ContextEngine` already serves as the world-state provider. DecisionEngine receives `context_snapshot`. Extending ContextEngine is appropriate; replacing it is not. |
| **Full strategic_planner** (multi-month horizon) | The StepPlanner (Improvement 4) handles SHORT-horizon decomposition. Multi-month strategic planning requires a goal-decomposition engine that doesn't exist and isn't needed until SHORT-horizon planning is proven. |
| **Person model** (JARVIS Gap 7) | No current infrastructure for theory-of-mind per person. Needs evaluation data on where person-modeling would help. Defer until InteractionAnalyzer (already exists in some districts) produces evidence. |

---

## C. What Can Be Deleted (After Reachability Verification)

These modules are suspected dead code per doc 46 but must be verified reachable before deletion:

### 5 Orphaned Guidance Modules
| Module | Location | Suspected Status | Verification Method |
|--------|----------|------------------|---------------------|
| CollusionDetector | `core/brain/collusion_detector.py` | Orphaned | `grep -r "collusion_detector" core/ districts/` — if no imports, safe to delete |
| MemoryQuorum | `core/brain/memory_quorum.py` | Orphaned | `grep -r "memory_quorum" core/ districts/` |
| AuthorityGate | `core/brain/authority_gate.py` | Orphaned | `grep -r "authority_gate" core/ districts/` |
| EconomicGovernor | `core/brain/economic_governor.py` | Orphaned | `grep -r "economic_governor" core/ districts/` |
| CoherenceScheduler | `core/brain/coherence_scheduler.py` | Orphaned | `grep -r "coherence_scheduler" core/ districts/` |

### 8 Dead Code Modules (from doc 46)
Verify each with grep + runtime log analysis (run VECTOR for 24h, check if any log line references the module):

| Module | Suspected Status |
|--------|------------------|
| Dead code modules identified in cognitive audit | Run `python scripts/reachability_check.py` (to be written) |

### Neural Training (Conditional)
| Module | Condition for Deletion |
|--------|------------------------|
| `vectorcode/src/neural_training.py` (6 RL algorithms) | If after Improvement 2 lands, evaluation shows policy.py convergence is adequate AND no plan exists to wire neural RL in the next quarter. Currently: `record_outcome()` trains but weights never affect scoring — effectively orphaned but harmless. |

**Deletion protocol:**
1. For each module: `grep -r "import.*module_name" --include="*.py"` — if zero matches, it's unreachable.
2. Run VECTOR for 24h with `loguru` at DEBUG level. If no log line references the module, confirm orphaned.
3. Move to `core/_deprecated/` (not delete immediately) for one release cycle.
4. After 7 days with no issues, permanently delete.

---

## D. First Implementation Task

**Start immediately: Improvement 1 — Wire EpistemicTracker into `decision_engine._score_candidate()`.**

**Why this first:**
- 40 LOC. Can be done in one session.
- Zero new files, zero new dependencies.
- Closes JARVIS Gap 3 (the only genuinely orphaned gap module).
- No regression risk (additive, behind try/except, with env flag bypass).
- Unblocks Improvement 2's `epistemic_coverage` metric.
- Proves the pattern: "connect existing orphaned modules" before building new ones.

**Exact steps:**

1. Open `core/loop/decision_engine.py`.
2. In `_score_candidate()` (line ~271), after the existing 5-factor computation (line ~297), add:
   ```python
   # Epistemic confidence dampening (JARVIS Gap 3)
   if CONFIG.get("epistemic_scoring", True):
       try:
           epistemic = self._get_epistemic()
           if epistemic:
               domain = candidate.action_type.split("_")[0]
               claim_id = f"action_domain:{domain}"
               conf = epistemic.get_confidence(claim_id)
               if conf > 0.0:
                   epistemic_factor = 0.85 + (0.15 * conf)
                   candidate.total_score = round(candidate.total_score * epistemic_factor, 4)
                   candidate.reasoning_chain.append(
                       {"factor": "epistemic_confidence", "value": conf, "weight": epistemic_factor}
                   )
       except Exception as e:
           logger.debug(f"[VECTOR][decision_engine] epistemic scoring skipped: {e}")
   ```
3. In `_act_on()` (line ~904), after the existing reward computation (line ~1170), add:
   ```python
   # Record epistemic belief about this action domain
   if CONFIG.get("epistemic_scoring", True):
       try:
           epistemic = self._get_epistemic()
           if epistemic:
               domain = winner.action_type.split("_")[0]
               claim_id = f"action_domain:{domain}"
               epistemic.merge_belief(claim_id, f"last_outcome={result.get('status')}", reward, "act_loop")
       except Exception as e:
           logger.debug(f"[VECTOR][decision_engine] epistemic belief update skipped: {e}")
   ```
4. In `autonomous_loop.py:_reflect_tick()` (line ~1385), add near the meta_cognition block:
   ```python
   # Epistemic decay — age all beliefs
   try:
       from core.brain.epistemic_tracker import EpistemicTracker
       decayed = EpistemicTracker().decay_all()
       logger.info(f"[VECTOR][reflect] epistemic decay: {decayed} beliefs updated")
   except Exception as e:
       logger.warning(f"[VECTOR][reflect] epistemic decay skipped: {e}")
   ```
5. Write unit tests in `tests/unit/test_epistemic_scoring.py`.
6. Run full test suite: `python scripts/syntax_check.py && python -m pytest tests/ -x`.
7. Run VECTOR for 24h, verify epistemic beliefs populate in `data/epistemic.db`.

**Acceptance criteria:**
- [ ] All existing tests pass.
- [ ] New unit tests pass.
- [ ] After 24h runtime, `data/epistemic.db` contains ≥10 claims with non-zero confidence.
- [ ] Decision logs show `epistemic_confidence` in `reasoning_chain` for candidates in known domains.
- [ ] Evaluation dashboard (once Improvement 2 lands) shows non-zero `epistemic_coverage`.

---

## Appendix: Cross-References

| Document | Relevance |
|----------|-----------|
| `43_REMEDIATION_REPORT.md` | 50 bugs fixed; all tests passing. This roadmap starts from a clean, verified baseline. |
| `44_UNRESOLVED_SYSTEM_QUESTIONS.md` | 4 questions resolved (Q1.2, Q3.1, Q8.3, Q9.2). Remaining questions are lower priority than the 5 improvements here. |
| `45_JARVIS_GAP_ANALYSIS.md` | Corrected scorecard. This roadmap closes Gap 3 (EpistemicTracker) and improves Planning (§6) and Learning (§11). |
| `46_COGNITIVE_INTEGRATION_AUDIT.md` | Identified 58 subsystems, 5 orphaned guidance modules, 8 dead code modules. This roadmap addresses the highest-value orphan (EpistemicTracker) first. |

---

## Appendix: Constraint Compliance

| Constraint | Compliance |
|------------|------------|
| 1. Identify 5 highest-value improvements | ✅ Epistemic, Evaluation, Owner-correction, Planning, Tool composition |
| 2. Prioritize by cognitive/reliability/safety/complexity/regression/dependency | ✅ Order reflects this (see Section A) |
| 3. Extend existing subsystems, don't add new | ✅ Only 2 new files (step_planner, plan_executor), both wrap existing components |
| 4. Don't add neural RL merely because it exists | ✅ Neural RL explicitly deferred (Section B) |
| 5. Don't create duplicate memory/context/planning | ✅ All improvements reuse existing modules |
| 6. Preserve autonomous loop and safety boundaries | ✅ All changes additive; PermissionGateway unchanged for single actions |
| 7. Treat policy.py as production learning | ✅ Owner-correction extends policy.py; neural RL deferred |
| 8. EpistemicTracker as candidate priority | ✅ Improvement 1 |
| 9. Multi-step planning as candidate priority | ✅ Improvement 4 |
| 10. Owner-correction learning as candidate priority | ✅ Improvement 3 |
| 11. Tool composition as candidate priority | ✅ Improvement 5 |
| 12. Quantitative evaluation as mandatory | ✅ Improvement 2 |

---

**End of Roadmap**
