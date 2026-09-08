# Task 58C — MLOps `hf_train` Permission Bypass Remediation

## 1. Task Objective

Remediate **Finding C** from `57_RESIDUAL_SIDE_EFFECT_SURFACE_VERIFICATION.md`: a real, confirmed
permission-gateway bypass in `districts/coding/mlops_agent.py`'s `hf_train` capability. This is a
narrowly-scoped security remediation — production changes are permitted, but strictly limited to
closing this one finding. Explicitly out of scope: Finding A (fixed, Task 58A), Finding B (fixed,
Task 58B), `phone_controller.py`, event fan-out, the remaining subprocess/os.system sweep,
memory/cognition/planning/hypothesis/inference/autonomous-loop/Governor-or-PermissionGateway
architecture globally, unrelated MLOps capabilities (`ml_research`, `hf_dataset`, `hf_hub`,
`github_ml`, `ml_plan`), and the 7-day experiment. Per the task's explicit stop condition, this
document covers Task 58C only.

## 2. Original Finding C (from Task 57)

`MLOpsAgent.hf_train(script, repo_id, hardware, timeout, requirements)` forwarded a
caller-supplied Python `script` string, unvalidated, into `args = {"script": script, ...}`,
submitted to `hf_jobs_handler(args)` — a real remote job submission to HuggingFace Jobs, using
the owner's HF credentials, executing on HF's cloud infrastructure at real (potentially
GPU-tier) cost. `"hf_train"` was declared in `self.capabilities` (reachable via
`Governor.dispatch()`'s exact-match and LLM-classified cross-district capability search) and had
**no PermissionGateway tier classification at all**. Zero `PermissionGateway` reference existed
anywhere in `hf_train()`'s source.

## 3. Fresh Pre-Fix Production Call Chain (re-traced this task, not trusted from Task 57's description)

Re-read `districts/coding/mlops_agent.py` in full and
`districts/coding/vector_mlops/agent/tools/jobs_tool.py` in full this task — confirmed and
extended Task 57's original trace:

```
MLOpsAgent.capabilities = ["ml_research", "hf_train", "hf_dataset", "hf_hub", "github_ml", "ml_plan"]
Governor.dispatch(task_type="hf_train")
  -> district hint "coding" (governor.py:645, a routing hint only, not a gate)
  -> agents = registry.get_by_district("coding")
  -> capable = [a for a in agents if "hf_train" in a.capabilities]  (exact-match path)
  -> OR, if capable is empty and task["_llm_classified"]:
       city_capable = [a for a in registry.get_all_agents() if "hf_train" in a.capabilities]
       (whole-city LLM-classified fallback — same capability check, same agent.run() call)
  -> agent = max(capable_or_city_capable, key=health_points)
  -> await agent.run(task)
       -> p = task.get("params", task); action = p.get("action")
       -> elif action == "hf_train":
              return await self.hf_train(script=p.get("script",""), repo_id=p.get("repo_id",""),
                                          hardware=p.get("hardware","cpu-basic"),
                                          timeout=p.get("timeout",3600),
                                          requirements=p.get("requirements"))
              -> [PRE-FIX] with _vector_mlops_agent_namespace():
                     from agent.tools.jobs_tool import hf_jobs_handler
                     args = {"runtime":"python","script":script,"repo_id":repo_id,
                             "hardware":hardware,"timeout":timeout,"requirements":requirements or []}
                     result, success = asyncio.run(hf_jobs_handler(args))   # REAL remote submission
```

**Newly-discovered routing nuance this task** (not present in Task 57's description, not a
security issue, documented for accuracy): `MLOpsAgent.run()` reads `p.get("action")` only — unlike
`FinAgentAgent.run()` (Task 58B), it has **no `task.get("type")` fallback**. `Governor.dispatch()`
derives its capability-match `task_type` purely from `task.get("type", "")` and never injects that
into `task["params"]["action"]`. This means a real Governor-routed caller must supply an
`"action"` key (either at `task["action"]` directly, when no `"params"` wrapper is used — since
`p = task.get("params", task)` falls back to the bare task — or nested at
`task["params"]["action"]`) matching `"hf_train"`, in addition to `task["type"] = "hf_train"` for
Governor's own capability match. This is a pre-existing routing-shape quirk of `MLOpsAgent.run()`,
not something this security fix needed to touch — it does not weaken the finding (the bypass was
real either way, once a caller shapes the task correctly) and does not need remediation to close
Finding C.

**Newly-discovered functional bug this task** (documented for honesty, explicitly NOT fixed — see
§19): `hf_train()`'s `_run()` closure builds `args` for `hf_jobs_handler()` without ever setting
the required `"operation"` key, and never passes a `session` (so `hf_token` inside the handler is
always `None`). Reading `HfJobsTool.execute()` fresh (`districts/coding/vector_mlops/agent/tools/
jobs_tool.py:340-353`): `operation = params.get("operation"); if not operation: return {...
"isError": True}` — meaning the **pre-existing, unmodified** call to the real HF Jobs library would
itself error out immediately today, before ever reaching `_run_job()`'s real `self.api.run_job(...)`
call. This is an unrelated functional correctness bug in the vendored-integration wiring, not a
security issue — if anything it currently makes exploitation harder than Task 57 assumed. It is
explicitly out of scope for a security remediation (fixing it is not required to close Finding
C — the vulnerability was "hf_train() has no gate before calling the submission boundary", not
"the submission boundary's own internal call always succeeds"). Not fixed here; noted as a
residual, separate, non-security finding in §19.

`jobs_tool.py` contains **no local OS-level primitive at all** — no `subprocess.*`, `os.system`,
or `os.popen` anywhere. It builds shell command strings (`_build_uv_command`,
`_wrap_inline_script`) but only ever passes them as **data** to `self.api.run_job(command=...)` —
the caller-supplied script executes remotely on HF's infrastructure, never locally. This differs
from Task 58B's local `subprocess.Popen`/`cmake` primitives; the consequential external boundary
here is purely network (real HTTP calls the `huggingface_hub` library makes to HF's API), not a
local process.

## 4. Permission Classification Before Fix

`"hf_train"` was absent from `core/config.py`'s `green`, `yellow`, and `red` lists entirely —
confirmed by direct read before any edit. A hypothetical direct
`gateway.execute(Action(action_type="hf_train", ...))` call would have hit the gateway's UNKNOWN
branch (blocked, logged critical). The real bug was architectural: **the gateway was never called
at all** on the actual path (`MLOpsAgent.run()` → `hf_train()` → real submission helper), so the
UNKNOWN-blocks-by-default protection never had a chance to apply.

## 5. Authorization Design Considered

**(A) Is `"hf_train"` the correct semantic action_type?** Yes — verified independently, not
assumed from Task 57's recommendation. It is the exact, unambiguous name of the consequential
capability being exercised; no existing action_type represents it more precisely.

**(B) Should it be RED?** Yes, verified independently (§6). Confirmed RED is correct by comparing
against `financial_transaction`'s classification rationale (real external cost + real remote
execution under the owner's credentials) and `execute_code`'s (arbitrary caller-supplied code
execution) — `hf_train` combines both risk classes and adds real external billing, so it is at
least as consequential as either. No other existing tier fits: GREEN/YELLOW auto-execute or
soft-gate, inappropriate for real remote code execution + real external cost.

**(C) Does the gateway already support generic RED approval for this?** Yes — the same generic
`Action`/`PermissionGateway.execute()` mechanism used for `push_github`/`solana_swap_execute`/
`launch_terminal` (Task 58B). Re-confirmed fresh this task by reading `git_bot.create_pr()` and
`hedgebot_agent.solana_execute()`: the agent itself constructs an `Action(action_type=...,
params=..., proposed_by=self.name)`, calls `await self._gateway.execute(action)`, and checks only
`.approved` before proceeding with its own real work — `_execute_action()` handlers are not
required (`push_github` has an independent, redundant handler there; `solana_swap_execute` does
not).

**(D) Does a gateway-side execution handler exist or is it necessary?** Not necessary — matching
Task 58B's precedent exactly, `MLOpsAgent.hf_train()` gates for the approval decision and performs
its own real submission afterward. `core/loop/permission_gateway.py` was **not modified**.

**(E) Should the agent perform the HF submission after approval, per other RED agent patterns?**
Yes — this is exactly what was implemented.

**(F) What parameters must the Action expose?** All consequential, caller-controlled parameters:
`script`, `repo_id`, `hardware`, `timeout`, `requirements` — plus a human-readable `summary` string
surfacing the concrete values (hardware, timeout, repo_id, script length, requirements) so an
approver is never asked to approve an unqualified "run training" (§9).

## 6. Chosen Remediation

1. **`core/config.py`**: added `"hf_train"` to `PermissionConfig.red`, with an inline comment
   explaining the rationale (comparable to `financial_transaction`) and explicitly noting it does
   **not** join `RED_INTERACTIVE_TOOLS` — confirmed by a repo-wide alternate-path audit (§15) that
   nothing routes an owner-typed/spoken command directly to this action_type.
2. **`districts/coding/mlops_agent.py`**:
   - `PermissionGateway`/`Action` imported.
   - `self._gateway = PermissionGateway()` added to `__init__`.
   - `hf_train()` rewritten to gate via `await self._gateway.execute(Action(action_type=
     "hf_train", params={"script", "repo_id", "hardware", "timeout", "requirements", "summary"},
     proposed_by=self.name))` **before** entering the `_run()` closure that calls the real
     `hf_jobs_handler`. Fails closed (never proceeds) if the gateway call raises, or if
     `gate_result.approved` is not `True`.

No changes to `permission_gateway.py`, `governor.py`, `terminal_launcher.py`,
`finagent_agent.py`, `pc_controller.py`, or `districts/coding/vector_mlops/**` (the vendored
package itself).

## 7. Why This Is the Smallest Safe Fix

- Reuses the exact `Action`/`gateway.execute()` mechanism already proven safe twice this session
  (Tasks 58A/58B) and established well before that (`push_github`/`solana_swap_execute`) — no new
  permission framework, no new mechanism, no new tier.
- Gates the single real chokepoint: `hf_train()` is the ONLY VECTOR-production entry point that
  reaches `hf_jobs_handler` (confirmed by the alternate-path audit, §15). Every reachability path
  (direct call, `run()`'s dispatch, Governor's exact-match, Governor's LLM-classified fallback)
  funnels through this one method.
- Does not touch `_execute_action()`, `Governor.dispatch()`, or `PermissionGateway` internals —
  zero risk to any other Governor route or RED action type.
- Does not self-mint any token — `MLOpsAgent` has zero `grant_control()`/token-minting code;
  authorization comes exclusively from `PermissionGateway.execute()`'s real decision (TEST 8a/8c,
  §16).
- Does not touch the unrelated functional bug found in §3 (missing `"operation"` key) — fixing
  that is not required to close Finding C and would expand scope beyond a security remediation.

## 8. Exact Production Files/Functions Changed

| File | Change |
|---|---|
| `core/config.py` | Added `"hf_train"` to `PermissionConfig.red` (with rationale comment). No other line touched. |
| `districts/coding/mlops_agent.py` | Added `PermissionGateway`/`Action` import; added `self._gateway = PermissionGateway()` to `__init__`; rewrote `hf_train()` to gate before entering its `_run()` closure. `ml_research()`, `hf_dataset()`, `hf_hub()`, `github_ml()`, `ml_plan()`, `run()`'s dispatch table, `self.capabilities`, `_answer_query()`, `run_forever()`: all unchanged. |

Nothing else in the production tree was modified.

## 9. Consequential Parameters and How They Are Authorized

Every caller-controlled parameter `hf_train()` accepts was audited against what it can affect
(remote code, hardware/compute, duration, script/code, requirements — `repo_id` identifies where
a trained model gets pushed but does not itself affect billing/execution risk). All five are
included verbatim in the gated `Action.params`: `script` (the arbitrary caller-supplied Python —
`execute_code`'s own established RED-gate precedent already places full code content directly in
`Action.params` with no digest/hash scheme elsewhere in the codebase, confirmed by reading its
`_execute_action()` handler fresh — this task follows that same precedent rather than inventing
a new secret-storage/digest mechanism), `repo_id`, `hardware` (compute/resource selection —
`cpu-basic` through `nvidia-a100-large`, directly billing-relevant), `timeout` (duration, directly
billing-relevant: cost scales with hardware × duration), `requirements` (additional pip packages
the job installs — part of the same "arbitrary code execution" risk surface as `script`). A
`summary` string is also included (`f"Submit HF Jobs training run: repo_id={repo_id!r},
hardware={hardware!r}, timeout={timeout}s, script={len(script)} chars,
requirements={requirements or []}"`) so the Pushover/HUD/council approval decision surfaces the
concrete hardware/duration/repo/requirements values, not just a 120-char truncated raw-params
fallback — matching `hedgebot_agent.solana_swap_execute`'s established `summary`-field pattern.
Owner HF credentials are **not** caller-controlled (they come from ambient/config state, never
from `p.get(...)`), so there is no credential-escalation surface to gate separately. TEST VERIFIED
by TEST 7 (§16): the exact `Action.params` the real gate receives were asserted directly.

## 10. Governor Exact-Match Behavior

Re-confirmed fresh this task by reading `core/city/governor.py`'s dispatch body (same logic
already re-confirmed in Task 58B, applying identically here):
`capable = [a for a in registry.get_by_district(district) if task_type in a.capabilities]; if
capable: agent = max(capable, key=health_points)`. TEST VERIFIED — TEST 4a/4b (§16) drive the real
`Governor().dispatch()` with a real `MLOpsAgent` registered and confirm the gate applies
identically to a direct call.

## 11. Governor LLM-Classified/Cross-District Behavior

Unlike Task 58B (which classified this branch as code-trace-verified only, since a
forced-empty-`capable` setup would have been structurally redundant to test separately), this
task **actually drove the fallback branch behaviorally**: a non-capable decoy `AgentBase` was
registered in `"chief_of_staff"` (so `registry.get_by_district("chief_of_staff")` is non-empty,
avoiding the `status: "no_agents"` short-circuit that occurs BEFORE the capability-match logic —
a real behavior discovered while writing TEST 5, confirmed by reading `governor.py`'s dispatch
body: `if not agents: result = {"status": "no_agents", ...}` runs before any capability check),
`MLOpsAgent` was registered under a district Governor would not guess into, and the task carried
`district="chief_of_staff"` + `"_llm_classified": True`. With the decoy occupying
`"chief_of_staff"` but declaring an unrelated capability, the exact-match `capable` list there is
empty, forcing `Governor.dispatch()`'s real `city_capable = [a for a in registry.get_all_agents()
if task_type in a.capabilities]` whole-city search to run — which found the real `MLOpsAgent` and
called its real `.run()`. BEHAVIORALLY VERIFIED — TEST 5a/5b (§16), not source-inspection-only.

## 12. Direct-Call Behavior

`MLOpsAgent().hf_train(...)` called directly (bypassing `run()`/Governor entirely) still requires
authorization — the gate lives inside `hf_train()` itself, not in `run()`'s dispatch table, so
there is no way to import the agent and call the method to skip the gate. TEST VERIFIED — TEST 3/
3b (§16).

## 13. Alias Behavior

No aliases exist for `hf_train` in `run()`'s dispatch table (`elif action == "hf_train":` is an
exact single-string match, unlike Task 58B's `launch_terminal`/`terminal`/`open_terminal` trio) —
confirmed by a fresh full read of `MLOpsAgent.run()`. A repo-wide grep for `"train"` and
`"huggingface"` as literal task_type/action strings elsewhere in the production tree found no
alias mapping to the same submission primitive (§15). No alias-specific test category applies.

## 14. External HuggingFace Boundary

The real chain from `hf_train()` to the network is:
`hf_train()` → (dynamic import under `_vector_mlops_agent_namespace()`) → `hf_jobs_handler(args)`
→ `HfJobsTool.execute()` → `HfJobsTool._run_job()` → `self.api.run_job(...)` (a real
`huggingface_hub.HfApi` method, making a real authenticated HTTPS call to HF's Jobs API). The
lowest **practical** boundary to mock for a reliable, real behavioral test is `hf_jobs_handler`
itself — the single, well-defined function `hf_train()` directly calls, fully encapsulating every
downstream network/credential/billing effect. Mocking deeper (e.g. `HfApi.run_job`) is reachable
in principle (`HfApi` is imported from the real, stably-cached `huggingface_hub` top-level
package, unaffected by the vendor namespace-swap dance) but was not necessary once the
`hf_jobs_handler`-level mock proved reliable, and mocking at `hf_jobs_handler` more directly
matches the task's own instruction to mock "only the external HuggingFace network/API/
job-submission boundary" without reaching into vendored internals.

**Mocking mechanism** (documented in detail because it required solving a real, previously-hit
difficulty): `hf_train()`'s `_run()` closure does `from agent.tools.jobs_tool import
hf_jobs_handler` fresh, inside a `with _vector_mlops_agent_namespace():` block, on every single
call — that context manager deletes and re-creates `sys.modules['agent'*]` entries each time
(needed because the vendored package's own internal imports assume a bare top-level `agent`
package, and this repo's `vectorcode/src/` also has its own, different `agent` package that would
otherwise collide). Task 57's diagnostic file documented that "attempting to monkeypatch that
import target proved unreliable across repeated runs (a fresh module object each call)" and fell
back to source-inspection only for this exact call. This task needed real behavioral tests, so it
found a robust mechanism: monkeypatch `mlops_agent._vector_mlops_agent_namespace` itself (a
single, stable, module-level object — not re-created per call, fully ordinary to monkeypatch) to
a no-op context manager, and pre-seed `sys.modules['agent']` / `['agent.tools']` /
`['agent.tools.jobs_tool']` (via `monkeypatch.setitem`, so pytest reverts them automatically after
each test) with a fake module tree whose `hf_jobs_handler` is an `async` spy. Verified working
end-to-end (real gate approval → real spy invocation, with exact args captured) before any test
in this task's suite was written. IMPLEMENTED and TEST VERIFIED across all of TEST 1–7 (§16).

## 15. Alternate-Path Audit

Repo-wide search (after implementing the fix) for: `hf_train`, `MLOpsAgent`, `hf_jobs_handler`,
`huggingface_hub`, `job.submit`, `create_job`, `submit_job`.

| Path | Classification |
|---|---|
| `districts/coding/mlops_agent.py` — `hf_train()` (direct call, `run()` dispatch, Governor exact-match, Governor LLM-classified) | **GATED** |
| `core/city/governor.py`'s `"hf_train": "coding"` district-hint entry | READ-ONLY / NON-CONSEQUENTIAL (a routing hint only — confirmed by fresh read, does not itself call anything) |
| `districts/coding/vector_mlops/__init__.py` — docstring mention of `hf_train` | READ-ONLY / NON-CONSEQUENTIAL (documentation string, not code) |
| `districts/coding/agent.py` — `("mlops_agent", "MLOpsAgent", "mlops")` manifest registration entry | READ-ONLY / NON-CONSEQUENTIAL (agent-class registration for the bootstrap loader, not an execution path) |
| `districts/coding/vector_mlops/agent/core/tools.py` — registers `hf_jobs_handler` as a tool for the vendored package's own internal `AgentLoop`/`Session`-based agent runtime | **UNCERTAIN, not RUNTIME REACHABLE from VECTOR's own code** — this is the vendored package's self-contained tool registry for a live `Session`/`AgentLoop` that `ml_research()`'s own pre-existing code comments (read fresh this task) already establish VECTOR deliberately does NOT construct ("not something safe to fake from outside that loop... A full fix (constructing a real Session + AgentLoop) is future work if that deeper capability is actually wanted"). Same UNCERTAIN-not-dormant classification Task 57 already gave to `vector_mlops` internals generally — not expanded or re-scoped by this task, since no VECTOR-side caller was found that instantiates this vendored AgentLoop. |
| `tests/test_task57_capability_bypass_diagnostic.py`, `tests/test_task58c_mlops_hf_train_permission_remediation.py` | test files, not production paths |

**No new equivalent bypass discovered.** The vendored `agent/core/tools.py` entry is not a new
finding — it is the same class of already-flagged, already-out-of-scope uncertainty Task 57
documented for `vector_mlops`'s internals generally, re-confirmed (not newly discovered) this
task and not requiring a separate follow-up beyond what Task 57 already recommended (§5 of that
document: "Verification-only follow-up... particular priority on... vector_mlops's own internal
subprocess usage").

## 16. Behavioral Tests

New file: `tests/test_task58c_mlops_hf_train_permission_remediation.py` — 16 tests, all
exercising the REAL `PermissionGateway.execute()`, `Governor.dispatch()`, and `MLOpsAgent.run()`/
`.hf_train()`, with only the external HF Jobs submission boundary (`hf_jobs_handler`, §14) and the
CouncilBrain LLM call / Pushover human-notification boundary
(`PermissionGateway._notify`/`_wait_for_confirmation`, mocked per the established codebase pattern
from Tasks 57/58A/58B) replaced. `permission_gateway.py`'s own gating logic runs for real
throughout, per `.claude/rules/testing.md`'s "No Mocking: permission_gateway.py."

| # | Test(s) | What it proves |
|---|---|---|
| 1 | `test_1_unapproved_hf_train_via_run_is_blocked` | Unapproved (council REJECT) `hf_train()`, driven through the real `run()` dispatch, never reaches the real (mocked) HF Jobs submission; `PermissionGateway.execute` is spied and confirmed actually invoked with `action_type="hf_train"`. |
| 2 | `test_2_approved_hf_train_reaches_submission_only_after_authorization` | Approved (council DEFER → simulated owner confirm) `hf_train()` succeeds; call-order spy proves `gateway.execute` happens strictly before `hf_jobs_handler`; expected `script`/`repo_id`/`hardware` values reach the (mocked) handler. |
| 3 | `test_3_direct_hf_train_call_cannot_bypass_gate`, `test_3b_..._approved_still_reaches_submission` | A direct `MLOpsAgent().hf_train(...)` call (no `run()`/Governor involved) cannot bypass the gate, and is not more-restricted than the gated path either. |
| 4 | `test_4a_governor_exact_match_unapproved_blocked`, `test_4b_..._approved_reaches_submission` | The REAL `Governor().dispatch({"type": "hf_train", "action": "hf_train", ...})`, with a real `MLOpsAgent` registered in the real agent registry, cannot bypass the boundary — unapproved blocks, approved reaches the (mocked) submission. |
| 5 | `test_5a_llm_classified_cross_district_unapproved_blocked`, `test_5b_..._approved_reaches_submission` | The REAL Governor LLM-classified whole-city fallback (§11), actually forced to execute via a non-capable decoy occupying the guessed district — not source-inspection-only. |
| 6 | `test_6a_unapproved_script_never_reaches_submission`, `test_6b_approved_script_passed_through_intact` | An attacker-shaped script (`import os; os.system(...)`) never reaches the (mocked) submission boundary unapproved; an approved exact script string is passed through byte-for-byte. |
| 7 | `test_7_consequential_parameters_visible_to_gate` | The real `Action.params` the gate receives include exact `script`/`repo_id`/`hardware`/`timeout`/`requirements` values, and a `summary` string surfacing the concrete hardware/timeout/repo_id — not merely "run training". |
| 8 | `test_8a_hf_train_source_has_no_self_mint_and_gates_before_submission`, `test_8b_hf_train_is_red_tier`, `test_8c_gateway_unreachable_fails_closed` | Source inspection confirms no `grant_control` self-mint and the gateway call/approval-check precede the `_run()` closure in source order; `hf_train` is classified RED in the real `CONFIG`; a raised gateway exception fails closed (`status: "blocked"`, zero calls reaching the (mocked) submission), never open. |
| 9 | `test_9_other_mlops_capabilities_unaffected`, `test_9b_capabilities_unaffected_by_the_fix` | No regression: `hf_hub()` still works and correctly is NOT gated by this fix (a separate, unmodified capability); `capabilities` list unchanged. |

Existing diagnostic file `tests/test_task57_capability_bypass_diagnostic.py` was updated in place
(matching the Task 58A/58B precedent): `test_hf_train_action_type_is_not_classified_in_any_
permission_tier` → `test_hf_train_action_type_is_now_classified_red` (assertion inverted, now
checks RED membership); `test_hf_train_forwards_caller_script_to_remote_job_submission_
unvalidated` (previously source-inspection-only, with an explicit note that a full mocked call
"proved unreliable") → `test_hf_train_no_longer_reaches_real_submission_without_approval`
(rewritten as a REAL behavioral test using the mocking mechanism from §14, driving `run()`
end-to-end with an unapproved council verdict and confirming the real submission boundary is
never reached — upgrading this test from source-inspection to genuine behavioral verification).
`test_mlops_declares_hf_train_capability` is unchanged (still true, capability declaration
unaffected by the fix). Finding B's tests (already updated in Task 58B) are untouched.

## 17. Test Isolation / Zero-Side-Effect Verification

Per the explicit lesson from the Task 58A incident (applied again in Task 58B, and again here):
before writing any test, the complete external boundary was inventoried (§3/§14) — confirmed
`jobs_tool.py` has **zero local OS-level primitives** (no `subprocess.*`/`os.system`/`os.popen`
anywhere in the file), so there is no local-process side-effect risk in this finding's call chain
at all — the only consequential external effect is network/credential/billing, fully intercepted
by replacing `hf_jobs_handler` itself before any real `HfApi`/`httpx` code is ever imported or
reached (confirmed: with the fake `sys.modules['agent.tools.jobs_tool']` in place, the REAL
vendored `jobs_tool.py` file — which imports `huggingface_hub.HfApi` — is never imported at all
during any test in this suite).

All 10 dangerous-path tests (TEST 1, 2, 3, 3b, 4a, 4b, 5a, 5b, 6a, 6b) were run **individually in
isolation** via `pytest path::test_name`; every isolated run: exit code 0. Because the mocking
boundary makes the real `huggingface_hub`/network code structurally unreachable (not merely
mocked-and-hoped) rather than reachable-but-intercepted, "no real HF job was created" and "no
real credentials were used" are guaranteed by construction, not merely inferred from a passing
assertion — the only production code path that could construct an authenticated `HfApi` instance
in this chain (`agent.tools.jobs_tool.py`) is never imported under any test in this file. (An
earlier draft additionally monkeypatched `httpx.Client`/`AsyncClient` process-wide as a second,
belt-and-suspenders network guard — this was found to break an unrelated `huggingface_hub`
module's import-time type-annotation evaluation (`_GLOBAL_CLIENT: httpx.Client | None = None`
raises `TypeError` once `httpx.Client` is replaced by a plain function) for zero additional
safety given the structural guarantee above, so it was removed; see the module's own top-of-file
comment for the full account.) The updated diagnostic test
(`test_hf_train_no_longer_reaches_real_submission_without_approval`) was also run individually in
isolation with the same result.

## 18. Full Regression Results

Baseline (established across Tasks 52–58B, `tests/unit` + `tests/integration` excluding
`test_planning.py`'s 2 independently pre-existing broken tests, per established precedent):
**2212 collected / 2175 passed / 8 failed / 0 errors / 29 skipped.**

This task's run of the identical scope: **8 failed / 0 errors / 29 skipped** — same 8 failing
test names, exact match (identical list to Task 58B's regression run, all previously root-caused
and unrelated to this task's diff):

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

Skipped count (29) is an exact match to baseline. **Zero new failures in the tracked baseline
scope. Identical to baseline.**

Beyond the tracked baseline scope, the rest of `tests/` was also run this task:

- `tests/districts/`: **0 failures.**
- Root-level `tests/*.py` (130 files): **12 failures** — 5 already accounted for/previously
  documented as pre-existing/unrelated (Task 54/58B): `test_frontend_bundle.py` (stale bundle
  hash), `test_permission_gateway.py::test_red_action_times_out_without_confirmation` (pending_id
  signature drift), `test_regression_governor_capability_routing.py`'s 2 embedding-drift
  failures, `test_openwa_absorption.py::TestBulkSender::test_exception_in_send_counted_as_failure`
  (order-dependent flake — re-confirmed passes in isolation) + 7 newly investigated this task
  (below).
- `tests/backend`, `tests/core`, `tests/emergency`, `tests/event_bus`, `tests/frontend`,
  `tests/hands`, `tests/loop`, `tests/persona`, `tests/personality`, `tests/research_engine`,
  `tests/resilience`, `tests/training`, `tests/voice`: **1 failure**
  (`tests/backend/test_webauthn_middleware_integration.py::test_wrong_token_type_rejected_
  type_confusion`, already documented as pre-existing/unrelated in Task 58B).

The 7 newly-surfaced-this-task failures (`tests/test_postiz_absorption.py`'s
`TestBlogPublisherDevTo` ×4, `TestBlogPublisherHashnode::test_successful_publish_mock`,
`TestBlogPublisherMedium` ×2) were individually investigated and root-caused:

| Test(s) | Root cause | Related to Finding C? |
|---|---|---|
| All 7 `test_postiz_absorption.py::TestBlogPublisher*` failures | Fail even when run in complete file isolation (not an ordering flake). Traced to `districts/content/blog_publisher.py`'s `_check_blog_dedup()`: every `publish_*()` method checks a real, persistent SQLite `blog_dedup` table (in the shared `episodic.db`) keyed on `sha256(f"{platform}\|{title}")` with a 24-hour suppression window, before doing any real (mocked, in the test) publish call. The tests all reuse the same literal title ("My Title") every run with no dedup-state reset between runs; a prior run within this session (this task's earlier full-suite passes) already recorded that dedup hash, so this run's mocked publish calls are short-circuited by `_check_blog_dedup()` returning `True` — confirmed via the log line `"Dev.to duplicate suppressed: 'My Title'"` (and the Hashnode/Medium equivalents) captured in the failure output. A pre-existing test-isolation defect in `test_postiz_absorption.py`/`blog_publisher.py` (no test-scoped dedup-state reset), surfaced only because this is the first time this session `test_postiz_absorption.py` happened to run twice within the 24h dedup window. `districts/content/blog_publisher.py` and `core/memory/episodic.py` were never touched by this task. | No |

All other failures match the exact same root causes already documented in Task 58B's regression
section (test_frontend_bundle staleness, the `pending_id` test-signature bug, the 2 embedding-
drift Governor-routing tests, the order-dependent openwa flake, the WebAuthn test) — not
re-investigated from scratch since the files involved are unchanged since that verification.

**Targeted tests** (`tests/test_task58c_mlops_hf_train_permission_remediation.py`, 16 tests):
16/16 pass, including all 10 dangerous-path tests individually isolated. **Relevant tests**
(`tests/test_task57_capability_bypass_diagnostic.py` 6/6, `tests/test_task57_device_control_
bypass_diagnostic.py` 4/4, `tests/test_task58a_play_music_escalation_remediation.py` 12/12,
`tests/test_task58b_finagent_terminal_permission_remediation.py` 16/16, `tests/districts/coding`,
`tests/test_governor.py`, `tests/test_governor_taint_block.py`, `tests/test_regression_governor_
capability_routing.py`, `tests/unit/test_permission_gateway.py` + `tests/unit/test_permission_
gateway_extra.py`, `tests/test_permission_gateway.py`, `tests/integration/test_phase_a7_council_
red_tier.py`, `tests/test_llm_council.py`, `tests/test_trust_ladder.py`): all pass except the 4
pre-existing/unrelated failures already documented above.

**Static/lint/type checks**: `ruff` and `mypy` are **not available** in this environment
(`ruff --version` / `mypy --version` both `command not found`) — same as every prior task this
session. `py_compile` syntax check and a live `import` of both modified modules (`core.config`,
`districts.coding.mlops_agent`) both succeed cleanly.

## 19. Residual Limitations

- **Separate, non-security finding** (§3): `hf_train()`'s `args` dict passed to `hf_jobs_handler`
  never sets the required `"operation"` key and never passes a `session`/`hf_token` — the
  pre-existing, unmodified call to the real HF Jobs library would itself error out today before
  reaching the real submission. Not fixed (explicitly out of scope for this security
  remediation); noted for the owner as a genuine functional defect independent of Finding C.
- `districts/coding/vector_mlops/agent/core/tools.py`'s internal `AgentLoop`/`Session`-based tool
  registry (§15) remains UNCERTAIN, matching Task 57's own prior classification — not expanded or
  newly investigated by this task since no VECTOR-side caller was found that reaches it.
- `tests/test_postiz_absorption.py`'s dedup-state test-isolation defect (§18) was newly surfaced
  and root-caused but not fixed — unrelated to Finding C, a `districts/content/blog_publisher.py`
  test-hygiene issue.
- The other Task 57 residuals (`phone_controller.py`'s shared token-scope tuple; the remaining
  ~40 unread subprocess files, "with particular priority on vector_backtest's and vector_mlops's
  own internal subprocess usage" per Task 57's own §5 recommendation) remain open and out of
  scope for 58A/58B/58C all.

## 20. Final Status

All 20 acceptance criteria satisfied:

- [x] Finding C's actual hf_train permission bypass is closed
- [x] An unapproved hf_train request cannot submit a remote job (TEST 1, 3, 4a, 6a)
- [x] An unapproved hf_train request cannot cause remote execution (same tests — the submission boundary is never reached)
- [x] Owner HuggingFace credentials cannot be used by an unapproved request (the credential-touching module is never imported unapproved — structural guarantee, §17)
- [x] The consequential parameters are covered by the authorization decision (TEST 7)
- [x] hf_train has an appropriate permission classification (RED, §4/§5/§6)
- [x] The real external submission occurs only downstream of authorization (TEST 2 call-order, TEST 8a source-order)
- [x] Direct hf_train invocation cannot bypass authorization (TEST 3/3b)
- [x] Governor exact-match routing cannot bypass authorization (TEST 4a/4b)
- [x] Governor LLM/cross-district routing cannot bypass authorization (TEST 5a/5b — behaviorally verified, not source-inspection-only)
- [x] Supported aliases cannot bypass authorization (none exist — confirmed, §13)
- [x] No self-minted authorization exists (TEST 8a)
- [x] No alternate Finding-C path remains unguarded (§15 alternate-path audit — all paths gated, read-only, or pre-existing UNCERTAIN vendored territory already flagged by Task 57)
- [x] Real PermissionGateway logic was exercised in behavioral tests (all 16 targeted tests, no mocking of `permission_gateway.py`)
- [x] External HuggingFace submission was mocked and NEVER actually invoked (structurally unreachable, §17)
- [x] No real credentials were used (same)
- [x] Dangerous-path tests were run individually (10/10, §17)
- [x] Zero unintended external/local side effects occurred during final testing
- [x] Full regression is compared against the tracked baseline (identical: 8 failed / 0 errors / 29 skipped)
- [x] No unrelated architecture was modified (2 production files, additive/localized changes only)
- [x] Documentation is complete (this document)

**58C — FIXED + BEHAVIORALLY VERIFIED**

Per the task's explicit stop condition: stopping here. Not proceeding to 59, 60, Task 54
re-verification, benchmark, or the 7-day experiment.
