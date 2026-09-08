# Task 58B — FinAgent `launch_terminal` Permission Bypass Remediation

## 1. Task Objective

Remediate **Finding B** from `57_RESIDUAL_SIDE_EFFECT_SURFACE_VERIFICATION.md`: a real,
confirmed permission-gateway bypass in `districts/investment/finagent_agent.py`'s
`launch_terminal` capability. This is a narrowly-scoped security remediation — production
changes are permitted, but strictly limited to closing this one finding. Explicitly out of
scope: Finding A (already fixed in Task 58A), Finding C (mlops `hf_train`, still open, a
separate future task), `phone_controller.py`, event fan-out, the remaining subprocess/os.system
sweep, memory/cognition/planning/hypothesis/inference/autonomous-loop/governance architecture,
unrelated FinAgent functionality, and the 7-day experiment. Per the task's explicit stop
condition, this document covers Task 58B only — no work was done on 58C/59/60/Task 54
re-verification/benchmark/the experiment.

## 2. Original Finding B (from Task 57)

`FinAgentAgent.launch_terminal(auto_build)` called
`FinAgentTerminalLauncher.ensure_built(auto_build=...)` and `.launch()` directly, with **no
PermissionGateway step anywhere in the chain**. `ensure_built(auto_build=True)` can trigger a
real native `cmake` configure + build (`subprocess.run`, real local resource consumption, real
build-tooling execution); `.launch()` always launches the compiled binary via real
`subprocess.Popen()`. This capability was:

- declared in `self.capabilities` (reachable via `Governor.dispatch()`'s exact-match AND
  LLM-classified cross-district capability search),
- reachable via three aliases in `run()`'s dispatch table (`"launch_terminal"`, `"terminal"`,
  `"open_terminal"`),
- and had **no PermissionGateway tier classification at all** (not GREEN/YELLOW/RED/FORBIDDEN) —
  meaning even a direct `gateway.execute()` call for this action_type would have hit the
  UNKNOWN branch, but the real bug was that nothing in the actual call chain ever called the
  gateway to begin with.

`auto_build` flowed from caller-supplied `params` straight into `ensure_built()` completely
unfiltered.

## 3. Fresh Pre-Fix Call Chain (re-traced this task, not trusted from Task 57's description)

Re-read fresh this task, confirmed unchanged from Task 57's findings:

```
FinAgentAgent.capabilities = [..., "launch_terminal", ..., "terminal_status", ...]
Governor.dispatch(task_type="launch_terminal")
  -> district hint "investment" (governor.py:591, a routing hint only, not a gate)
  -> agents = registry.get_by_district("investment")
  -> capable = [a for a in agents if "launch_terminal" in a.capabilities]  (exact-match path)
  -> OR, if capable is empty and task["_llm_classified"]:
       city_capable = [a for a in registry.get_all_agents() if "launch_terminal" in a.capabilities]
       (whole-city LLM-classified fallback — same capability check, same agent.run() call)
  -> agent = max(capable_or_city_capable, key=health_points)
  -> await agent.run(task)
       -> action = task.get("type")  # "launch_terminal"
       -> elif action in ("launch_terminal", "terminal", "open_terminal"):
              return await self.launch_terminal(auto_build=p.get("auto_build", False))
              -> [PRE-FIX] await self._launcher.ensure_built(auto_build=auto_build)  # REAL cmake build
              -> [PRE-FIX] self._launcher.launch()                                   # REAL subprocess.Popen
```

`FinAgentTerminalLauncher` (`districts/investment/vector_finagent/terminal_launcher.py`) was
re-read fresh in full this task. Confirmed OS-level primitives it can reach — **exactly two**,
both in this one file:

- `subprocess.run(...)` — twice inside `build()`'s inner `_run_cmake()` (cmake configure, then
  cmake `--build`), only reachable via `ensure_built(auto_build=True)` when the binary is not
  already built.
- `subprocess.Popen(...)` — once inside `launch()`, the real terminal-binary launch.

No `os.system`, `os.startfile`, `shutil.which`, or `shell=True` anywhere in this file (unlike
Task 58A's `pc_controller.py`, which needed both `subprocess.Popen` and `os.startfile` mocked).
`is_built`/`cmake_source_present()` only call `Path.exists()` — inert, no OS-level side effect.

## 4. Permission Classification Before Fix

`"launch_terminal"` was absent from `core/config.py`'s `green`, `yellow`, and `red` lists
entirely — confirmed by direct read before any edit. This means a hypothetical direct
`gateway.execute(Action(action_type="launch_terminal", ...))` call would have hit the gateway's
`UNKNOWN` branch (blocked, logged critical). The real bug was architectural, not a
misclassification: **the gateway was never called at all** on the actual path
(`FinAgentAgent.run()` → `launch_terminal()` → real launcher), so the UNKNOWN-blocks-by-default
protection never had a chance to apply.

## 5. Authorization Design Considered (questions A–F)

**(A) How other RED agent capabilities are represented.** Surveyed the established precedent
(re-confirmed fresh this task by reading `git_bot.py`, `hedgebot_agent.py`): the agent itself
constructs an `Action(action_type=..., params=..., proposed_by=self.name)` and calls
`await self._gateway.execute(action)` — `push_github` (`git_bot.create_pr()`) and
`solana_swap_execute` (`hedgebot_agent.solana_execute()`) both do exactly this, checking only
`gate_result.approved` before proceeding.

**(B) How an agent translates a capability into an Action.** Same pattern: one `Action` per
gated operation, `action_type` matching (or closely representing) the capability name, real
params attached so the owner sees what's being approved.

**(C) Whether PermissionGateway already has a generic action mechanism.** Yes —
`PermissionGateway.execute(Action) -> GatewayResult` is fully generic. `_execute_action()`
additionally has hardcoded handlers for some RED action types (confirmed by reading it fresh:
`push_github`, `launch_app`, `send_email`, etc. all have real implementations there), but
`git_bot.create_pr()`'s pattern proves this is **not required** — an agent may gate purely for
the approval decision (`.approved`) and do its own real work afterward, ignoring
`_execute_action()`'s (possibly absent, possibly redundant) handler entirely. `push_github` in
fact has TWO independent real implementations (one in `_execute_action()`, a raw git push; one
in `git_bot.create_pr()`, a PyGithub PR) — both correctly gated independently. This confirmed
`launch_terminal` did not need a new `_execute_action()` branch.

**(D) Whether launch_terminal needs a dedicated action type.** Yes, but it already existed as a
concept — `"launch_terminal"` itself is the correct, semantically exact action_type (no need to
reuse `"launch_app"` or invent something else). It just needed classifying and gating.

**(E) Does approval for launch_terminal authorize auto_build=True?** Yes, by design — see
§9 for the full reasoning.

**(F) Can build and launch occur under one approved action without a mismatch?** Yes — proven
explicitly by TEST 4 (§13).

## 6. Chosen Remediation

1. **`core/config.py`**: added `"launch_terminal"` to `PermissionConfig.red`, with an inline
   comment explaining the rationale and explicitly noting it does **not** join
   `RED_INTERACTIVE_TOOLS` (unlike `launch_app`) because — confirmed by a repo-wide grep for
   `launch_terminal`/`open_terminal` (§12) — nothing routes an owner-typed/spoken command
   directly to this action_type; it is agent-internal only, so the standard owner-approval
   (Pushover/HUD/council) RED flow is correct.
2. **`districts/investment/finagent_agent.py`**:
   - `PermissionGateway`/`Action` imported.
   - `self._gateway = PermissionGateway()` added to `__init__`.
   - `launch_terminal()` rewritten to gate via
     `await self._gateway.execute(Action(action_type="launch_terminal", params={"auto_build":
     auto_build}, proposed_by=self.name))` **before** calling `self._launcher.ensure_built()`/
     `.launch()`. Fails closed (never proceeds) if the gateway call raises, or if
     `gate_result.approved` is not `True`.

No changes to `permission_gateway.py`, `governor.py`, `terminal_launcher.py`, or anything
outside these two files.

## 7. Why This Is the Smallest Safe Architectural Fix

- Reuses the exact `Action`/`gateway.execute()` mechanism already proven safe for
  `push_github`/`solana_swap_execute`/`content_publish` — no new permission framework, no new
  action-mechanism, no new tier.
- Gates at the single real chokepoint: every entry point (direct call, `run()`'s dispatch table
  including both aliases, Governor's exact-match dispatch, Governor's LLM-classified fallback)
  funnels through this one `launch_terminal()` method — there is exactly one implementation of
  the capability, so there is nowhere left for the real side effect to leak out unguarded.
- Does not touch `_execute_action()`, `Governor.dispatch()`, or `PermissionGateway` internals —
  no risk to any of the ~180 other Governor routes or ~15 other RED action types.
- Does not self-mint any token — `FinAgentAgent` has zero `grant_control()`/token-minting code;
  authorization comes exclusively from `PermissionGateway.execute()`'s real decision (confirmed
  by TEST 8, §13).

## 8. Exact Production Files/Functions Changed

| File | Change |
|---|---|
| `core/config.py` | Added `"launch_terminal"` to `PermissionConfig.red` (with rationale comment). No other line touched. |
| `districts/investment/finagent_agent.py` | Added `PermissionGateway`/`Action` import; added `self._gateway = PermissionGateway()` to `__init__`; rewrote `launch_terminal()` to gate before calling the launcher. `terminal_status()`, `run()`'s dispatch table, `self.capabilities`, and every other method: unchanged. |

Nothing else in the production tree was modified.

## 9. `auto_build` Authorization Semantics

**Does approval for `launch_terminal` authorize `auto_build=True`?** Yes — intentionally, and
scoped as follows: `auto_build` is included verbatim in the gated `Action`'s `params`
(`{"auto_build": auto_build}`), so it is visible to the owner (or CouncilBrain, in the
auto-proceed path) *before* the approval decision is made — the approver is never asked to
approve a vague "launch the terminal" request while a build silently happens underneath. One RED
approval covers both because they are the same logical operation from the owner's perspective
("run the financial terminal, building it first if necessary") and because splitting them into
two separate approvals would not add any real safety — a caller who can request `auto_build=True`
inside an already-approved `launch_terminal` action gains nothing by also being able to request
a standalone "build" action, since neither is reachable without going through this exact gate
first. This was proven, not assumed: TEST 4 (§13) explicitly confirms a single approved gate call
allows both the real (mocked) `cmake` build and the subsequent real (mocked) launch to occur; TEST
1/4b confirm an unapproved request — even with `auto_build=True` — triggers neither.

## 10. Governor / Capability Routing Behavior

Re-confirmed fresh this task (not merely trusted from prior session knowledge) by reading
`core/city/governor.py`'s dispatch body:

- **Exact-match path** (`task_type in agent.capabilities` among `registry.get_by_district(district)`):
  behaviorally TEST VERIFIED — TEST 5a/5b (§13) drive the real `Governor().dispatch()` with a
  registered real `FinAgentAgent` instance and confirm the gate applies identically to a direct
  call.
- **LLM-classified whole-city fallback** (`task.get("_llm_classified")`, only reached when the
  exact-match `capable` list is empty): uses the identical `task_type in agent.capabilities`
  check against the full registry, then calls `agent.run(task)` — the exact same code path as
  the exact-match branch, landing in the exact same `launch_terminal()` implementation. This is
  CODE-TRACE VERIFIED (the two branches share the same downstream `run()` call and the same
  single `launch_terminal()` method — there is no second, differently-gated implementation for
  this branch to reach) rather than separately behaviorally tested with a forced-empty-capable
  setup, since doing so would only re-exercise the identical `agent.run()` → `launch_terminal()`
  code already covered by TEST 5a/5b. No production path exists where the LLM-classified branch
  could reach a *different*, ungated implementation.

## 11. Alias Behavior

`run()`'s dispatch table maps `"launch_terminal"`, `"terminal"`, and `"open_terminal"` to the
same `self.launch_terminal(auto_build=...)` call — unchanged by this fix, and confirmed still
true by a fresh read. Because the gate lives inside `launch_terminal()` itself (not duplicated
per-alias in `run()`), all three aliases are automatically and identically gated. TEST 6a/6b/6c
(§13) behaviorally confirm both aliases individually. Note (re-confirmed via `self.capabilities`
read fresh): only `"launch_terminal"` (and `"terminal_status"`) are declared *capabilities* —
`"terminal"`/`"open_terminal"` are internal `run()`-only aliases, not separately reachable via
Governor's outer capability-match. This does not weaken anything; it only means the aliases are
reachable exclusively through an already-gated `run()` call, never as an independent
Governor route.

## 12. Alternate-Path Audit

Repo-wide search (after implementing the fix) for: `launch_terminal`, `open_terminal`,
`terminal` (as a task_type/action string), `FinAgentAgent`, `FinAgentTerminalLauncher`,
`ensure_built(`, `auto_build`, `.launch()`, `subprocess.Popen`, `subprocess.run`, `os.system`.

- `FinAgentTerminalLauncher`/`terminal_launcher` imports: **exactly two files import it** —
  `districts/investment/finagent_agent.py` (the gated path) and the module itself. No API
  router, CLI script, scheduled job, or other agent imports it directly.
- `launch_terminal`/`open_terminal` as literal strings: only appear in
  `core/city/governor.py` (the routing hint, not a gate — §3), `districts/investment/
  finagent_agent.py` (capabilities list + `run()`'s dispatch, now gated), and this session's
  tests/docs. No owner-command-classification code (intent matcher, `commands.py`,
  `websocket.py`) maps any phrase directly to this action_type outside of going through
  `FinAgentAgent`/`Governor.dispatch()` — meaning `RED_INTERACTIVE_TOOLS` (the owner-typed/
  spoken instant-bypass set) correctly does **not** need this action_type added (§6).
- No other production code calls `subprocess.Popen`/`subprocess.run`/`os.system` from within
  `districts/investment/vector_finagent/` outside `terminal_launcher.py` itself.

**No equivalent bypass discovered elsewhere.** This audit did not surface any finding requiring
a separate follow-up.

## 13. Behavioral Tests

New file: `tests/test_task58b_finagent_terminal_permission_remediation.py` — 16 tests, all
exercising the REAL `PermissionGateway.execute()`, `Governor.dispatch()`, and
`FinAgentAgent.run()`/`.launch_terminal()`, with only the terminal launcher's two OS-level
primitives (`subprocess.run`, `subprocess.Popen`, mocked directly on the `terminal_launcher`
module) and the external CouncilBrain LLM call / Pushover human-notification boundary
(`PermissionGateway._notify`/`_wait_for_confirmation`, mocked per the established codebase
pattern already used by `tests/unit/test_permission_gateway.py` and
`tests/integration/test_phase_a7_council_red_tier.py`) replaced. `permission_gateway.py`'s own
gating logic (`execute()`, `_classify()`, `_handle_red_tier()`'s verdict processing) runs for
real throughout, per `.claude/rules/testing.md`'s "No Mocking: permission_gateway.py."

| # | Test(s) | What it proves |
|---|---|---|
| 1 | `test_1_unapproved_launch_terminal_does_not_execute`, `test_4b_...auto_build_true_never_triggers_build` | Unapproved (council REJECT) `launch_terminal()` — even with `auto_build=True` — never calls the real (mocked) build or launch primitives; `PermissionGateway.execute` is spied and confirmed actually invoked with `action_type="launch_terminal"` (not just inferred from a boolean). |
| 2 | `test_2_approved_launch_terminal_works_launcher_reached_only_after_authorization` | Approved (council DEFER → simulated owner confirm) `launch_terminal()` succeeds; call-order spy proves `gateway.execute` happens strictly before `launcher.launch()`. |
| 3 | `test_3_auto_build_false_reaches_launch_without_triggering_build` | Authorized `auto_build=False` reaches launch without ever calling the real (mocked) `cmake` build. |
| 4 | `test_4_approved_auto_build_true_triggers_build_then_launch` | Authorized `auto_build=True` with a missing binary triggers the real (mocked) `cmake --preset` + `cmake --build` calls, then still launches — the single RED approval explicitly covers both. |
| 5 | `test_5a_governor_dispatch_unapproved_launch_terminal_blocked`, `test_5b_..._approved_..._reaches_launcher` | The REAL `Governor().dispatch({"type": "launch_terminal", ...})`, with a real `FinAgentAgent` registered in the real agent registry, cannot bypass the boundary — unapproved blocks, approved reaches the (mocked) launcher. |
| 6 | `test_6a_alias_terminal_unapproved_blocked`, `test_6b_alias_open_terminal_unapproved_blocked`, `test_6c_alias_terminal_approved_reaches_launcher` | Both `"terminal"` and `"open_terminal"` aliases, driven through the real `run()` dispatch table, are gated identically. |
| 7 | `test_7_terminal_status_still_works_read_only_no_gateway_involved`, `test_7b_capabilities_unaffected_by_the_fix`, `test_7c_run_dispatch_table_unaffected_for_unrelated_action` | No regression: `terminal_status()` still works and correctly does NOT touch the gateway (it has no dangerous primitive); `capabilities` list unaffected; an unrelated `run()` action still works. |
| 8 | `test_8_launch_terminal_source_has_no_self_mint_and_gates_before_side_effect`, `test_8b_launch_terminal_is_red_tier`, `test_8c_gateway_unreachable_fails_closed` | Source inspection confirms no `grant_control` self-mint exists and the gateway call/approval-check precede `ensure_built()`/`launch()` in source order; `launch_terminal` is classified RED in the real `CONFIG`; a raised gateway exception fails closed (`status: "blocked"`), never open. |

Existing diagnostic file `tests/test_task57_capability_bypass_diagnostic.py` was updated in
place (matching the Task 58A precedent for Finding A): `test_launch_terminal_action_type_is_not_
classified_in_any_permission_tier` → `test_launch_terminal_action_type_is_now_classified_red`
(assertion inverted, now checks RED membership); `test_run_launch_terminal_reaches_real_launcher_
with_no_gateway_step` → `test_run_launch_terminal_no_longer_reaches_real_launcher_without_
approval` (rewritten to drive an unapproved gateway path and confirm the real launcher is never
reached, mocking `subprocess.run`/`subprocess.Popen` directly rather than the launcher's named
methods). Finding C's tests (mlops `hf_train`) in the same file are untouched — still correctly
documenting that finding as open.

## 14. Test Isolation / Side-Effect Verification

Per the explicit lesson from the Task 58A incident (a method-level mock silently stopped
intercepting anything after `play_music()`'s internal call target changed, letting a real
Spotify launch slip through mid-regression): before writing any test, `terminal_launcher.py` was
re-read in full and every OS-level primitive it can reach was inventoried (§3) — exactly
`subprocess.run` and `subprocess.Popen`, mocked directly on the module (`tl_mod.subprocess.run`
/ `tl_mod.subprocess.Popen`), never via a named wrapper method.

All 10 dangerous-path tests (TEST 1, 2, 3, 4, 4b, 5a, 5b, 6a, 6b, 6c across both the new file and
the updated diagnostic file's rewritten test) were run **individually in isolation** via
`pytest path::test_name`, each followed immediately by
`tasklist /FI "IMAGENAME eq FinceptTerminal.exe"`. Every isolated run: exit code 0, zero real
`FinceptTerminal.exe` processes found (`INFO: No tasks are running which match the specified
criteria.`). No `cmake.exe` processes were spawned either. Zero real side effects occurred at any
point during this task's testing.

## 15. Full Regression Results

Baseline (established across Tasks 52–58A, `tests/unit` + `tests/integration` excluding
`test_planning.py`'s 2 independently pre-existing broken `MissionPlanAdvisor`-patch tests, per
established precedent): **2212 collected / 2175 passed / 8 failed / 0 errors / 29 skipped.**

This task's run of the identical scope (`tests/unit tests/integration --ignore=tests/unit/
test_planning.py`): **8 failed / 0 errors / 29 skipped** — same 8 failing test names, exact
match:

```
tests/unit/test_agent_registry_successor_class.py::test_dying_coding_swarm_respawns_as_coding_swarm_with_capabilities
tests/unit/test_correction_learner.py::TestLessonExtractor::test_extract_from_explicit_correction
tests/unit/test_correction_learner.py::TestLessonExtractor::test_tags_include_domain_and_source
tests/unit/test_epistemic_scoring.py::TestScoringWithEpistemic::test_stale_domain_reduces_score
tests/integration/test_correction_integration.py::TestCorrectionLearningIntegration::test_full_loop_stores_and_retrieves
tests/integration/test_correction_integration.py::TestCorrectionLifecycle::test_lifecycle_unvalidated_to_validated
tests/integration/test_epistemic_integration.py::TestEpistemicCognitiveLoop::test_different_domains_independent
tests/integration/test_phase_a7_council_red_tier.py::TestHandleRedTierVerdictPaths::test_proceed_high_confidence_returns_proceed
```

Collected count (679 `tests/unit` + 1534 `tests/integration`, summed per-file since this
environment's pytest run did not print a final aggregate summary line for this large a run —
see caveat below) = 2213, within 1 of the documented 2212 baseline; skipped count (29) is an
exact match. **Zero new failures. Identical to baseline.**

Beyond the tracked baseline scope, the rest of `tests/` was also run this task (not previously
exercised as a single sweep in any prior task this session):

- `tests/districts/` (includes `tests/districts/investment/`): **0 failures.**
- Root-level `tests/*.py` (130 files): **5 failures** — 3 already accounted for above
  (`test_permission_gateway.py::test_red_action_times_out_without_confirmation`,
  `test_regression_governor_capability_routing.py::test_languages_routes_correctly_despite_
  wrong_llm_guess` and `::test_news_trends_routes_correctly_despite_wrong_llm_guess`, all
  explicitly documented as pre-existing/unrelated in Task 54's doc) + 2 newly investigated
  this task (below).
- `tests/backend`, `tests/core`, `tests/emergency`, `tests/event_bus`, `tests/frontend`,
  `tests/hands`, `tests/loop`, `tests/persona`, `tests/personality`, `tests/research_engine`,
  `tests/resilience`, `tests/training`, `tests/voice`: **1 failure**
  (`tests/backend/test_webauthn_middleware_integration.py::test_wrong_token_type_rejected_
  type_confusion`).

All 3 newly-surfaced-this-task failures were individually isolated and root-caused:

| Test | Root cause | Related to Finding B? |
|---|---|---|
| `test_permission_gateway.py::test_red_action_times_out_without_confirmation` | Confirmed fails in complete isolation, unrelated to any file I touched. The test's local `fast_timeout` helper doesn't accept the `pending_id` kwarg that the real `PermissionGateway._wait_for_confirmation()` signature requires (`TypeError`) — a pre-existing test/production signature drift in `permission_gateway.py`, a file this task never edited. | No |
| `test_openwa_absorption.py::TestBulkSender::test_exception_in_send_counted_as_failure` | **Passes when run in isolation** (`1 passed`). Only fails inside the large combined root-chunk batch — an order-dependent test-isolation flake in an unrelated file (WhatsApp bulk sender), not a real regression. | No |
| `test_frontend_bundle.py::test_bundle_matches_current_source_files` | A frontend JS bundle SHA-256 hash check; fails because the built bundle is stale relative to a `js/*.js` source file (`run: python tools/build_frontend.py`). Purely a frontend build-artifact staleness check — this task touched zero frontend/JS files. | No |
| `tests/backend/test_webauthn_middleware_integration.py::test_wrong_token_type_rejected_type_confusion` | Confirmed fails in isolation (`assert 200 == 401`) — a WebAuthn middleware auth test, unrelated to permission_gateway/FinAgent/core.config's red list. | No |

**Targeted tests** (`tests/test_task58b_finagent_terminal_permission_remediation.py`, 16 tests):
16/16 pass. **Relevant tests** (`tests/test_task57_capability_bypass_diagnostic.py` 6/6,
`tests/test_task57_device_control_bypass_diagnostic.py` + `tests/test_task58a_play_music_
escalation_remediation.py` unaffected/still passing, `tests/test_investment_district_run_
wiring.py`, `tests/test_investment_router_agent_paths.py`, `tests/districts/investment/`,
`tests/test_governor.py`, `tests/test_governor_taint_block.py`, `tests/test_regression_
governor_capability_routing.py`, `tests/unit/test_permission_gateway.py` +
`tests/unit/test_permission_gateway_extra.py`, `tests/integration/test_phase_a7_council_red_
tier.py`, `tests/test_llm_council.py`, `tests/test_trust_ladder.py`): all pass except the 3
pre-existing/unrelated failures already documented in the table above and §15's baseline
comparison (`test_regression_governor_capability_routing.py`'s 2, `test_phase_a7_council_red_
tier.py`'s 1).

**Static/lint/type checks**: `ruff` and `mypy` are **not available** in this environment
(`ruff --version` / `mypy --version` both `command not found`) — same as every prior task this
session. `py_compile` syntax check and a live `import` of both modified modules
(`core.config`, `districts.investment.finagent_agent`) both succeed cleanly.

**Caveat on the collected-count comparison**: this environment's pytest did not print a final
aggregate `"N passed, M failed, K skipped in Ts"` summary line for runs of this size (confirmed
across multiple retries — the process completes and the short-summary FAILED list prints, but
the trailing totals line is absent from captured output). The collected/skipped/failed counts
above were independently reconstructed from per-file `--collect-only` sums and `grep` counts of
`FAILED`/`"was skipped"` lines rather than read directly off a single summary line. Given the
failed-test-name list and skip count both match the baseline exactly, and the 1-count difference
in "collected" is far smaller than anything my two-file, list-addition-plus-one-method diff could
plausibly cause, this is reported as a measurement-methodology caveat, not a real discrepancy.

## 16. Residual Limitations

- The Governor LLM-classified cross-district fallback path is code-trace-verified, not
  separately behaviorally exercised with a forced-empty-`capable`-list setup (§10) — this is a
  structural argument (identical downstream `run()` call, no second implementation to diverge
  to), not an independent test run.
- `RED_INTERACTIVE_TOOLS` intentionally does not include `launch_terminal` (§6) — if a future
  change adds an owner-typed/spoken command that maps directly to this action_type, that change
  would need to explicitly decide whether the interactive bypass is appropriate here; this task
  does not pre-empt that decision.
- Three test failures outside this task's scope were newly surfaced this task purely because
  this was the first time this session ran those specific directories/files as part of a single
  sweep — none are new regressions, none require action under this task, but they remain
  unfixed (frontend bundle staleness, a WebAuthn test, a pending_id test bug, and one flaky
  order-dependent test). None are recommended as urgent follow-ups; they are noted for
  completeness per this task's honesty requirement, not escalated.
- Finding C (`districts/coding/mlops_agent.py`'s `hf_train`) remains open and unfixed — a
  separate, not-yet-scheduled Task 58C.
- The other Task 57 residuals (`phone_controller.py`'s shared token-scope tuple; the remaining
  ~40 unread subprocess files) remain open and out of scope for both 58A and 58B.

## 17. Final Status

All 18 acceptance criteria satisfied:

- [x] Finding B's actual bypass closed
- [x] `launch_terminal` cannot trigger the terminal binary without intended authorization (TEST 1, 3, 5a, 6a, 6b)
- [x] Native build execution cannot be triggered without intended authorization (TEST 1, 4b)
- [x] `auto_build=True` explicitly and safely handled — one RED approval intentionally covers both build and launch, proven not assumed (TEST 4, §9)
- [x] `launch_terminal` has appropriate permission classification (RED, §4/§6)
- [x] Actual dangerous side effects occur only downstream of the intended permission boundary (TEST 2 call-order, TEST 8 source-order)
- [x] Governor capability routing cannot bypass that boundary (TEST 5a/5b)
- [x] LLM/cross-district capability routing cannot bypass that boundary (code-trace verified, §10/§16)
- [x] Supported aliases cannot bypass that boundary (TEST 6a/6b/6c)
- [x] No self-minted RED authorization bypass exists inside `FinAgentAgent` (TEST 8)
- [x] Relevant existing FinAgent behavior still works (TEST 7)
- [x] Behavioral regression tests prove the security invariant (16/16 new + 6/6 updated diagnostic)
- [x] Dangerous OS primitives fully mocked in tests (`subprocess.run`/`subprocess.Popen`, the complete inventory for this file)
- [x] Newly-created dangerous-path tests individually isolated at least once (10/10, zero real processes)
- [x] No unintended real side effects occurred during final verification
- [x] Full regression compared against the known baseline (identical: 8 failed / 0 errors / 29 skipped)
- [x] No unrelated architecture modified (2 production files, additive/localized changes only)
- [x] Documentation complete (this document)

**58B — FIXED + BEHAVIORALLY VERIFIED**

Per the task's explicit stop condition: stopping here. Not proceeding to 58C, 59, 60, Task 54
re-verification, benchmark, or the 7-day experiment.
