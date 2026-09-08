# Task 58F — Incident Playbook Destructive-Action Permission Remediation

## 1. Executive Verdict

**58F — FIXED + BEHAVIORALLY VERIFIED.**

`districts/security/incident_playbook_runner.py`'s four destructive OS-level primitives
(`block_ip`, `unblock_ip`, `kill_process` — which `isolate_process` also inherits, since it
delegates internally to the same handler) now require a real `PermissionGateway` RED approval
before their real `subprocess.run()` call, regardless of which of the confirmed entry points
(direct call, `run()` dispatch, `Governor.dispatch()`, or a fully-built-but-dormant autonomous
SIEM pipeline discovered during this task) reaches them. Read-only/notification steps remain
fully autonomous and ungated, per the smallest-boundary requirement.

## 2. Exact Pre-Fix Attack/Reachability Chain

```
Governor.dispatch(task_type="execute_playbook")                    [exact-match capability route]
  -or- IncidentPlaybookRunner().run({"type":"execute_playbook", "params":{...}})   [direct/run() route]
  -or- IncidentPlaybookRunner().execute_playbook(playbook, evidence, alert_id)     [direct method call]
  -or- SIEMPipeline.async_process_event(event) -> execute_playbook(...)           [autonomous route, dormant]
  -> execute_playbook(playbook, evidence, alert_id)
     -> for step in playbook["steps"]:
          -> _execute_action(step["action"], step["params"], evidence, incident_id)
             -> handlers = {"block_ip": ..., "unblock_ip": ..., "kill_process": ...,
                             "isolate_process": ..., ...}
             -> [PRE-FIX] _action_kill_process(params, evidence, incident_id)
                   pid = params.get("pid", 0)   # caller/playbook-step-controlled
                   subprocess.run(["taskkill", "/F", "/PID", str(pid)], ...)   # REAL, UNRESTRICTED
             -> [PRE-FIX] _action_isolate_process(params, evidence, incident_id)
                   pid = params.get("pid", evidence.get("pid", 0))   # EVIDENCE-controlled
                   -> _action_kill_process({"pid": pid}, ...)                  # same real primitive
             -> [PRE-FIX] _action_block_ip / _action_unblock_ip(params, evidence, incident_id)
                   ip = params.get("ip", evidence.get("target", ""))   # caller/evidence-controlled
                   subprocess.run(["netsh", "advfirewall", "firewall", "add"/"delete", ...], ...)
```

Zero `PermissionGateway` reference existed anywhere in this file before this task.

## 3. Root Cause

Same class as Findings A–G: real, destructive, unsandboxed OS-level primitives reachable through
ordinary Governor capability routing (and, as this task's own fresh trace found, a dedicated
autonomous SIEM pipeline) with no authorization boundary. Task 59's own prior audit noted the
currently-packaged `core_playbooks.yaml` never invokes the destructive handlers and classified
this UNCERTAIN rather than CONFIRMED — but, per this task's explicit instruction, "currently no
packaged playbook uses it" was never a real security boundary: any caller supplying its own
`playbook`/`evidence` dict (direct call, `run()`, or a future/owner-authored packaged playbook)
could already reach every destructive handler unauthorized.

## 4. Phase 1 — Pre-Fix Reachability Table

Traced fresh this task, not assumed from Task 59's description. `Do not assume the three named
handlers are exhaustive` was taken literally: `_execute_action()`'s full handler map (`block_ip`,
`unblock_ip`, `capture_process_snapshot`, `kill_process`, `notify`, `log_evidence`,
`isolate_process`, `collect_memory_dump`, `run_antivirus`, `escalate_to_human`) was read in full.
**`block_ip` was found to be a fourth real destructive handler Task 59's own writeup did not
name** — it shares the identical evidence-controlled-target pattern and real firewall side effect
as `unblock_ip`.

| Action | Entry point(s) | Caller-controlled input | Real side effect | Pre-fix gate | Autonomously reachable? | Severity |
|---|---|---|---|---|---|---|
| `block_ip` | Governor exact-match; direct call; `run()`; SIEM pipeline (dormant) | `ip` via `params.ip` or `evidence.target` — fully caller-controlled on the direct/`run()` path | Real `netsh advfirewall firewall add rule ... action=block remoteip={ip}` | NONE | Yes | HIGH — arbitrary outbound-IP block; DoS/self-sabotage potential |
| `unblock_ip` | same | `ip` via `params.ip` or `evidence.target` | Real `netsh advfirewall firewall delete rule` | NONE | Yes | HIGH — removes a block rule; could re-enable blocked malicious traffic or erase a prior block's effect |
| `kill_process` | same | `pid`/`name` via `params` (playbook step params, or direct caller params) | Real `taskkill /F /PID <pid>` or `/IM <name>` — **unrestricted target** | NONE | Yes | CRITICAL — can kill any process, including critical VECTOR processes or unrelated OS/user processes |
| `isolate_process` | same | `pid` via `params.pid` or **`evidence.pid`** — directly evidence-controlled, Task 59's original concern | Delegates to `kill_process` | NONE | Yes | CRITICAL — same as `kill_process`, plus a more direct evidence-injection path |
| `capture_process_snapshot` | same | none consequential | `tasklist`/`netstat` (read-only) + local file write | N/A | Yes | LOW — diagnostics only |
| `notify`, `escalate_to_human` | same | message text (logged only) | log line | N/A | Yes | NONE |
| `log_evidence` | same | arbitrary `evidence` dict content | local JSON file write | N/A | Yes | LOW — data persistence, no code execution |
| `collect_memory_dump`, `run_antivirus` | same | none | **currently stubs** — log only, no real effect | N/A | Yes | NONE (today) |

No production code modified during this phase, per the task's explicit instruction.

**Fresh finding beyond Task 59's own scope**: `districts/security/siem_pipeline.py`'s
`SIEMPipeline` connects `LogAggregator → DetectionRules → IncidentPlaybookRunner` and its
`async_process_event()` calls `self.playbook_runner.execute_playbook(pb, alert["evidence"],
alert["alert_id"])` directly, with **zero owner approval anywhere**, once a `DetectionRules`
match's `suggested_action` names a `playbook:<id>`. `wire_loguru_sink()` would feed this from any
WARNING+ VECTOR log line. Confirmed via a repo-wide search: `SIEMPipeline` is **not** instantiated
anywhere in `core/`/`districts/` outside its own file/tests, and — unlike `IncidentPlaybookRunner`
itself, which **is** registered in `districts/security/__init__.py`'s agent-construction map —
`SIEMPipeline` is **not** in that map, so it is not independently Governor-reachable either.
**DORMANT / NOT RUNTIME REACHABLE today**, but a fully-built, one-registration-away autonomous
auto-response pipeline that would call `execute_playbook()` with zero owner approval the moment it
is wired in — exactly the class of latent risk the task's "must not rely on 'currently
unreachable'" framing warns about. Documented, not silently ignored (§7, §12); automatically
inherits this fix regardless of its dormancy, since the gate lives inside the shared destructive
handlers `execute_playbook()` itself calls, not at `execute_playbook()`'s own entry.

`process_loop()`'s own `_event_queue`-driven trigger inside `incident_playbook_runner.py` was also
checked: nothing in production code feeds it (no caller of `.process_loop()` or a queue-`.put()`
was found outside the file itself and `siem_pipeline.py`'s own, separate queue) — also dormant
today, also automatically covered by the same fix.

No MCP/API/CLI route exposing this functionality was found (`core/api/routers/` and
`core/mcp_server.py` both searched, zero references).

## 5. Phase 2/3 — Security Boundary and Implementation

**Chosen boundary**: gate the individual destructive handlers themselves
(`_action_block_ip`, `_action_unblock_ip`, `_action_kill_process` — which
`_action_isolate_process` inherits automatically via its existing internal delegation to
`_action_kill_process`), not the top-level `execute_playbook()`/`run()` capability. Reasoning,
directly required by the task's own Phase 2 instructions:

- Gating the top-level playbook capability would force **every** playbook invocation — including
  the fully-harmless `log_evidence`/`notify`/`capture_process_snapshot`/`escalate_to_human` steps
  — through an owner-approval RED gate, defeating the automated-incident-response system's own
  purpose (this is reinforced by discovering `siem_pipeline.py`, §4: a genuinely-autonomous
  SIEM auto-response pipeline that is legitimately supposed to act without a human tap for its
  safe steps).
- Gating only the top level would also fail the task's own explicit "arbitrary/caller-controlled
  playbook content [must not] smuggle a destructive operation through a generic execution path"
  requirement in the opposite direction: an *approved* generic "run this playbook" action could
  still contain an unauthorized destructive step the approver never specifically saw.
- Gating each handler at its own real side-effect point is the narrowest boundary that
  **guarantees** the destructive primitives themselves cannot execute without authorization,
  regardless of which playbook, evidence shape, or entry point reaches them — matching the
  established Task 58A–58G "gate at the point of effect" pattern.

**Files changed**:

- **`core/config.py`**: added `"block_ip"`, `"unblock_ip"`, `"kill_process"` to
  `PermissionConfig.red` (with an inline rationale comment matching the established 58-series
  style). No new permission tier. Not added to `RED_INTERACTIVE_TOOLS` — nothing routes an
  owner-typed/spoken command directly to these action_types.
- **`districts/security/incident_playbook_runner.py`**:
  - Added `from core.loop.permission_gateway import PermissionGateway, Action`.
  - Added `self._gateway = PermissionGateway()` to `__init__`.
  - Added a shared `_gate_destructive_action(action_type, params, incident_id)` helper: calls
    `self._gateway.execute(Action(action_type=..., params={**params, "incident_id": incident_id},
    proposed_by=self.name))`; returns `None` if approved (caller proceeds to the real side
    effect); returns `{"status": "error", "message": "blocked by permission gateway: <reason>"}`
    (or `"blocked: permission gateway unavailable: <e>"` on a gateway exception — fail-closed) if
    not. **The `{"status": "error", ...}` shape was deliberately chosen to match this file's own
    pre-existing convention** — `execute_playbook()`'s existing step loop already checks
    `result.get("status") == "error"` to mark a step failed and trigger rollback; returning
    `"error"` here means an unauthorized destructive step is correctly treated as a real failure
    by logic that already existed, with zero changes needed to that logic.
  - `_action_block_ip`, `_action_unblock_ip`, `_action_kill_process` each now call
    `_gate_destructive_action(...)` immediately after their existing "is a target even specified"
    validation and before their real `subprocess.run(...)` call, returning early on a non-`None`
    result. `_action_isolate_process` is unchanged — it already delegates to
    `_action_kill_process`, so it inherits the gate automatically.
  - The `Action`'s `params` include the target (`ip`, or `pid`/`name`), `incident_id`, and a
    human-readable `summary` (e.g. `"Force-kill process 4242 (incident a1b2c3d4)"`) — no secrets,
    no raw evidence dict dumped verbatim.

No changes to `Governor`, `PermissionGateway`, `siem_pipeline.py`, `detection_rules.py`, or any
packaged playbook YAML.

## 6. Before/After Call Graph

```
BEFORE:
_execute_action(action, params, evidence, incident_id)
  -> handlers[action](params, evidence, incident_id)
       -> [block_ip/unblock_ip/kill_process] real subprocess.run(...)   <- NO GATE

AFTER:
_execute_action(action, params, evidence, incident_id)
  -> handlers[action](params, evidence, incident_id)
       -> [block_ip/unblock_ip/kill_process]
            -> _gate_destructive_action(action_type, {target..., summary}, incident_id)
                 -> PermissionGateway.execute(Action(...))   <- REAL RED GATE
                 -> not approved / exception -> return {"status":"error", ...}  (no further code runs)
            -> if approved: real subprocess.run(...)
       -> [isolate_process] -> _action_kill_process(...) -> (same gate, inherited)
       -> [log_evidence/notify/capture_process_snapshot/escalate_to_human/
           collect_memory_dump/run_antivirus] -> UNCHANGED, no gate, fully autonomous
```

## 7. All Alternate Entry Points Checked

Phase 1 (pre-fix) and Phase 8 (post-fix, repeated independently) repo-wide searches for
`execute_playbook`, `IncidentPlaybookRunner`, `kill_process`, `isolate_process`, `block_ip`,
`unblock_ip`, direct `subprocess`/`taskkill`/`netsh advfirewall` usage, `PermissionGateway`
usage, and Governor capability registrations, run both before and after the code change (results
identical both times):

| Path | Status |
|---|---|
| `Governor.dispatch(task_type="execute_playbook")` (exact-match capability route) | **GATED** (behaviorally verified, TEST 13a/13b) |
| Direct `IncidentPlaybookRunner().execute_playbook(...)` | **GATED** (TEST 11, 12) |
| `IncidentPlaybookRunner().run({"type": "execute_playbook", ...})` | **GATED** (TEST 12b) |
| `SIEMPipeline.async_process_event()` → `execute_playbook()` | DORMANT / NOT RUNTIME REACHABLE today — not instantiated anywhere in `core/`/`districts/` outside its own file/tests, not in the district's agent-bootstrap map. **Would inherit the gate automatically** if ever wired in, since the gate lives in the destructive handlers `execute_playbook()` itself calls (TEST 15). |
| `IncidentPlaybookRunner.process_loop()`'s own `_event_queue` trigger | DORMANT — nothing in production code feeds this queue. Same automatic-inheritance property as above. |
| MCP/API/CLI routes | None found — `core/api/routers/` and `core/mcp_server.py` both searched, zero references to this subsystem. |
| `core/resilience/injectors/network_chaos.py`, `core/resilience/injectors/process_kill.py` | Found during the `taskkill`/`netsh` search — **confirmed unrelated**: chaos-engineering/resilience-testing tools for a different purpose (deliberately disrupting VECTOR's own processes/network to test supervisor recovery), not part of `execute_playbook`'s handler chain, out of this task's scope. Not investigated further, per the task's explicit stop condition — flagged here as a separate item if the owner ever wants those audited too, not expanded into. |
| `districts/ops/devops_automator.py`'s `taskkill` usage | Already independently audited in Task 59 (§12 of that doc) — confirmed **VERIFIED GATED** via a real `gateway.execute()` call before the kill (a pre-existing, unrelated action_type-labeling clarity issue was noted there, not a bypass). Unrelated to this finding, not touched. |

No alternate path was found that bypasses the new boundary.

## 8. Tests Added and Results

New file: `tests/test_task58f_incident_playbook_destructive_action_permission_remediation.py` —
19 tests, all exercising the REAL `PermissionGateway.execute()`, `Governor.dispatch()`, and
`IncidentPlaybookRunner`'s real `execute_playbook()`/`run()`/handler methods, with only
`subprocess.run` (the actual `netsh`/`taskkill` primitive) and the gateway's human-notification
boundary (`_notify`/`_wait_for_confirmation`) replaced. Every test uses an isolated `tmp_path` for
`playbooks_dir`/`db_path`.

| Requirement | Test(s) | Result |
|---|---|---|
| 1/2. kill_process blocked/executes | `test_1_...`, `test_2_...` | PASS |
| 3/4. isolate blocked/executes | `test_3_...`, `test_4_...` | PASS |
| 5/6. unblock_ip blocked/executes | `test_5_...`, `test_6_...` | PASS |
| (bonus) block_ip blocked/executes | `test_block_ip_blocked_without_approval`, `test_block_ip_executes_after_approval` | PASS — the fourth handler found in Phase 1 |
| 7. gateway exception fails closed | `test_7_...` (all three gated handlers) | PASS |
| 8. no self-mint | `test_8_...` (source inspection, all 3 handlers + shared helper) | PASS |
| 9. caller-controlled PID cannot bypass | `test_9_...` (4 distinct PIDs, all blocked, gate genuinely consulted each time) | PASS |
| 10. caller-controlled IP cannot bypass | `test_10_...` (4 distinct IPs) | PASS |
| 11. arbitrary playbook content cannot bypass | `test_11_...` (fully caller-constructed playbook dict, not a packaged YAML) | PASS |
| 12. direct execute_playbook cannot bypass | `test_12_...`, `test_12b_...` (direct call + `run()`) | PASS |
| 13. Governor route converges with direct route | `test_13a_...`, `test_13b_...` | PASS |
| 14. harmless/read-only operations unaffected | `test_14_...` (4-step harmless playbook, zero gateway calls) | PASS |
| 15. every discovered destructive handler protected | covered by 1–6, bonus block_ip test, plus `block_ip` was itself the "additional handler discovered during Phase 1" | PASS |

19/19 pass. 16 dangerous-path tests were each also run individually in isolation
(`pytest path::test_name`), every one `exit=0`. Post-sweep verification:
`netsh advfirewall firewall show rule name=all` shows zero `VECTOR_Block_*` rules (confirming no
real firewall rule was ever created or left behind); no real process was killed (trivially true —
this session's own Python process is still running); `git status --short` shows only this task's
own two changed/new files.

## 9. Adversarial Composition Result

TEST 11 (§8) is the direct composition test the task's Phase 5 required: a fully attacker/LLM-
constructed `playbook` dict (not one of VECTOR's own packaged YAML files) with a `kill_process`
step and a caller-supplied `pid`, driven through the real `execute_playbook()` step-execution
loop with no approval. Result: zero real `subprocess.run` calls, the step is marked `"failed"`,
the incident is marked `"FAILED"`. TEST 9/10 extend this to prove the result is identical across
multiple distinct caller-supplied PID/IP values — the gate is genuinely consulted every time, not
bypassed by any particular value. **No composition of generic playbook/input construction +
caller-controlled evidence + destructive operation was found to reach the real primitive without
approval.**

## 10. Full Regression Result

**Targeted**: 19/19 new tests pass; 16 dangerous-path tests individually isolated, all clean.

**Relevant** (`tests/integration/test_spec04_siem.py`, `tests/districts/security/test_detection_
rules.py`, `tests/test_task58a_...` through `tests/test_task58g_...`, Governor/PermissionGateway/
trust-ladder suites, `tests/test_karpathy_lab_run_wiring.py`, `tests/districts/security/`): all
pass except the same 4 pre-existing, already-root-caused-in-prior-tasks failures
(`test_regression_governor_capability_routing.py`'s 2 embedding-drift tests, `test_permission_
gateway.py`'s `pending_id` signature drift, `test_phase_a7_council_red_tier.py`'s empty
`COUNCIL_AUTO_PROCEED_ALLOWED` test) — identical failure list to every prior 58-series task's own
regression run of this same battery. No flaky or environmental failures were observed this task
(unlike Tasks 58B/58E/58G, which each hit one non-deterministic timing flake in their large
combined batteries — none reproduced here).

**Full tracked baseline** (`tests/unit` + `tests/integration`, excluding `test_planning.py`'s 2
independently pre-existing broken tests): **8 failed / 0 errors / 29 skipped — exact same 8
failing test names**, exact match to the documented baseline (`2212 collected / 2175 passed / 8
failed / 0 errors / 29 skipped`). Zero new failures.

**Baseline failures** (pre-existing, unrelated, unchanged by this task): the 8 listed above.
**New failures**: none. **Flaky failures**: none observed this task. **Environmental failures**:
none observed this task.

**Static/lint/type checks**: `ruff` and `mypy` are **not available** in this environment
(`command not found`) — same as every prior task this session. `py_compile` and a live `import`
of both modified modules succeed cleanly.

## 11. Runtime Behavioral Verification Result

Phase 7's explicit requirement — driven with the REAL `IncidentPlaybookRunner`, REAL
`PermissionGateway` (including real `_classify()`/`_handle_red_tier()` verdict processing; only
the external CouncilBrain LLM call and the human Pushover confirmation boundary simulated), and
the REAL `Governor.dispatch()` routing/capability-match layer:

**WITHOUT APPROVAL** (TEST 13a): `Governor.dispatch({"type": "execute_playbook", "district":
"security", "params": {"playbook_id": "danger", "evidence": {}}})` against a real registered
`IncidentPlaybookRunner`, with a real destructive (`kill_process`) playbook and a real council
REJECT verdict → the real `PermissionGateway.execute()` call is made, returns unapproved, the
handler returns `{"status": "error", ...}`, `execute_playbook()`'s existing logic marks the
incident `FAILED` → **zero real subprocess call** (mocked `subprocess.run` spy: empty).

**WITH APPROVAL** (TEST 13b): identical setup, real council DEFER verdict + simulated owner
confirmation → the real gate approves → the real (mocked-at-the-OS-primitive-level) `subprocess.
run` is reached with the correct `taskkill`/`netsh` command shape.

Both directions demonstrated end-to-end through the real Governor→agent→gateway chain, not merely
at the handler level in isolation (TEST 1–6, 9–12 additionally demonstrate the same invariant
directly against the handlers and `execute_playbook()`).

## 12. Remaining Limitations

- `SIEMPipeline`'s dormancy (§4, §7) was confirmed by a repo-wide search for instantiation/
  bootstrap-registration within `core/`/`districts/` — not by proving no external
  configuration or future commit could wire it in. This does not weaken the security conclusion
  (the fix is already in place at the shared handler level, §7), only the "not currently
  reachable" characterization's shelf life.
- `core/resilience/injectors/network_chaos.py` and `process_kill.py` (§7) were noticed but
  explicitly not investigated, being a different subsystem/purpose entirely — flagged as a
  possible separate future audit item, not expanded into per this task's stop condition.
- `collect_memory_dump` and `run_antivirus` are currently no-op stubs (§4) — they were left
  ungated since they have no real side effect today; if either is ever implemented with a real
  destructive/consequential effect, it would need the same treatment applied here, per the
  pattern this task establishes (not itself a limitation of the fix, but noted for future
  awareness).
- The `target` variable computed at the top of `_execute_action()` (`target = evidence.get(
  "target", params.get("ip", ""))`) appears to be dead code (never referenced again in that
  function) — noticed during tracing, not touched, as it has no security relevance and fixing
  dead code is outside this task's scope.

## 13. Final Classification

**58F — FIXED + BEHAVIORALLY VERIFIED**

Every currently reachable path to `block_ip`, `unblock_ip`, `kill_process`, and (via delegation)
`isolate_process` — Governor exact-match routing, direct method calls, `run()` dispatch, and the
dormant-but-automatically-covered `siem_pipeline.py`/`process_loop()` paths — passes real
`PermissionGateway` authorization before the real OS-level side effect. Unauthorized attempts,
gateway exceptions, and adversarial tool/evidence composition all fail closed with zero real side
effect, verified behaviorally (not merely by test existence or by the presence of
`PermissionGateway` text in the modified function). Harmless/read-only playbook operations remain
fully unaffected and ungated. Full regression is identical to the tracked baseline.

Per the task's stop condition: not continuing into any unrelated security finding after this
task.
