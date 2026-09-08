# E2 — Outcome Attribution

**Starting HEAD:** `7f305271aa298be163bd1524a323b66eafe4dfe6` (the E1 checkpoint). Clean tree,
confirmed before starting.

## Question

Does VECTOR know what happened AFTER a decision? Trace decision → execution → result → attribution
→ reward/update, and classify each reward writer by whether it uses a real outcome or a hardcoded
value.

## Method

Direct re-inspection of every reward-writing call site inside `core/loop/autonomous_loop.py`'s
`_act_on()` / `_act_on_plan_step()` family (already substantially mapped during R7/R8/R9's own work
this session), cross-checked for identity consistency against `PolicyMemory.make_situation_hash()`
and `DecisionEngine._score_candidate()`'s reader.

## Findings

### 1. Which outcomes exist

`result.get("status")` (real, district-reported via `governor.dispatch()`), `result.get(
"goal_progress")` (real if a district reports it, else a documented default), `result.get(
"overridden")`/`result.get("corrected")` (real flags when present), `vc_result.get("status")`
(VectorCode bridge), plan-step `result.get("status")`/`result.get("plan_progress")`.

### 2/3. Which carry decision_id / candidate_id

Per R7/R10: the episodic `decision_candidate` log, `CounterfactualMemory.rejections`,
`loop_state.save_decision()`, and `reasoning_chains.steps`' correlation entry all carry both.
`PolicyMemory.update_from_outcome()` deliberately does not (aggregate row, R7/R9's own documented,
unchanged decision).

### 4/5. Reward writers: real vs. hardcoded

| Writer | Location | Real or hardcoded? |
|---|---|---|
| Main path | `_act_on()` ~line 1313 | **Mostly real**: `uf*0.40 + goal_progress*0.25 + not_overridden*0.15 + not_corrected*0.15 + completed*0.05`. `uf` (user feedback) uses a real episodic-memory-recalled value when present, else a completion-based estimate (`0.7`/`0.3`). `goal_progress` uses the district's real reported value when present, else a **documented hardcoded 0.5 default** — a real fallback, not silently pretended-real. |
| VectorCode path | `_act_on()` ~line 1092 | **Hardcoded binary**: `0.8` if `status=="ok"` else `0.3`. Not a computed signal. |
| Plan-step path | `_act_on_plan_step()` ~line 1596 | **Hardcoded binary**: `0.7` if `status=="completed"` else `0.3`. Not a computed signal. |

Neither hardcoded-binary writer is a newly-discovered defect — they are documented, deliberate
simplifications (a binary success/failure proxy), not a reader/writer mismatch. **No fix was made to
either reward VALUE** — E2's mandate is attribution correctness, not reward-formula redesign, and
these are honestly reported here rather than silently treated as "real."

### 6. Which paths are dead

None of the reward writers themselves are dead — all three are reachable from real production call
sites. (`validate_lesson()`, found dead in R8, is a correction-learning mechanism, not a reward
writer, and is out of this stage's scope.)

### THE BUG FOUND AND FIXED: plan-step reward used a non-canonical identity

The plan-step writer computed its own situation hash independently:
```python
sk = f"plan_step:{winner.action_type}:{json.dumps(winner.params, sort_keys=True, default=str)}"
h = hashlib.sha256(sk.encode()).hexdigest()[:12]
```
— a **completely separate identity namespace** from `PolicyMemory.make_situation_hash()`, which
every other writer (the main path, the VectorCode path) and the ONE reader
(`decision_engine._score_candidate()` → `get_score()`) already use. A reward learned from executing a
plan step could never be read back by `DecisionEngine` scoring the identical `(action_type, params)`
as a regular goal-action candidate, and vice versa — the reward was genuinely recorded, but
effectively **unattributable** to any future decision about the same real situation. This is exactly
the audit question "which reward writers use real outcomes" sharpened one level further: even a
"real" reward is worthless for attribution if it is filed under a key nothing else will ever read.

This exact writer was already identified during Task 89 (D2) as a 4th non-canonical `PolicyMemory`
caller and explicitly deferred — quoting that session's own record: *"deliberately left untouched
(identity-merge design question, explicitly deferred)."* E2's mandate ("If minimal wiring is
justified, implement it") is the explicit authorization to resolve that deferral now.

## Implementation

`core/loop/autonomous_loop.py::_act_on_plan_step()`: replaced the ad-hoc `hashlib.sha256(f"plan_step:
...")` construction with `pm.make_situation_hash(winner.action_type, winner.params)` — the exact
same call every other writer and the one real reader already make. No new identity system, no schema
change, no reward-value change. Historical `plan_step:`-hashed rows in `policy_memory` are neither
migrated nor deleted — they simply stop being written to going forward, and nothing reads them by
that key today (nothing ever did), so no data is lost or corrupted.

## Tests

`tests/test_e2_outcome_attribution.py` — **7 tests, all passing**:

- `TestPlanStepIdentityFix` (3 tests) — proves the old ad-hoc hash construction is gone from the
  actual method body (not just from a casual grep, which would false-positive on the explanatory
  comment left in place); proves the fixed writer calls the real canonical
  `make_situation_hash()`; and a full behavioral proof — a reward recorded exactly the way the fixed
  writer now does it is genuinely readable back through `decision_engine`'s own independent hash
  reconstruction for the identical situation (the precise causal connection that was broken before).
- `TestRewardWriterHonesty` (4 tests) — direct source-level assertions (not prose) confirming which
  reward writer uses the real weighted formula, which two use hardcoded binaries, and that the
  `goal_progress` fallback-to-`0.5` default remains visible in source (so this report cannot silently
  drift out of sync with the actual code) — plus a signature-unchanged proof that
  `PolicyMemory.update_from_outcome()`'s contract itself was never touched.

## Regression comparison

Targeted regression (`tests/test_e2_outcome_attribution.py` + `tests/integration/test_planning_integration.py`
+ `tests/unit/test_planning.py` + R6/R7/R8/R9's own test suites + `tests/unit/test_decision_engine.py`
+ `tests/test_decision_engine.py`, excluding the 4 known pre-existing baseline failures by name):
**0 failures.** The 2 pre-existing `test_planning.py` baseline failures
(`test_circular_deps_flattened`, `test_decompose_returns_plan_or_none`) were independently confirmed
still present and unrelated (both fail on `MissionPlanAdvisor` mocking, nothing to do with
`_act_on_plan_step`'s reward-hash identity).

## Historical compatibility

No schema change. Old `plan_step:`-hashed `policy_memory` rows remain in the table (never deleted),
simply orphaned going forward exactly as they always effectively were (nothing ever read them by that
key) — no behavior regression relative to before this fix, only a forward-looking correction.

## Explicit non-claims

This does not claim the two hardcoded-binary reward writers (VectorCode, plan-step's own
success/failure signal) are now "real, computed" rewards — they remain honest binary proxies, exactly
as documented. This does not claim plan-step executions and spontaneous goal actions of the same
`(action_type, params)` *should* share one learned value in every possible sense — only that
`PolicyMemory`'s own stated identity model (`action_type` + `params` = reusable situation) already
implies they do, and this fix makes the code consistent with that stated model rather than silently
contradicting it.

## Final verdict

```
STARTING HEAD: 7f305271aa298be163bd1524a323b66eafe4dfe6
BUG FOUND: plan-step reward writer used a non-canonical "plan_step:"-hashed identity, unreadable by
           decision_engine's own scoring path for the same real situation -- a Task-89-deferred,
           now-resolved reader/writer mismatch
IMPLEMENTATION: 1 call-site fix (autonomous_loop.py, ad-hoc hash -> canonical make_situation_hash)
NEW TABLE: none / REWARD VALUES CHANGED: none (only which key the plan-step reward is filed under)
HARDCODED REWARD WRITERS HONESTLY CATALOGUED: VectorCode (0.8/0.3), plan-step (0.7/0.3) --
                                                unchanged, reported not hidden
NEW TESTS: 7/7 PASS
REGRESSION: 0 new failures (2 pre-existing test_planning.py baseline failures reconfirmed unrelated)
VERDICT: E2 COMPLETE
```

**FINAL HEAD:** `f6ae7d223229b7edf5577cc271daa2703df93be8`
