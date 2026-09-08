# Task 59 — Residual Permission / Side-Effect Surface Verification

**VERIFICATION-ONLY. No production code was modified in this task.**

## 1. Executive Summary

After Tasks 58A/58B/58C closed the three CONFIRMED bypasses from Task 57 (`play_music`,
`launch_terminal`, `hf_train`), this task swept the explicitly-named residual surfaces (phone
controller token scope, the remaining subprocess/os.system sweep, `vector_backtest`,
`vector_mlops` internals, and a capability↔permission consistency check) for additional
autonomous permission bypasses.

**One new CONFIRMED BYPASS was found**, matching the exact architectural pattern of Findings
A/B/C: `districts/karpathy_lab/autoresearch_runner.py`'s `run_experiment_cycle` capability
writes LLM-generated Python to `train.py` and executes it via a real, ungated `subprocess.run()`
call, reachable through ordinary `Governor.dispatch()` capability-match with **zero
PermissionGateway involvement** and **zero permission-tier classification**. This is designated
**Finding D**.

Two further HIGH-severity items were traced in `districts/investment/vector_backtest/` and
`districts/security/incident_playbook_runner.py` that are architecturally ungated but are
**not currently demonstrated as reachable** due to unrelated bugs/empty playbook inventory —
classified UNCERTAIN, flagged for proactive follow-up rather than treated as confirmed blockers,
per this task's explicit evidentiary bar.

**Overall verdict: 59 — NEW BLOCKER(S) FOUND** (one confirmed: Finding D).

## 2. Scope

Per the task's explicit instructions, this covers only: (A) phone controller permission/token
scope, (B) the remaining subprocess/os.system sweep, (C) `vector_backtest` execution surfaces,
(D) `vector_mlops` internal execution surfaces, (E) a focused capability↔permission consistency
cross-check for obvious equivalents of Findings A/B/C, (F) autonomous reachability synthesis,
(G) diagnostic-only testing, (H) an 58A/58B/58C regression sanity check. This is explicitly NOT
a general security audit of all of VECTOR — files/subsystems outside these residuals were not
exhaustively re-audited. No production code, permission tier, Governor logic, PermissionGateway
logic, autonomous loop, or agent capability was modified.

## 3. Current Baseline After 58A/58B/58C

Independently re-confirmed (not merely re-reading the docs) that all three fixes are present in
current source:

- `core/config.py` `PermissionConfig.red` contains `"launch_app"` (58A's narrowed token-check
  target), `"launch_terminal"` (58B), and `"hf_train"` (58C) — confirmed via direct grep of the
  current file.
- `core/control/pc_controller.py:234`: `launch_app()`'s token check is
  `self._verify_control_token(control_token, "launch_app")` — single-value, matches 58A's fix.
- `districts/investment/finagent_agent.py:516`: `launch_terminal()` calls
  `self._gateway.execute(Action(...))` before touching the real launcher — matches 58B's fix.
- `districts/coding/mlops_agent.py:345`: `hf_train()` calls `self._gateway.execute(Action(...))`
  before touching the real HF Jobs submission — matches 58C's fix.
- Full regression re-run of all four tasks' test suites (58A: 12, 58B: 16, task57 diagnostic: 6,
  task57 device-control diagnostic: 4 — 38 total, plus 58C's 16, minus overlap in the combined
  run reported below): all pass, zero failures (§10).

## 4. Phone Controller Audit

Fresh trace, not trusted from Task 57's description.

**Mechanism**: `PermissionGateway.grant_control(action_type, uses, ttl)` mints an opaque
`secrets.token_hex(8)` string bound to exactly one `action_type`, stored in `PermissionGateway`'s
`_control_grants` dict. `PermissionGateway.__new__` makes `PermissionGateway()` **always return
the one process-wide shared instance** (confirmed by reading the class fresh — an explicit
singleton pattern, not per-call instantiation), so `_control_grants` is effectively global
process state: a token minted anywhere in the process is verifiable anywhere else.
`verify_control(token, action_type)` refuses on missing/expired/exhausted/**mismatched**
`action_type` — real, working per-action-type scoping at the primitive level.

`PCController._verify_control_token(token, *allowed_action_types)` and
`PhoneController._verify_control_token(token, *allowed_action_types)` both accept a token if it
matches **any** of several caller-declared action types — this is the "shared scope" mechanism
Task 57 flagged. Fresh audit of every call site:

| Controller | Call site | Accepted action types | Same tier? |
|---|---|---|---|
| PC | tap (2 variants) | `pc_click, click_screen, vision_control` / `pc_click, click_screen, gui_task, desktop_task, vision_control` | All RED |
| PC | type (2 variants) | `pc_type, gui_task, desktop_task` | All RED |
| PC | launch_app | `launch_app` only | Single (58A fix) |
| PC | play_music | `play_music` only | Single (58A fix) |
| PC | run_shell_command | `run_shell_command` only | Single |
| Phone | unlock/tap/swipe/type_text/etc. (6 call sites) | shared tuple: `instagram_post_via_phone, youtube_upload_via_phone, pc_click, click_screen, gui_task, desktop_task, vision_control, pc_type, launch_app, play_music` | **Mixed — includes `play_music` (GREEN) alongside RED entries** |

**The one real cross-tier mixing found**: `PhoneController._control_action_types` includes
`"play_music"` (GREEN, auto-executes with zero owner approval) in the same shared-acceptance
tuple as several RED phone-interaction primitives. In principle, a `"play_music"`-scoped token
would be accepted by `PhoneController.unlock()`/`.tap()`/etc.

**Traced whether this is actually exploitable** (per this task's explicit instruction: a shared
scope is not itself a vulnerability without a demonstrated privilege-escalation chain):

- `grant_control()` is called in exactly 5 production places: `permission_gateway.py`'s
  `play_music`/`launch_app`/`run_shell_command` handlers (each mints and *immediately, internally*
  consumes its own token against its own matching `PCController` primitive — the token value
  never escapes that closure), and `districts/content/phone_poster.py`'s two calls (both **after**
  a real `PermissionGateway().request_approval(action_type="instagram_post_via_phone"/
  "youtube_upload_via_phone", ...)` call that fails closed on any error/timeout/rejection).
- `request_approval()` (re-read fresh) is a hardcoded, always-real-owner-approval path — it does
  **not** consult `core/config.py`'s GREEN/YELLOW/RED classification at all, does not go through
  CouncilBrain auto-proceed, and always does the Pushover-notify-and-wait dance. This is a
  *stricter* guarantee than the standard `execute()` RED path, independent of whether
  `"instagram_post_via_phone"`/`"youtube_upload_via_phone"` are classified anywhere (they are not
  — same "unclassified but still gated by a different, unconditional mechanism" pattern as
  `request_approval`'s other callers).
- Repo-wide search for every direct caller of `PhoneController`'s write primitives
  (`unlock`/`tap`/`swipe`/`type_text`/`launch_app`): **only `districts/content/phone_poster.py`**
  calls them (`core/api/routers/control.py`'s three phone endpoints and `core/loop/
  autonomous_loop.py`'s observe-tick and `districts/finance/upi_parser.py` all call only
  read-only methods — `is_connected`/`current_app`/`get_notifications`/`take_screenshot`/
  `get_sms_recent` — none require or pass a `control_token`).
- No production code path was found that mints a `"play_music"` token and then passes it to a
  `PhoneController` primitive, or that lets an external caller obtain and redirect a
  `"play_music"`-scoped token to a different controller.

**Classification: VERIFIED GATED** for actual production reachability (the only real caller,
`phone_poster.py`, requires a genuine unconditional owner approval before minting anything).
The `PhoneController._control_action_types` cross-tier mixing (`play_music` alongside RED
entries) remains **UNCERTAIN — latent design weakness, not a demonstrated exploit**, matching
and now more thoroughly confirming Task 57's own prior S1/UNCERTAIN classification. Not
experiment-blocking: no reachable call chain demonstrates the escalation.

## 5. Remaining Subprocess/OS Sweep

Repo-wide search for `subprocess.Popen/run/call/check_call/check_output`, `os.system`,
`os.popen`, `os.startfile`, `shell=True`, `asyncio.create_subprocess_exec/shell` across
production code (excluding tests) found **~230 files** repo-wide, **102 in `core/`+`districts/`
alone** (the vendored `vectorcode/src/` framework — ~130 files — is a separate, largely
CLI/dev-tool-oriented absorbed codebase not reachable via `Governor.dispatch()`'s district-agent
capability-match model; a handful of spot checks, e.g. `core/coding_assistant/`, `core/mcp_tools/`
builtins, confirmed these are Claude-Code-facing developer tooling, not VECTOR's own autonomous
agent capabilities, and were not exhaustively re-audited here per the task's "not a general
audit" scope).

Prioritized the **17 files that are both district agents (`self.capabilities` declared) AND use
a subprocess/os primitive** — this is exactly the reachability class that produced Findings
A/B/C, and is the highest-signal place to look for equivalents:

| File | What it does | Caller-controlled? | Gate? | Classification |
|---|---|---|---|---|
| `districts/investment/finagent_agent.py` | (false positive — only the 58B docstring's prose mentions "subprocess.run"/"subprocess.Popen" as words) | — | 58B gate | VERIFIED GATED |
| `districts/coding/bug_hunter.py`, `code_reviewer.py`, `security_reviewer.py`, `python_reviewer.py` | Regex/AST pattern strings this agent uses to *scan other code* for `os.system`/`eval`/`exec`/`shell=True` — not actual calls in these files themselves | — | N/A | VERIFIED SAFE (false positives) |
| `districts/coding/code_intel_agent.py` | Fixed `node index.js` (a bundled, local JSON-RPC MCP server) with structured JSON-RPC `args` (search/index queries) — no shell, no caller-controlled executable/path | args are caller data, not commands | none needed | VERIFIED SAFE / LOW |
| `districts/coding/git_bot.py` | git operations | mixed | Established `push_github`/`commit_code` RED/YELLOW gate (pre-existing, re-confirmed) | VERIFIED GATED |
| `districts/investment/finagent_agent.py` alias — n/a, see above | | | | |
| `districts/content/video_merger.py`, `voice_generator.py` | Fixed `ffmpeg`/`ffprobe` invocations, local media files | file paths (VECTOR's own generated/downloaded content) | none | VERIFIED SAFE / LOW — fixed executable, no shell, no external network/credential/billing effect, no code execution |
| `districts/learning/video_ingestor.py` | `yt-dlp <url>` — fixed executable, caller-controlled URL | yes (URL) | none | LOW-MEDIUM — network fetch of arbitrary URL is an intended, documented capability ("VideoIngestor (any URL)" per CLAUDE.md); no code execution, no credentials. Not deep-dived further (out of the A/B/C/D risk class: no arbitrary code execution, no billing, no destructive effect). |
| `districts/marketing/ads_orchestrator_agent.py` | `[sys.executable, <fixed script>] + args` — 5 fixed scripts (`analyze_landing.py` etc.), never a caller-controlled `script_name` | `args` (e.g. `output_dir`) are caller-controlled | none | LOW-MEDIUM — no shell=True, no command injection (list-form argv); a caller-controlled `output_dir` could in principle traverse outside the intended output folder for a local file write (image/PDF generation), bounded to what the fixed downstream script does with that path. Not a Finding-A/B/C/D-class bypass (no external side effect, no arbitrary code execution). |
| `districts/ops/devops_automator.py` | `tasklist`/`taskkill` to restart stuck VECTOR services | fixed process names (default list) | **Real `gateway.execute(Action(...))` call, `if approved:` before the kill** | VERIFIED GATED — but the `action_type` used is `"send_message_routine"` (RED, per 2026-08-05 hardening), which is **semantically mismatched** with what's actually being approved (a process kill/restart, not a message send). The Pushover approval notification would literally read "VECTOR wants to: send_message_routine" for a process-restart action. This does not weaken the actual boundary (still real, unconditional RED owner approval, not in `RED_INTERACTIVE_TOOLS`) — a clarity/labeling defect, not a bypass. |
| `districts/qa/evidence_collector.py`, `doc_generator.py`, `reality_checker.py` | `git log`, fixed test-runner scripts (`smoke_test.py`, `integration_check.py`), module-import checks | no | none | VERIFIED SAFE / LOW — read-only diagnostics |
| `districts/security/network_monitor.py` | `netstat`-style connection scan | no | none | VERIFIED SAFE / LOW — read-only |
| `districts/security/incident_playbook_runner.py` | see §11 (dedicated analysis) | see §11 | see §11 | UNCERTAIN — see §11 |
| `districts/karpathy_lab/autoresearch_runner.py` | see §9 (dedicated analysis) | see §9 | **none** | **CONFIRMED BYPASS — Finding D** |

Also spot-checked (not district agents, but autonomously-relevant): `core/loop/cron_jobs.py`
(fixed `compileall`/`git log` — read-only diagnostics, VERIFIED SAFE); `core/loop/
autonomous_loop.py`'s only `PhoneController` usage is read-only (§4).

## 6. Vector Backtest Audit

`districts/investment/backtest_agent.py` (VECTOR's own wrapper agent, re-read fresh in full —
`self.capabilities = ["vt_research", "quant_research", "vt_backtest", "shadow_account",
"vt_swarm", "vt_skills", "vt_export"]`) wraps the vendored `vector_backtest/` package. **Zero
`PermissionGateway` reference exists anywhere in `backtest_agent.py`.**

- `vt_research()`/`vt_swarm()`/`vt_export()` construct a real LangChain-style `AgentLoop`/
  `SwarmRuntime` with `include_shell_tools=self._cfg().get("enable_shell_tools", False)`. Traced
  `vector_backtest/src/tools/bash_tool.py`: it is a genuine arbitrary-shell-command tool
  (`command = kwargs["command"]; subprocess.run(shlex.split(command), ...)`) gated by this exact
  config flag. **Confirmed `core/config.py`'s `"vector_backtest"` section sets
  `"enable_shell_tools": False`** — VERIFIED SAFE for this specific tool, correctly disabled by
  default with no evidence anything flips it on.
- `vt_backtest(strategy_code=...)` is a different, **not similarly gated** path:
  `(run_dir / "signal_engine.py").write_text(strategy_code, encoding="utf-8")` — caller-supplied
  Python written directly to disk — then `bt_main(run_dir)` (`backtest/runner.py`, the vendored
  package's own fixed CLI entrypoint) is called. Traced `runner.py` fresh: it looks for
  `run_dir / "code" / "signal_engine.py"` (note the extra `"code"` subdirectory
  `backtest_agent.py` does **not** create) and dynamically loads it via
  `importlib.util.spec_from_file_location` + `spec.loader.exec_module(module)`, then
  `engine_cls = getattr(signal_module, "SignalEngine"); signal_engine = engine_cls()` —
  **real dynamic Python execution of caller-supplied content.**
  - **Path mismatch bug** (confirmed by direct comparison of the two write/read paths): as
    currently wired, `strategy_code` written by `backtest_agent.py` lands at
    `run_dir/signal_engine.py`, but `runner.py` reads from `run_dir/code/signal_engine.py` — the
    file the caller's code was written to is never the file that gets loaded. `runner.py`'s own
    code fails closed on this (`if not signal_path.exists(): print(error); sys.exit(1)`) — so
    **`strategy_code` injection does not currently reach real code execution**, but only because
    of this unrelated path bug, not because of any deliberate authorization boundary.
  - `runner.py` does have its own defense-in-depth: `_validate_signal_engine_source()` AST-parses
    the file and rejects executable top-level statements, and `safe_run_dir()` whitelists allowed
    run-directory roots against path traversal. **However, `runner.py`'s own comment (read fresh,
    line 388-390) explicitly acknowledges the limitation**: "the AST scrubber below blocks
    executable top-level statements but a method body still runs on instantiation" — i.e. a
    `strategy_code` string shaped as `class SignalEngine:\n    def __init__(self):\n        import
    os; os.system(...)` would pass the top-level-statement check and execute fully once
    `engine_cls()` is instantiated (line 476) or its methods are called during the real backtest
    run (`market_engine.run_backtest(...)`, line 497).
- Owner credentials: not involved (local backtest execution, no external API keys required for
  the core loaders per the module docstring — "Backtest data loaders work without API keys").
  Billing/resource consumption: local CPU only, no evidence of cloud billing.
- Autonomous reachability: `vt_backtest` is a declared capability, reachable via
  `Governor.dispatch()`'s ordinary exact-match capability routing — same mechanism as Findings
  A/B/C/D.

**Classification: UNCERTAIN — high severity, currently blocked by an unrelated path-mismatch
bug, not a demonstrated reachable chain today.** This is architecturally the same class of gap
as Finding D (caller-supplied code, write-to-disk, dynamic-import-and-instantiate, zero
`PermissionGateway`), and the vendored package's own AST scrubber is knowingly incomplete against
method-body payloads even if the path bug were fixed. Recommended as a priority item for a
dedicated follow-up remediation task (§15) — not classified CONFIRMED BYPASS only because the
specific reachable chain traced today does not complete, per this task's explicit evidentiary
bar ("a theoretical issue without a demonstrated reachable chain" is listed as NOT automatically
a blocker) — but flagged as high-risk precisely because an unrelated bug-fix (correcting the
`code/` subdirectory mismatch, an entirely plausible future change) would silently remove the
only thing currently preventing exploitation.

`vt_research`/`vt_swarm`/`vt_export`'s ReAct `AgentLoop`/`SwarmRuntime` default tool registry
(the non-shell tools `build_registry()` includes when `include_shell_tools=False`) was **not**
fully audited for other dangerous primitives (e.g. a code-interpreter or file-write tool) —
UNCERTAIN, out of this task's time budget; noted as a residual limitation (§17).

## 7. Vector MLOps Internal Audit

Task 58C already performed a fresh, direct read of `districts/coding/mlops_agent.py` and
`districts/coding/vector_mlops/agent/tools/jobs_tool.py` this session (not re-derived from
memory here — re-confirmed by re-reading 58C's own documented trace and cross-checking against
the current file state, which is unchanged since that task).

- `districts/coding/vector_mlops/agent/core/tools.py` registers `hf_jobs_handler` (and several
  other tools) into the vendored package's own internal `AgentLoop`/`Session`-based tool registry
  — this is the SAME class of "vendored package's own agent runtime" as `vector_backtest`'s
  `AgentLoop`/`SwarmRuntime`. Repo-wide search for any VECTOR-side code that constructs a real
  `agent.core.session.Session` + drives this `AgentLoop`: **none found**. `mlops_agent.py`'s own
  `ml_research()`/`ml_plan()` methods explicitly avoid it (pre-existing code comments, read fresh
  again this task: "not something safe to fake from outside that loop... A full fix (constructing
  a real Session + AgentLoop) is future work if that deeper capability is actually wanted").
- **Classification: DORMANT / NOT RUNTIME REACHABLE FROM VECTOR** — re-confirmed, not newly
  discovered. Consistent with Task 57's own prior classification of `vector_mlops` internals
  generally.
- All 6 of `MLOpsAgent`'s own actions (`ml_research`, `hf_dataset`, `hf_hub`, `github_ml`,
  `hf_train`, `ml_plan`) were already individually traced in Task 58C; `hf_train` is now RED-gated
  (§3), the other 5 do not reach subprocess/remote-execution primitives (LLM chat calls, dataset
  inspection, HF Hub file list/upload/delete via the `huggingface_hub` library directly, GitHub
  code search). No new finding here beyond re-confirming 58C's own conclusions still hold.

## 8. Capability ↔ Permission Consistency

Extracted all `self.capabilities` string literals declared across `districts/` (excluding
vendored sub-packages) — 782 unique strings — too large to individually cross-reference against
every subprocess call within this task's scope. Focused instead (per the task's explicit "not a
perfect taxonomy" instruction) on the intersection already computed in §5 (agent files that both
declare capabilities AND touch a subprocess/os primitive) — this is the exact reachability class
that produced every one of Findings A/B/C/D. That intersection (17 files) was fully triaged in
§5, with `run_experiment_cycle` (§9) as the one genuine equivalent found, and `vt_backtest`'s
`strategy_code` (§6) and `execute_playbook`'s destructive handlers (§11) as high-severity but
not-currently-demonstrated-reachable uncertainties.

A secondary check specifically searched for the "write caller/LLM-generated content to a `.py`
file, then dynamically import/exec it" signature (`importlib.util.spec_from_file_location`,
`.write_text` targeting `.py` files, bare `exec(`/`eval(`) across `core/`+`districts/`,
excluding already-audited vendored sub-packages. Found: `districts/investment/alpha_zoo/
factors/registry.py` and `__init__.py` use `importlib.util.spec_from_file_location` to
dynamically load alpha-factor modules — traced fresh: `self._py_paths[alpha.id]` is populated
from a fixed, repo-bundled directory of alpha-factor `.py` files at registry-init time, keyed by
a pre-registered `alpha.id`, not from caller-supplied content or an arbitrary path at
request-time. No capability was found that lets a caller add a new alpha-factor file or supply
its own code into this specific loader. **Classification: VERIFIED SAFE** (fixed internal factor
library, no caller-controlled code-injection point found within this task's time budget).

## 9. Finding D — `run_experiment_cycle` (Karpathy autoresearch loop)

**File**: `districts/karpathy_lab/autoresearch_runner.py`
**Class**: `AutoresearchRunner(AgentBase)`
**Capability**: `self.capabilities = ["karpathy_lab", "run_experiment_cycle"]`
**Permission classification**: `"run_experiment_cycle"` is **absent from `core/config.py`'s
`green`/`yellow`/`red` lists entirely** — confirmed via direct grep. Zero `PermissionGateway`
reference exists anywhere in this file.

**Exact call chain**:
```
Governor.dispatch(task_type="run_experiment_cycle")
  -> capability match (self.capabilities includes it) -> agent.run(task)
  -> task_type == "run_experiment_cycle": return await self.run_experiment_cycle()
     -> for i in range(1, MAX_EXPERIMENTS_PER_RUN + 1):   # up to 3 iterations
            proposed_code = self._propose_improvement(best_code, experiments)
              -> asks the local reasoning LLM ("vector-reasoning") to generate
                 a Python architectural change to train.py
            self._train_script.write_text(proposed_code, encoding="utf-8")
              -> REAL FILE WRITE of LLM-generated code, overwriting train.py
            result = self._run_training()
              -> proc = subprocess.run([python_cmd, str(self._train_script)],
                                        cwd=..., timeout=TIME_BUDGET_MINUTES*60+120)
              -> REAL LOCAL SUBPROCESS EXECUTION of the LLM-generated code,
                 no sandbox, no PermissionGateway anywhere in the chain
```

**Permission boundary missing**: none exists. `execute_code` (the codebase's own established RED
action for LLM-generated code) uses `core/sandbox/vector_sandbox.py`'s `VectorSandbox` — subprocess
isolation with timeouts, output truncation, environment filtering, and crucially a real
`PermissionGateway.execute()` RED-tier gate before it runs at all. This path bypasses that
established mechanism entirely: it writes LLM-generated code directly to a real file and executes
it via a raw `subprocess.run()` with no sandbox and no gate.

**Input/control source**: the code executed is LLM-generated (`_propose_improvement()`'s prompt
includes prior experiment `history` — pulled from `episodic memory`/results files — as context),
not directly caller-supplied text, but the LLM call itself is not classified as SENSITIVE-only
(no evidence this specific call is pinned to a fully isolated, un-promptable-by-external-content
model) and the resulting code is executed with no review step of any kind.

**Autonomous reachability**: `Governor.dispatch()`'s exact-match capability routing reaches this
identically to how it reached `launch_terminal`/`hf_train` before their fixes — no dedicated
cron/scheduler trigger was found (repo-wide search for `AutoresearchRunner`/
`run_experiment_cycle` found only this file and its district `__init__.py`), but Governor
dispatch itself is reachable both from ordinary API/chat requests and from the autonomous loop's
own decision-making, matching class 3 ("reachable through Governor routing") and potentially
class 5 ("reachable through LLM-generated autonomous action") of the task's own reachability
taxonomy, per the same mechanism already proven exploitable for Findings A/B/C.

**Severity**: S2-S3 — real local arbitrary-code-execution (bounded to a max ~21 minutes wall-clock
across 3 experiments by the subprocess's own `timeout=` kwarg, and to whatever the local
reasoning LLM produces, but genuinely unsandboxed and ungated). Local only — no external
credentials, no billing, no remote network reach demonstrated in this specific chain — lower
severity than Finding C (`hf_train`, remote+billing) but architecturally identical to Findings B/D
in kind (unsandboxed local execution reachable with zero authorization).

**Why this blocks the 7-day experiment**: it is a confirmed, currently-reachable autonomous path
that can execute unsandboxed, unreviewed, LLM-generated code locally with zero owner
authorization — exactly the class of risk the 7-day autonomous experiment gate exists to rule
out, and exactly the pattern already twice confirmed exploitable this session (Findings B and D
share the same "write generated code, run subprocess, no gate" shape).

**Recommended follow-up**: **Task 58D — Karpathy Autoresearch Permission Remediation.** Gate
`run_experiment_cycle()` behind a real `PermissionGateway.execute()` call before the
write-then-run loop (classify a new or reused RED action_type, e.g. `"run_experiment_cycle"` or
route through the existing `execute_code`/`VectorSandbox` mechanism instead of a raw
`subprocess.run()`), following the same minimal, established pattern used in Tasks 58A/58B/58C.

## 10. 58A/58B/58C Regression Sanity Check

Re-ran the full targeted test suites for all three prior fixes plus the updated Task 57
diagnostic files (`tests/test_task58a_play_music_escalation_remediation.py`,
`tests/test_task58b_finagent_terminal_permission_remediation.py`,
`tests/test_task58c_mlops_hf_train_permission_remediation.py`,
`tests/test_task57_capability_bypass_diagnostic.py`,
`tests/test_task57_device_control_bypass_diagnostic.py`): **56/56 pass, zero failures.** Combined
with the direct source re-confirmation in §3, all three findings remain closed. No regression
detected.

## 11. Incident Playbook Runner — `execute_playbook`'s destructive handlers

**File**: `districts/security/incident_playbook_runner.py`. `capabilities = ["execute_playbook",
"incident", "list_incidents", "list_playbooks", "rollback", "security"]`. Zero `PermissionGateway`
reference anywhere in this file. `"execute_playbook"` is absent from `core/config.py`'s
permission tiers.

`run()`'s `execute_playbook` branch requires an **exact** `task_type == "execute_playbook"` match
plus an explicit, existing `playbook_id` (the code has its own comment explicitly noting free-text
chat dispatch is deliberately never routed here). Once matched, it runs
`execute_playbook(playbook, params.get("evidence", {}), ...)`. Traced the action-handler map:
`kill_process`, `unblock_ip`, `isolate` (which falls back to `evidence.get("pid", 0)`) are real
handlers (`taskkill /F /PID <pid>`, etc.) whose target `pid`/`ip` can come from the **caller-
controlled** `evidence` dict, not only from the YAML playbook's own fixed step params.

**However**: the only packaged playbook file found
(`districts/security/data/playbooks/core_playbooks.yaml`) contains **zero** steps using
`kill_process`/`isolate`/`unblock_ip`/`run_antivirus` — every step across all playbooks in this
file is `log_evidence`, `notify`, `capture_process_snapshot`, or `escalate_to_human` (all
non-destructive). A caller can only select an *existing* `playbook_id` by name; there is no
capability to supply new playbook content, so the destructive handlers cannot be reached with the
current playbook inventory.

**Classification: UNCERTAIN — architecturally ungated, currently not reachable due to an empty
playbook inventory rather than a deliberate boundary.** If the owner (or a future update) ever
adds a playbook whose `kill_process`/`isolate`/`unblock_ip` step relies on `evidence`-sourced
targets, this becomes immediately exploitable with zero owner authorization. Not classified
CONFIRMED BYPASS today per the same evidentiary standard applied to §6 — no demonstrated
reachable chain currently exists. Recommended as a lower-priority proactive follow-up (§15): gate
`execute_playbook` (or specifically its destructive action handlers) behind PermissionGateway
regardless of current playbook content, since the capability itself is the risk, not merely
today's YAML inventory.

## 12. Findings Table

| # | Surface | Classification | Autonomous reachable? | Blocker? |
|---|---|---|---|---|
| D | `autoresearch_runner.py::run_experiment_cycle` | **CONFIRMED BYPASS** | Yes (Governor exact-match, same class as A/B/C) | **YES** |
| — | `backtest_agent.py::vt_backtest(strategy_code=...)` → `runner.py`'s signal_engine dynamic-import | UNCERTAIN (high severity, path-bug-blocked today) | Would be, if path bug fixed | Not today; proactive priority |
| — | `incident_playbook_runner.py::execute_playbook`'s destructive handlers | UNCERTAIN (empty-inventory-blocked today) | Would be, if a matching playbook is added | Not today; proactive priority |
| — | `PhoneController._control_action_types` cross-tier mixing (`play_music` + RED entries) | UNCERTAIN — latent, no reachable chain | No demonstrated path | No |
| — | `devops_automator.py`'s `"send_message_routine"` action_type mismatch for process restart | VERIFIED GATED (clarity defect only) | N/A — real approval still required | No |
| — | `ads_orchestrator_agent.py`'s caller-controlled `output_dir` | LOW-MEDIUM, VERIFIED SAFE for injection, path-traversal-bounded local write only | Governor-reachable | No — no external/destructive effect |
| — | `video_ingestor.py`'s `yt-dlp <url>` | LOW-MEDIUM, intended documented capability | Governor-reachable | No — no code execution/billing |
| — | `vt_research`/`vt_swarm`/`vt_export`'s non-shell ReAct tool registry contents | UNCERTAIN — not fully audited | Governor-reachable | Uncertainty noted, not confirmed |
| — | `vector_mlops/agent/core/tools.py`'s internal AgentLoop tool registry | DORMANT / NOT RUNTIME REACHABLE | No (re-confirmed) | No |
| — | `alpha_zoo` dynamic factor-module loading | VERIFIED SAFE | N/A — fixed internal library, no injection point found | No |
| — | Phone controller real reachability (phone_poster.py's flow) | VERIFIED GATED | N/A | No |
| — | 58A/58B/58C fixes | VERIFIED GATED (regression-confirmed) | N/A | No |
| — | ~85 remaining core/districts subprocess files not individually re-triaged (bug_hunter/code_reviewer/security_reviewer/python_reviewer pattern strings, git_bot, code_intel_agent, video_merger, voice_generator, qa/*, network_monitor, cron_jobs.py — see §5) | VERIFIED SAFE / LOW (spot-checked, no HIGH-risk pattern found) | Mixed | No |
| — | `vectorcode/src/` (~130 subprocess-using files) | Out of scope this task — CLI/dev-tool framework, not part of VECTOR's own Governor/district-agent capability-routing model; not exhaustively re-audited | Presumed not Governor-reachable (spot-checked, not exhaustive) | Not assessed as a blocker; flagged as a scope gap (§17) |

## 13. Uncertainties

- **`vt_backtest`'s `strategy_code` path** (§6): traced the write path, the read path, the AST
  scrubber, and its own acknowledged limitation. Could not establish (without executing real code,
  which this task's rules forbid) whether the AST scrubber would in practice catch every
  method-body attack shape, or whether some other code path reconciles the path mismatch. The
  uncertainty itself is **experiment-relevant** (high severity if the underlying bug is ever
  fixed) even though it does not meet today's "demonstrated reachable" bar.
- **`execute_playbook`'s destructive handlers** (§11): could not establish whether the
  user-writable `playbooks_dir` (`data_path("security","playbooks")`) has ever been populated
  with anything beyond the packaged `core_playbooks.yaml` on the owner's actual machine — this
  task only inspected the packaged/default file. If the owner has authored additional playbooks
  using `kill_process`/`isolate`/`unblock_ip`, this could already be reachable. Not confirmed
  either way within this task's scope.
- **ReAct `AgentLoop`/`SwarmRuntime` default tool registry** (§6): `build_registry()`'s exact set
  of non-shell tools was not enumerated — could not establish whether a code-interpreter or
  file-write tool is included by default. Not experiment-blocking on its own evidence, but not
  ruled out either.
- **`vectorcode/src/`'s ~130 subprocess-using files** (§5/§17): not audited for Governor
  reachability at all — assumed (based on directory purpose and a handful of spot checks) to be
  CLI/dev-tooling outside VECTOR's own capability-routing model, but this was not exhaustively
  verified for every file.

None of these uncertainties are, on their own current evidence, classified as blockers — but the
`vt_backtest` one in particular is flagged as high-priority precisely because "not currently
reachable" is fragile (one plausible bug-fix away from becoming reachable).

## 14. Experiment-Blocker Assessment

```
CONFIRMED AUTONOMOUS SIDE-EFFECT BYPASSES:        1   (Finding D — run_experiment_cycle)
CONFIRMED USER-REACHABLE SIDE-EFFECT BYPASSES:    1   (same finding — also reachable via ordinary
                                                        Governor dispatch, not autonomous-only)
UNCERTAIN AUTONOMOUS SIDE-EFFECT SURFACES:        4   (vt_backtest strategy_code; execute_playbook
                                                        destructive handlers; PhoneController
                                                        cross-tier token scope; ReAct tool registry
                                                        contents)
VERIFIED/GATED SURFACES:                         ~20  (58A/58B/58C fixes re-confirmed; phone
                                                        controller real reachability; devops_
                                                        automator; git_bot; ~15 other spot-checked
                                                        subprocess files; alpha_zoo; vector_mlops
                                                        internals)
NEW 7-DAY EXPERIMENT BLOCKERS:                    1   (Finding D)
```

Applying the task's own rule ("A confirmed autonomous path can cause a consequential side effect
without the intended permission boundary" = BLOCKER; "a theoretical issue without a demonstrated
reachable chain" = NOT automatically a blocker): Finding D meets the BLOCKER bar on direct
evidence (real file write + real subprocess execution + real Governor-reachable capability +
zero gate, fully traced end to end). The two UNCERTAIN high-severity items (§6, §11) do not meet
today's evidentiary bar for a currently-reachable chain, so they are not counted as confirmed
blockers, but are recommended as priority proactive fixes given how fragile their current
non-reachability is.

## 15. Recommended Follow-Up Tasks

1. **Task 58D — Karpathy Autoresearch Permission Remediation** (HIGH priority, required before
   the 7-day experiment): gate `AutoresearchRunner.run_experiment_cycle()`'s write-then-execute
   loop behind a real `PermissionGateway.execute()` call, following the exact 58A/58B/58C pattern.
2. **Task 58E — Vector Backtest Strategy Code Remediation** (HIGH priority, recommended before the
   7-day experiment even though not currently reachable): fix or explicitly document the
   `signal_engine.py` path mismatch, and gate `vt_backtest(strategy_code=...)` behind
   PermissionGateway before any code reaches `bt_main()`'s dynamic import — do not rely on the
   AST scrubber alone (it explicitly does not claim to be a sandbox against method-body payloads).
3. **Task 58F — Incident Playbook Destructive-Action Gate** (MEDIUM priority): gate
   `execute_playbook`'s `kill_process`/`isolate`/`unblock_ip`/`run_antivirus` handlers (or the
   whole `execute_playbook` capability) behind PermissionGateway regardless of current playbook
   content, since the capability's ungated existence — not today's empty inventory — is the real
   risk surface.
4. **Verification-only follow-up**: audit `vectorcode/src/`'s subprocess-using files for any
   Governor-reachable path VECTOR's own district agents could invoke (this task assumed, but did
   not exhaustively verify, that this framework is developer-tooling-only).
5. **Verification-only follow-up**: enumerate `build_registry()`'s default (non-shell) tool set in
   `vector_backtest` to rule out a code-interpreter/file-write tool being reachable via
   `vt_research`/`vt_swarm`/`vt_export` even with `enable_shell_tools=False`.
6. **Verification-only follow-up**: confirm on the owner's actual machine whether
   `data_path("security","playbooks")` (the user-writable playbooks directory) contains anything
   beyond the packaged defaults.

## 16. Test Results

Per the task's explicit rule against creating tests whose only purpose is source-string matching
when a real behavioral test is reasonably possible, and given this is a verification-only task
that must not modify production code: no new diagnostic test file was created for Finding D,
since demonstrating it behaviorally would require either (a) writing a test that exercises the
real, currently-ungated `run_experiment_cycle()` end-to-end — which would itself perform the real
local file-write + real subprocess execution this task's own testing rules explicitly forbid
("never execute real shell commands... zero real side effects"), or (b) mocking the dangerous
primitives, which would only re-demonstrate what source inspection here already conclusively
shows (no gate exists in the source) without adding independent evidence. The exact call chain
(§9) was instead traced directly against current source, matching the same standard already used
for the original Task 57 audit's Findings A/B/C (which were also first established via source
trace before their respective remediation tasks added behavioral tests).

The one testing action taken this task: re-running the existing 58A/58B/58C + Task 57 diagnostic
suites unmodified (§10) — 56/56 pass. No production code, test file, or configuration was
modified.

## 17. Residual Limitations

- `vectorcode/src/`'s ~130 subprocess-using files were not individually audited for Governor
  reachability — a scope assumption (CLI/dev-tooling, not VECTOR's own agent capability model),
  not an exhaustive verification. See recommended follow-up #4.
- ~85 of the 102 core/districts subprocess-using files were not individually deep-traced beyond a
  fast context-grep triage — the 17 files at the intersection of "declares agent capabilities" AND
  "uses a subprocess primitive" received full attention (the highest-signal class, per how
  Findings A/B/C/D were all found); the remainder were spot-checked for obvious HIGH-risk patterns
  (`shell=True`, caller-controlled command strings) and none were found, but this is not the same
  as a full per-file trace.
- `build_registry()`'s exact default (non-shell) tool contents in `vector_backtest` were not
  enumerated (§13).
- Whether the owner's live `data_path("security","playbooks")` directory contains any
  additional, non-packaged playbooks was not checked (§13).
- 782 unique capability strings exist across all district agents; only those intersecting with
  subprocess usage were cross-checked against `core/config.py`'s permission tiers. Capabilities
  that reach OTHER consequential primitives (network calls without subprocess, file deletion,
  external API writes not yet covered) were not systematically cross-checked against permission
  tiers in this task — this remains a general residual, matching Task 57's own acknowledged
  "not an exhaustive audit of every agent's capability list" scope limitation.

## 18. Final Verdict

**59 — NEW BLOCKER(S) FOUND**

One confirmed autonomous permission bypass (Finding D — `districts/karpathy_lab/
autoresearch_runner.py::run_experiment_cycle`) was found and fully traced end to end: a declared,
Governor-reachable capability that writes LLM-generated Python to disk and executes it via a real,
unsandboxed, ungated `subprocess.run()` call, with zero `PermissionGateway` involvement and no
permission-tier classification — architecturally identical to the already-remediated Findings
A/B/C. This must be closed (recommended: Task 58D) before the 7-day autonomous experiment begins.

Two further high-severity, architecturally-identical gaps (`vt_backtest`'s `strategy_code` path
and `execute_playbook`'s destructive handlers) were traced and found currently non-reachable due
to unrelated bugs/empty configuration rather than any deliberate authorization boundary — not
counted as confirmed blockers under this task's evidentiary rule, but flagged as high-priority
proactive fixes (recommended: Tasks 58E, 58F) given how fragile their current non-reachability is.

No production code was modified in this task.
