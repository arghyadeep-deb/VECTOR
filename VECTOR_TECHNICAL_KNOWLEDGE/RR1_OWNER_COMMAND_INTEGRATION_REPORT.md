# RR-1 OWNER COMMAND INTEGRATION REPORT

## 1. Starting State

- HEAD: `60acc693697da6f2397c45382e231c8ccfd3fca2` (authoritative starting point, confirmed via `git rev-parse HEAD`).
- Working tree: clean apart from the same pre-existing untracked files present since RG-0 (stray worktree tooling, unrelated docs, prior RG/RR-0 report `.md`s).
- VECTOR confirmed stopped before any mutation.

## 2. Pre-change Path Comparison

| | Stage-0 (`_detect_intent_action` keyword match) | classify_chat_intent action path (pre-RR-1) |
|---|---|---|
| Input validation | top-level `scan_text(body.text)` (shared, both paths) | same (shared, runs before branching) |
| Prompt-injection scanning | shared, as above | shared, as above |
| Taint checks | none | `governor.dispatch()`'s own TaintTracker SHELL_EXEC/NET_FETCH sink check (shell/fetch-substring task_types only) |
| Council review | none | `governor.dispatch()`'s advisory-only RED-tier council check (never blocks, only logs+annotates) |
| PermissionGateway | **real GREEN/YELLOW/RED/FORBIDDEN tiering via `perm_gateway.execute()`** | **none — bypassed entirely** |
| Agent resolution | via `_execute_action`'s dispatch table (GREEN/YELLOW/RED-gated) | `governor.dispatch()`'s capability-based agent resolution across all districts |
| District routing | not applicable (no district concept) | real, with honest `no_capable_agent` refusal |
| Result handling | `_build_response_text()` | `AvatarVoice()._extract_text()` |
| Reasoning-chain logging | Step 7, real `gateway_result.level`/`approved` | hardcoded reward 0.8/0.4 by request status |
| Episodic logging | Step 8 | separate, near-duplicate call |
| PolicyMemory | **written** (Step 6) | **never written** |
| CausalGraph | not directly written by either path (both eventually route through `governor.dispatch()`'s own downstream effects where applicable) | same |
| Error handling | outer `try/except` (shared) | same |

**Key asymmetry found**: the old classify_chat_intent path had taint-tracking and advisory council review that Stage-0 lacked; Stage-0 had real PermissionGateway authorization that the classify_chat_intent path lacked entirely. Neither path was a strict superset of the other.

## 3. Root Cause

`core/api/routers/commands.py:154-220` (pre-RR-1): the classify_chat_intent action branch built a bespoke `gov_task` dict and called `GovernorCouncil().dispatch()` directly — a second, parallel action-execution path never reaching `Candidate`, `DecisionEngine.evaluate()`, or `PermissionGateway.execute()`, sitting ~90 lines above the "real" Candidate-based pipeline in the same file (see `RR0_ROOT_CAUSE_ARCHITECTURE_REPORT.md` P1-1).

## 4. Implementation

**File changed**: `core/api/routers/commands.py` only. **No new helper function created** — per the mission's own preference, the classifier's output is reassigned onto the existing `intent_action` variable and allowed to fall through (no `return`) into the unmodified Step 3-8 block, which Stage-0 already used identically. Zero duplication.

**Before**: `classify_chat_intent()` → build `gov_task` → `GovernorCouncil().dispatch(gov_task)` → `AvatarVoice()._extract_text()` → bespoke reasoning-chain/episodic writes → `return`.

**After**: `classify_chat_intent()` → reassign `intent_action = {"action_type": ..., "params": {...}}` → **fall through** → Step 3 builds one `Candidate` from `intent_action` → Step 4 `decision_engine.evaluate([candidate])` → Step 5 `perm_gateway.execute(Action(...))` → Step 6 `update_policy(...)` → Step 7/8 reasoning-chain + episodic writes (unchanged, shared with Stage-0) → `return`.

A new `district_hint` variable threads the classifier's district guess into the final `CommandResponse.district` field, preserving the pre-RR-1 observable behavior for that field.

**Important, deliberately-documented design finding**: `core/config.py`'s GREEN/YELLOW/RED lists were built around `AutonomousLoop`'s own candidate vocabulary, not the full space of established district task_types `classify_chat_intent` names (confirmed empirically: none of `system_status`, `review_content`, `track_campaign_performance`, `study_session`, `goal_summary`, and every other regex-preclassified task_type are in any tier list). Post-RR-1, such actions now classify `UNKNOWN` and are **blocked** by PermissionGateway's existing, untouched, intentional fail-closed rule ("UNKNOWN — default to RED, never silently allow") rather than silently executing via the removed bypass. This is the correct, safe consequence of making PermissionGateway authoritative — not a bug, not something RR-1 attempted to route around, and not a permission-tier weakening. Expanding `config.py`'s tier coverage for these real capabilities is a natural, explicitly out-of-scope follow-up (a config change, not this integration fix).

## 5. Safety Preservation

- **TaintTracker**: for any task_type not yet in `config.py`'s tier lists (the overwhelming majority of `classify_chat_intent`'s real output), the new path's UNKNOWN→blocked outcome is **strictly stronger** than the old taint-substring-match-only check, which only inspected shell/fetch-flavored task_types and let everything else through freely.
- **Council review**: for task_types that ARE tiered RED (e.g. `run_shell_command`), the new path routes through PermissionGateway's real, blocking RED-tier flow (CouncilBrain deliberation + Pushover owner approval, fail-closed on timeout) — strictly stronger than the old advisory-only council check that never blocked.
- **PermissionGateway**: now authoritative for every executable owner action reached via this route — GREEN auto-executes, YELLOW/RED follow existing authorization semantics, FORBIDDEN and UNKNOWN both deny. Verified directly against the real, unmodified gateway (never mocked, per `.claude/rules/testing.md`).
- No permission tier, threshold, timeout, or fallback semantic was modified anywhere. `core/config.py`, `permission_gateway.py`, `decision_engine.py`, `governor.py`, `autonomous_loop.py` are byte-identical to HEAD.

## 6. Tests

All 6 required scenarios implemented in `tests/test_rr1_command_integration.py` (9 test functions), using the **real, unmocked** `DecisionEngine` and `PermissionGateway` throughout (only `classify_chat_intent` mocked, plus `ContextEngine.session_hydration_prompt` stubbed for speed — neither is on the "never mock" list):

| # | Test | Result | Proves |
|---|---|---|---|
| 1 | Classified action integration | PASS | `DecisionEngine.evaluate()` called with exactly 1 real Candidate; `resp.action_taken`/`district` populated; old `GovernorCouncil.dispatch()` path proven unreachable (patched to raise if called) |
| 2 | answer_question control | PASS | `DecisionEngine.evaluate` and `PermissionGateway.execute` both proven not-called for pure Q&A; text-only response preserved |
| 3 | Timeout/fallback control | PASS | Talk-not-act preserved; no Candidate execution, no gateway call, for the exact fallback shape `classify_chat_intent`'s real timeout/error/low-confidence paths all normalize to |
| 4 | Decision authority | PASS | `PermissionGateway.execute()` proven (by object identity, not just value equality) to receive the `params` object from `DecisionEngine`'s own winning Candidate |
| 5 | Safety (RED action) | PASS | `financial_transaction` (real RED config entry) confirmed not auto-executed with no owner confirmation, against the real, unmocked gateway |
| 6 | Taint/council regression | PASS | Real gateway confirms an unrecognized LLM-classified task_type is UNKNOWN (fail-closed, stronger than old taint-substring check); `run_shell_command` confirmed still RED-gated |

## 7. Regression

Ran the full RR-1-relevant suite: `test_command_intent_routing.py`, `test_command_websocket_parity.py`, `test_decision_engine.py` (both locations), `test_permission_gateway.py` (all 3 files), `test_policy_reward_identity.py`, `test_task89c_goal_progress.py`, `test_counterfactual_block_penalizes_policy.py` — **197 tests total, 195 passed**.

**2 unrelated environmental failures**, both confirmed pre-existing by re-running against the unmodified baseline HEAD with RR-1's changes stashed (identical failures reproduced):
- `test_decision_engine.py::TestScoringFactors::test_each_factor_contributes_to_reasoning_chain` — a stale hardcoded `len(reasoning_chain)==6` assertion, now 8 entries (R22/R23/R24 factor growth from prior waves) — `decision_engine.py` was never touched by RR-1.
- `test_permission_gateway.py::test_red_action_times_out_without_confirmation` — a local test-fixture mock (`fast_timeout`) missing the `pending_id` kwarg the real call site now passes — `permission_gateway.py` was never touched by RR-1.

Not fixed, per the mission's own instruction to report unrelated failures separately rather than fix them.

## 8. Production-path Validation

**Instruction delivered**: `"Is everything running smoothly right now?"` (harmless, read-only, no external communication, no source/config/doc mutation; deliberately chosen to route via `classify_chat_intent`'s deterministic regex pre-classifier for a fast, reproducible, non-LLM-dependent real trace — confirmed to avoid every Stage-0 keyword).

**Real end-to-end log trace** (VECTOR launched via the unmodified production command, `python run_vector.py api --host 127.0.0.1 --port 8000`):
```
classify_chat_intent DEBUG: REGEX_PRECLASSIFY matched ... -> district=ops, task_type=system_status
decision_engine:evaluate — Winner: system_status (score=0.5419) over 0 alternatives. goal_alignment=0.30 policy=0.50 confidence=0.85
permission_gateway:execute — system_status classified as UNKNOWN (proposed by api_command)
permission_gateway:execute — CRITICAL: UNKNOWN action type: 'system_status' — blocked.
```
**Response**: `{"response":"I couldn't determine the action type for: ...","action_taken":null,"candidates_evaluated":1,"winner_score":0.5419,"district":"ops"}` — HTTP 200, 2096ms.

**PolicyMemory**: real write confirmed, `system_status` / `avg_reward=0.2` / `sample_count=1` (the existing, unmodified denied-action reward — no special RR-1 write added).

This is the honest, complete, real result — `candidates_evaluated=1` (vs. the pre-RR-1 `0`), a real DecisionEngine score, and a real PermissionGateway authorization decision (UNKNOWN→blocked), exactly matching the documented, deliberate consequence described in Section 4. No steering after delivery; VECTOR stopped immediately after.

## 9. Diff Audit

```
core/api/routers/commands.py | 175 ++++++++++++++++++------------------
tests/test_rr1_command_integration.py | new file (411 insertions)
```
Exactly the two files intended: one production file (within the mission's expected scope), one new test file. No other production file was touched — `DecisionEngine`, `AutonomousLoop`, `Governor`, `PermissionGateway`, `PolicyMemory`, `CausalGraph`, `GoalSystem`, `EpistemicTracker`, `CounterfactualMemory`, R6, reward formulas, goal progress, and candidate scoring are all byte-identical to HEAD (confirmed — no file outside `commands.py` appears in the diff).

## 10. Final HEAD

`dfa767140c8d399eedc90fcf10090a2c3d572222`

## 11. Remaining Gaps

RR-1 does **not** claim to have fixed RG-D's reward/goal-progress decoupling (RR-2) or the failure→epistemic/counterfactual gap (RR-3) — both remain exactly as characterized in `RR0_ROOT_CAUSE_ARCHITECTURE_REPORT.md`, untouched by this change. The newly-surfaced, real-world consequence that most `classify_chat_intent`-classified district task_types are currently `UNKNOWN`-tiered (and therefore blocked) is a genuine, honestly-reported side effect of making PermissionGateway authoritative — closing that gap (expanding `config.py`'s tier coverage) is explicitly out of RR-1's scope and not attempted here.

## 12. Verdict

# RR-1 PASS — OWNER ACTION PATH UNIFIED

**Hard Stop.** VECTOR is stopped. RR-2 and RR-3 not implemented. RG-C not rerun. Awaiting independent review.
