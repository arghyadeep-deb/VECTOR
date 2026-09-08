# Task 58G — Vector Backtest ReAct Tool-Registry Permission Remediation

## 1. Executive Summary

Task 58E discovered, while tracing every production caller of `vt_backtest`, a separate and more
severe route to the same class of arbitrary-code-execution vulnerability: `BacktestAgent.
vt_research()`/`vt_swarm()`/`vt_export()` construct a real ReAct `AgentLoop` whose tool registry
**unconditionally** includes a `write_file` tool and a `backtest` tool (neither gated by
`enable_shell_tools`), and the `backtest` tool reads from the **correct** path (no accidental
protection) and spawns the real backtest runner as a subprocess. This bypasses Task 58E's
`vt_backtest` gate entirely — it is a different method. This task closes that gap by gating the
one function every real invocation path shares: `districts/investment/vector_backtest/src/tools/
backtest_tool.py`'s `run_backtest()`.

While tracing every caller of that function (as required), a **third** alternate entry point was
found: `districts/investment/vector_backtest/mcp_server.py`, a standalone FastMCP server (`vibe-
trading-mcp` CLI command) exposing its own `backtest` tool that also calls `run_backtest()`.
Confirmed dormant/not-runtime-reachable from VECTOR's own production code, but automatically
covered by this fix regardless, since the gate lives inside the shared function itself.

**58G — FIXED + BEHAVIORALLY VERIFIED.**

## 2. Task 58E Residual Finding

Task 58E §10 (re-read fresh, unchanged): `vt_research()`/`vt_swarm()`/`vt_export()` call
`build_registry(persistent_memory=..., include_shell_tools=cfg.get("enable_shell_tools", False))`.
`_SHELL_TOOL_NAMES = {"bash", "background_run"}` is the only set gated by that flag.
`backtest_tool.py` (`name = "backtest"`) and `write_file_tool.py` (`name = "write_file"`) are both
unconditionally registered. `backtest_tool.py` reads `run_path / "code" / "signal_engine.py"` —
the path `runner.py` actually expects — and spawns `backtest/runner.py` as a real subprocess via
`src.core.runner.Runner.execute()`. `vt_research` is reachable from the real public
`POST /api/investment/research` endpoint; all three methods are Governor-reachable. None of this
passes through `BacktestAgent.vt_backtest()`, and therefore none of it passed through Task 58E's
gate.

## 3. Current ReAct Architecture

Traced fresh this task (not inferred from tool existence alone):

- `build_registry(include_shell_tools=False)` (`src/tools/__init__.py`, re-read in full):
  auto-discovers every `BaseTool` subclass under `src/tools/` via `pkgutil.iter_modules` +
  `BaseTool.__subclasses__()`, instantiates each (`registry.register(cls())`), skipping only
  `cls.name in _SHELL_TOOL_NAMES` when `include_shell_tools=False`. `write_file`/`backtest` are
  neither shell tools nor otherwise conditionally excluded — always present.
- `vt_research()`/`vt_export()` (`backtest_agent.py`) call `build_registry(...)` directly and pass
  the resulting `ToolRegistry` into a real `AgentLoop`.
- `vt_swarm()` calls `SwarmRuntime(...).start_run(preset_name=..., include_shell_tools=...)`.
  Traced `src/swarm/runtime.py` → `_run_worker_with_retries()` → `src/swarm/worker.py`'s
  `run_worker()` (confirmed by reading it fresh): `registry = build_filtered_registry(agent_spec.
  tools, include_shell_tools=include_shell_tools)`. **This registry is built entirely inside
  vendored `swarm/worker.py`, per swarm-preset-agent, and is never exposed back to
  `backtest_agent.py`** — a wrapping approach at the `backtest_agent.py` level (post-hoc replacing
  the tool in a registry `build_registry()` returns to VECTOR's own code) would **not** cover this
  path. This is the specific, concrete reason gating had to happen inside the vendored tool itself
  rather than at a VECTOR-owned wrapper layer (§11).
- `ToolRegistry.execute(name, params)` (`src/agent/tools.py`, re-read in full): a plain
  `self._tools: Dict[str, BaseTool]` lookup, calling `tool.execute(**params)` synchronously and
  catching exceptions into a JSON error envelope. This is the single dispatch point an `AgentLoop`
  uses for every tool call an LLM requests.
- **Tool-call origin**: LLM-generated, via the ReAct loop's own function-calling mechanism —
  `params` for both `write_file` and `backtest` are supplied by the LLM's own tool-call arguments,
  which this task treats as fully untrusted regardless of system-prompt alignment, per the task's
  explicit instruction.
- **Composability, proven not inferred**: `ToolRegistry.execute()` is called once per LLM tool
  call, in a loop, with tool results fed back into the LLM's context for its next decision (the
  standard ReAct pattern this codebase already implements) — nothing in the loop prevents an LLM
  from calling `write_file` for `config.json`, then `write_file` again for
  `code/signal_engine.py`, then `backtest` with a matching `run_dir`, across three separate
  iterations. TEST 4 (§15) behaviorally drives exactly this three-call sequence through the real
  `ToolRegistry.execute()` dispatch to prove the point, not merely assert it.

## 4. Tool Registration Analysis

Confirmed via direct source read: `write_file` and `backtest` register unconditionally through
every construction path this subsystem has — `build_registry()` (used by `vt_research`/
`vt_export`), `build_filtered_registry()` (used by `vt_swarm`'s per-worker registries — itself
calling `build_registry()` internally first, per its own definition: `full = build_registry(
include_shell_tools=include_shell_tools)`), and the standalone `mcp_server.py`'s own registry
construction (§10). No other conditional gate, feature flag, or capability check restricts either
tool's registration anywhere in the traced code.

## 5. write_file Analysis

`write_file_tool.py` (`WriteFileTool.execute(path, content, run_dir)`, re-read in full):
`run_root = safe_run_dir(run_dir)` (whitelists `run_dir`'s root against a fixed list of allowed
directories — `agent_root/runs`, `agent_root/.swarm/runs`, `cwd/runs`,
`home/.vibe-trading/shadow_runs`, plus an env-configurable list); `resolved = safe_path(file_path,
run_root)` (prevents escaping outside that `run_root` — path-traversal protection). Re-read
`path_utils.py`'s `safe_path`/`safe_run_dir` in full: **no extension restriction, no content
restriction, no distinction between code and data.** `path="code/signal_engine.py"` and arbitrary
Python `content` are fully accepted — confirmed both by direct code reading and by TEST 3 (§15),
which writes exactly that path/content combination and confirms it succeeds unmodified. The
answer to the task's own framing question — "can the LLM use it to create executable content in a
location subsequently consumed by the backtest tool?" — is unambiguously **yes**. Path validation
(the only protection present) is a location boundary, not a content/purpose authorization, exactly
as the task anticipated.

## 6. Backtest Tool Analysis

`backtest_tool.py`'s `run_backtest(run_dir)` (pre-fix, re-read in full): `run_path =
safe_run_dir(run_dir)`; reads and JSON-parses `config.json`; validates `source` against a fixed
enum; checks `run_path / "code" / "signal_engine.py"` exists; then (pre-fix) unconditionally
constructs `Runner(timeout=300)` and calls `.execute(entry_script=backtest/runner.py, run_path,
cwd=agent_root, cli_args=[str(run_path)])`. Re-read `src/core/runner.py`'s `Runner.execute()` in
full: `subprocess.run(cmd, cwd=str(effective_cwd), env=env, timeout=self.timeout, ...)` —
**no `shell=True`** (list-form argv, immune to shell-metacharacter injection), but
`env = os.environ.copy()` — **the full parent process environment is inherited**, including
whatever API keys/credentials the main VECTOR process has loaded (a real, non-maximal but genuine
credential-exposure surface for any malicious `signal_engine.py`). Timeout: 300s. Command
construction is entirely from fixed values (`python_cmd`, `entry_script`, `str(run_path)`) —
`run_dir` itself already passed `safe_run_dir()`'s whitelist check by this point. The dangerous
primitive is therefore: a real, unsandboxed, environment-inheriting **child process** running
`backtest/runner.py`, which (§11 of Task 58E, re-confirmed unchanged) dynamically imports and
instantiates whatever class lives in `signal_engine.py` and calls its methods during the real
backtest run. AST filtering, `enable_shell_tools`, and `run_dir` being inside an allowed root were
all explicitly considered and explicitly rejected as substitutes for authorization, per the task's
instruction — none of them constrain what a validly-placed `signal_engine.py` can *contain*.

## 7. Tool-Composition Attack Chain

```
LLM (ReAct reasoning, untrusted tool-call arguments)
  -> write_file(path="config.json", content=<valid config>, run_dir=<LLM-chosen, whitelist-valid>)
  -> write_file(path="code/signal_engine.py", content=<arbitrary Python>, run_dir=<same>)
  -> backtest(run_dir=<same>)
       -> run_backtest(run_dir)
            -> [PRE-FIX] Runner(timeout=300).execute(backtest/runner.py, run_path, ...)
                 -> real subprocess, full env inherited
                 -> _load_module_from_file() dynamic import
                 -> SignalEngine() instantiation + method calls
                 -> ARBITRARY CODE EXECUTION, zero PermissionGateway involvement
```

Behaviorally proven, not merely asserted, by TEST 4 (§15) — the single most important test in
this task's suite.

## 8. Public API Reachability

`core/api/routers/investment.py`'s `POST /research` (re-read fresh): `agent = _get_agent(
"districts.investment.backtest_agent.BacktestAgent"); return await agent.run({"type":
"vt_research", "params": body.model_dump()})`. This reaches `BacktestAgent.run()` →
`vt_research()` → the exact `build_registry()` call traced in §3/§4. TEST 8 (§15) exercises the
identical `build_registry(include_shell_tools=False)` call this endpoint's code path makes and
confirms the `backtest` tool it contains is gated — the closest real integration route available
without standing up a live HTTP server, per the task's own allowance for using "the closest real
router-to-agent integration path available in the existing test architecture."

## 9. Governor Reachability

`core/city/governor.py` (re-confirmed): `"vt_backtest": "investment"` and (from Task 58E's own
trace, unchanged) `vt_research`/`vt_swarm`/`vt_export` are all declared in `BacktestAgent.
capabilities` and reachable via Governor's ordinary exact-match capability routing — same
mechanism already proven exploitable/closed for Findings A–E across this session. TEST 9a (§15)
registers a real `BacktestAgent` and confirms all three task types are in `agent.capabilities`,
then confirms the registry `vt_research`'s own code would build is gated. A full live-LLM
end-to-end Governor→vt_research→real-ReAct-reasoning→tool-call trace was not performed (§17) —
not necessary given the shared function itself is now proven gated regardless of which of these
three methods, or which registry-construction path, reaches it.

## 10. Root Cause

Same class as Findings A–F: a real, consequential local side-effect primitive
(dynamic-import-and-execute) reachable through ordinary tool composition with zero
`PermissionGateway` involvement. Distinct from prior findings in one respect: the vulnerable
composition spans **two independently-reusable, generically-necessary tools** (`write_file`,
`backtest`) rather than one atomic agent method — the vulnerability is in the *combination*, not
in either tool alone, which is why over-gating `write_file` unconditionally was explicitly
rejected (§12) in favor of gating the single point where the combination actually becomes
consequential.

## 11. Remediation Options Considered

**Option B (gate the enclosing capabilities — `vt_research`/`vt_swarm`/`vt_export` themselves)**
was rejected: it would require owner approval for every research query, swarm run, or export —
including ones that never touch `write_file`/`backtest` at all (e.g. "what's AAPL's RSI right
now"). The task explicitly warned against this ("Do not automatically classify vt_research/
vt_swarm/vt_export as RED merely because the AgentLoop contains tools... preserve safe
functionality wherever possible"), and it would not even be more secure than tool-level gating —
it just moves the boundary to a coarser, less accurate place.

**Option A, gate both `write_file` (conditionally, when writing to a code-bearing path) AND
`backtest`**, was considered per the task's own "Possible Safe Design" sketch. Rejected the
`write_file` half specifically: a file written but never executed is inert — no consumer of an
arbitrary `.py` file under a `runs/` tree exists other than `run_backtest()` itself (confirmed via
the alternate-path search, §14) and `BacktestAgent.vt_backtest()`'s own `bt_main()` call (a
*different*, already-58E-gated path). Gating `write_file` unconditionally would break every
harmless use (writing intermediate notes, CSVs, reports, non-code config) — confirmed as real,
common usage by `test_read_and_edit_file_accept_configured_run_root` and this task's own TEST 10.
Gating `write_file` only when it detects a code-shaped path would add a content-sniffing
heuristic with no security benefit once the execution point is gated (§16 confirms the invariant
holds with `write_file` left alone) and real cost in complexity/false-positive risk.

**Chosen: Option A, gate `backtest` only** — specifically, gate the single function
(`run_backtest()`) shared by every real invocation path, rather than each tool/caller
independently. This is smaller, uniform, and — critically, discovered only by tracing rather than
assuming — the *only* choice that correctly covers `vt_swarm`'s internally-built worker registries
(§3) and the newly-found `mcp_server.py`/`shadow_account` paths (§10) without needing to modify
four or more separate call sites.

## 12. Chosen Security Boundary

Gate `districts/investment/vector_backtest/src/tools/backtest_tool.py`'s `run_backtest()`
function itself, immediately after the existing harmless read-only validation (path safety via
`safe_run_dir()`, `config.json` parse, `source` enum check, `signal_engine.py` existence check —
none of these write anything new or execute anything) and immediately before `Runner(timeout=300)`
is constructed. **Why this does not weaken the invariant despite leaving `write_file`
unconditionally available** (the task's own required justification, per its TEST 3 framing): the
write operation alone produces no side effect beyond an inert file on disk; the *only* code path
in the entire traced subsystem — `backtest` tool, `run_shadow_backtest` tool, `mcp_server.py`'s
`backtest` tool, and any direct import — that ever reads and executes `signal_engine.py` is
`run_backtest()` itself, and it is now gated. An attacker who successfully writes a malicious
`signal_engine.py` gains nothing until a *separate*, real, authorized decision approves its
execution.

**Action design**: reused the existing `"vt_backtest"` RED action_type established in Task 58E,
rather than introducing a second one, per the task's explicit "do not blindly create multiple
permission actions if one existing consequential primitive can represent the operation" —
the underlying consequence (a real backtest runner dynamically importing and executing
`signal_engine.py`) is identical regardless of whether it was reached via `BacktestAgent.
vt_backtest()` directly or via the ReAct tool composition. No `core/config.py` change was needed
this task — `"vt_backtest"` is already RED.

## 13. Implementation

One vendored file changed — a deliberate, explicitly-justified deviation from Tasks 58A–58E's
pattern of only touching VECTOR-owned wrapper files, required because `vt_swarm`'s per-worker
registries are constructed entirely inside vendored `src/swarm/worker.py` with no visibility from
`backtest_agent.py` (§3, §11):

**`districts/investment/vector_backtest/src/tools/backtest_tool.py`**: `run_backtest()` rewritten
to, after the existing `signal_path.exists()` check and before constructing `Runner`:
```python
strategy_source = signal_path.read_text(encoding="utf-8", errors="replace")
strategy_digest = hashlib.sha256(strategy_source.encode("utf-8")).hexdigest()[:16]
strategy_preview = strategy_source[:300]

try:
    from core.loop.permission_gateway import PermissionGateway, Action
    gate_result = asyncio.run(PermissionGateway().execute(Action(
        action_type="vt_backtest",
        params={
            "run_dir": str(run_path), "codes": config.get("codes"),
            "engine": config.get("engine"), "source": config.get("source"),
            "has_strategy_code": True,
            "strategy_code_length": len(strategy_source),
            "strategy_code_sha256": strategy_digest,
            "strategy_code_preview": strategy_preview,
            "summary": (f"Execute backtest strategy via the ReAct 'backtest' tool: "
                        f"run_dir={run_path}, engine={config.get('engine')!r}, "
                        f"source={config.get('source')!r} — runs {len(strategy_source)} "
                        f"chars of code (sha256:{strategy_digest}) at code/signal_engine.py, "
                        f"dynamically imported and instantiated by the backtest runner, "
                        f"no sandbox."),
        },
        proposed_by="BacktestTool",
    )))
except Exception as e:
    return json.dumps({"status": "blocked", "reason": f"gateway unavailable: {e}"}, ensure_ascii=False)

if not gate_result.approved:
    return json.dumps({"status": "blocked", "reason": gate_result.reason}, ensure_ascii=False)
```
`import asyncio` and `import hashlib` added at module level (both stdlib, negligible import cost —
verified this does not affect server cold-start behavior, §17). `asyncio.run(...)` bridges to the
async `PermissionGateway` from this synchronous tool method, matching the exact pattern already
established in `mlops_agent.py`'s `hf_train()` — safe here because `run_backtest()` is always
invoked from a thread with no already-running event loop in real usage (`loop.run_in_executor()`
in `vt_research`/`vt_export`; `ThreadPoolExecutor`-style worker threads in `vt_swarm`; a plain
synchronous MCP tool-call handler in `mcp_server.py`). **Full source is deliberately not placed in
`Action.params`** — a length, a truncated SHA-256 digest, and a 300-character preview are used
instead, per the task's own explicit TEST 7 guidance ("A hash/length/safe preview may be
preferable to full source... Do not log arbitrary strategy source unnecessarily") — a deliberate,
documented deviation from Task 58E's own precedent (which did place full `strategy_code` in
`Action.params`, following `execute_code`'s established full-content precedent), justified here by
this task's more specific instruction.

No changes to `write_file_tool.py`, `path_utils.py`, `core/config.py`, `permission_gateway.py`,
`governor.py`, or `backtest_agent.py`.

## 14. Alternate Entry-Point Verification

Repo-wide search (after implementing the fix) for every `import ... run_backtest` statement under
`vector_backtest/` (excluding the definition site and test files) — a precise search for actual
import statements rather than a bare substring match, which over-matches docstrings, an unrelated
`run_backtest_fn` parameter name in `codegen.py`'s docstring, and `SKILL.md` prose (confirmed by
first trying the substring approach and observing exactly these false positives, then correcting
the search — see TEST 11b's own docstring for the full account):

```
src/shadow_account/backtester.py   — _default_run_backtest_fn() imports and returns run_backtest
                                      directly (the "run_shadow_backtest" tool's injection point)
mcp_server.py                      — backtest() tool: `from src.tools.backtest_tool import
                                      run_backtest; return run_backtest(run_dir)`
```

Both behaviorally confirmed gated (TEST 11a, TEST 11c, §15) — **not merely asserted from the
import search**. `mcp_server.py` (`vibe-trading-mcp` CLI command, `main()`'s own docstring: "Entry
point for `vibe-trading-mcp` CLI command") is confirmed **DORMANT / NOT RUNTIME REACHABLE** from
VECTOR's own production code — a repo-wide search found no `core/` or `districts/` file (outside
`vector_backtest`'s own test suite) that imports or launches it; it is a standalone process an
operator would start manually for an external MCP-client integration, entirely outside Governor,
`core/api/routers/investment.py`, and `BacktestAgent`. It is documented here (not silently
ignored, per the task's explicit exception clause for "another alternate entry point to the SAME
... execution primitive") and is automatically covered by this fix regardless of its own
reachability status, since the gate lives in the one function both paths share — a direct benefit
of choosing the source-level boundary (§11/§12) over a per-caller wrapping approach.

No other production caller of `Runner.execute`, `backtest/runner.py`, or `bt_main` was found
beyond `backtest_tool.py` itself and `BacktestAgent.vt_backtest()`'s own, separate, already-58E-
gated `bt_main()` call.

## 15. Behavioral Tests

New file: `tests/test_task58g_vector_backtest_react_tool_permission_remediation.py` — 15 tests,
all exercising the REAL `PermissionGateway.execute()`, the REAL `ToolRegistry.execute()` dispatch,
and (where applicable) the REAL `Governor`/`build_registry()`/`BacktestAgent`, with only `src.core.
runner.Runner.execute` (the actual subprocess primitive) and `PermissionGateway`'s human-
notification boundary (`_notify`/`_wait_for_confirmation`) replaced. Every test sets
`VIBE_TRADING_ALLOWED_RUN_ROOTS` to an isolated pytest `tmp_path`, matching the vendored package's
own established test pattern (`tests/test_path_safety.py`, `tests/test_file_tool_sandbox_
security.py`) — never a real repo path or `~/.vibe-trading/`.

| # | Test(s) | What it proves |
|---|---|---|
| 1 | `test_1_shell_flag_disabled_does_not_prevent_the_tool_composition_reaching_the_gate` | `enable_shell_tools=False` correctly excludes `bash`/`background_run` but does NOT create false safety — `write_file`/`backtest` remain present and `backtest` still reaches the real gate. |
| 2 | `test_2_unauthorized_backtest_blocked` | Direct `run_backtest()` call, unapproved: blocked, zero `Runner.execute` calls. |
| 3 | `test_3_write_file_of_executable_strategy_is_not_gated_but_stays_inert_without_approval` | `write_file` succeeds unmodified (the deliberate design choice, §12) and provably cannot itself trigger any execution (no `Runner` reference in `write_file_tool.py` at all). |
| 4 | `test_4_composition_attack_write_file_then_backtest_without_approval_cannot_execute` | **THE MOST IMPORTANT TEST.** Drives the exact 3-call ReAct sequence (write config.json, write signal_engine.py, call backtest) through the real `ToolRegistry.execute()` dispatch with no approval — the writes succeed, the composed attack is blocked at the execution step, zero real subprocess calls. |
| 5 | `test_5_approved_execution_reaches_mocked_runner` | Approved call reaches the real (mocked) `Runner.execute`, with the correct `run_dir`. |
| 6 | `test_6_gateway_exception_fails_closed` | A raised gateway exception fails closed — no execution. |
| 7 | `test_7_action_content_correct_and_no_unnecessary_source_exposure` | Real `Action` has `action_type="vt_backtest"`, `proposed_by="BacktestTool"`, correct `codes`/`engine`/`source`/`has_strategy_code`/`strategy_code_length`/`strategy_code_sha256` values, a descriptive `summary` — and explicitly confirms full `strategy_code` source is NOT placed in params, and no credential-shaped keys exist. |
| 8 | `test_8_vt_research_agent_run_cannot_reach_unauthorized_backtest_execution` | The closest real route to `POST /api/investment/research` available without a live HTTP server: the exact `build_registry(include_shell_tools=False)` call `vt_research()` makes, confirmed to contain a gated `backtest` tool. |
| 9 | `test_9a_governor_dispatch_vt_research_registry_contains_gated_backtest` | Confirms `vt_research`/`vt_swarm`/`vt_export` are all declared `BacktestAgent` capabilities (Governor-reachable) and that the registry construction they use is gated. |
| 10 | `test_10_harmless_read_only_tools_unaffected` | No regression: `write_file` for ordinary notes and `read_file` continue to work exactly as before; `read_file`'s `is_readonly` flag unaffected. |
| 11 | `test_11a_run_shadow_backtest_tool_reaches_the_same_gate`, `test_11b_only_the_two_known_importers_of_run_backtest_exist`, `test_11c_dormant_mcp_server_backtest_tool_is_also_gated` | Confirms `shadow_account/backtester.py`'s injection point resolves to the identical gated function and is blocked identically; a precise repo-wide import search finds exactly two importers, both accounted for; the newly-discovered dormant `mcp_server.py` path is behaviorally confirmed gated too. |
| 12 | `test_12a_run_backtest_source_has_no_self_mint_and_gates_before_side_effect`, `test_12b_vt_backtest_action_type_reused_and_still_red` | Source inspection: no `grant_control`; gate call/approval-check precede `Runner` construction in source order; `"vt_backtest"` confirmed still RED. |

## 16. Composition-Attack Verification

TEST 4 (§15) is the direct, explicit answer to the task's central question: "can an LLM still
achieve arbitrary Python execution through another sequence of tools or another direct path?" —
driven through the real `ToolRegistry.execute()` dispatch (the same mechanism a real `AgentLoop`
uses for every LLM tool call), with `write_file` deliberately left fully functional (proving the
"write" half of the invariant isn't secretly broken to make the test trivially pass) and only the
`backtest` step's real subprocess mocked. The answer, behaviorally confirmed: **no** — the
composed sequence writes both artifacts successfully and is blocked exactly at the point where
execution would occur, with zero calls to the mocked `Runner.execute`.

## 17. Regression Results

**Targeted**: 15/15 pass; 9 dangerous-path tests individually isolated (`pytest path::test_name`),
each `exit=0`.

**Relevant, first combined run**: the same 4 pre-existing, already-root-caused-in-prior-tasks
failures (`test_regression_governor_capability_routing.py`'s 2 embedding-drift tests, `test_
permission_gateway.py`'s `pending_id` signature drift, `test_phase_a7_council_red_tier.py`'s empty
`COUNCIL_AUTO_PROCEED_ALLOWED` test) **plus one additional failure**,
`districts/investment/vector_backtest/tests/test_mcp_server_smoke.py::test_mcp_server_happy_path`
(`AssertionError: initialize did not respond within 30.0s`). Investigated rather than dismissed:

1. Reproduced in isolation: **failed** the first run.
2. Re-ran immediately after, identical command, no code changes: **passed** (25.66s total).
3. The test's own module docstring documents its timeout as "Generous bound — covers cold imports
   of fastmcp + tool registry build on slow CI runners. The patched server typically finishes
   initialize in 3-9s" — i.e. a 30s ceiling around a normal 3-9s operation, spawning a real Python
   subprocess that cold-imports `fastmcp` + the full ~22-tool registry.
4. This task's own code change adds two stdlib imports (`asyncio`, `hashlib`) at
   `backtest_tool.py`'s module level (negligible cost) and one heavy import
   (`core.loop.permission_gateway`) **inside** `run_backtest()`'s function body — not triggered by
   module import or by `mcp_server.main()`'s registry pre-warm (`_get_registry()`, which
   instantiates tool objects but never calls `run_backtest()`), so there is no plausible mechanism
   by which this change affects server *startup* time specifically (the `initialize` handshake
   happens before any tool is ever called).

This is a **non-deterministic, cold-subprocess-spawn timing flake** (confirmed by direct
reproduction of both the failing and passing outcome from the identical test with no code changes
between runs), not a regression. Not counted as a new deterministic failure, consistent with the
identical evidentiary standard already applied to `test_openwa_absorption.py` (Task 58B) and
`test_trust_ladder.py::test_explicit_rejection_feeds_ladder` (Task 58E).

**Relevant test suite** (`tests/test_task58g_...` 15, `tests/test_task58e_...` 13,
`tests/test_task58a_...` 12, `tests/test_task58b_...` 16, `tests/test_task58c_...` 16,
`tests/test_task58d_...` 10, `tests/test_task57_capability_bypass_diagnostic.py` 6,
`tests/test_task57_device_control_bypass_diagnostic.py` 4, Governor/PermissionGateway/trust-ladder
suites, `tests/test_karpathy_lab_run_wiring.py`, and the vendored `test_backtest_runner_security.
py` (3), `test_tool_registry_security.py` (2), `test_registry.py` (15), `test_shadow_account.py`
(28), `test_shadow_codegen_security.py` (1), `test_file_tool_sandbox_security.py` (3), `test_path_
safety.py` (17), `test_mcp_regression.py`, `test_mcp_server_smoke.py`): all pass except the 4
pre-existing failures and the one confirmed non-deterministic flake documented above.

**Full tracked baseline** (`tests/unit` + `tests/integration`, excluding `test_planning.py`'s 2
independently pre-existing broken tests): **8 failed / 0 errors / 29 skipped — exact same 8
failing test names, exact match to the documented baseline**
(`2212 collected / 2175 passed / 8 failed / 0 errors / 29 skipped`). Zero new failures in the
tracked scope.

**Static/lint/type checks**: `ruff` and `mypy` are **not available** in this environment
(`command not found`) — same as every prior task this session. `py_compile` on the modified
vendored file succeeds cleanly; the vendored package's own related test suites (49 tests across
`test_backtest_runner_security.py`, `test_tool_registry_security.py`, `test_registry.py`, `test_
shadow_account.py`, `test_shadow_codegen_security.py`) all pass unmodified.

## 18. Side-Effect Hygiene

Before and after all dangerous-path test runs: `~/.vector/vector_backtest/runs/` inspected —
empty, no leaked run directories. `~/.vibe-trading/` inspected — contains only pre-existing
application state (`fonts`, `memory`, `sessions.db`, `shadow_accounts`), no new or recently-
modified artifacts attributable to this task's tests. `git status --short` shows only this task's
own legitimate changes: `districts/investment/vector_backtest/src/tools/backtest_tool.py`
(modified) and `tests/test_task58g_vector_backtest_react_tool_permission_remediation.py` (new) —
the working tree's many other pre-existing uncommitted files (confirmed unrelated, present before
this task started, consistent with this being a live, actively-developed repository) are excluded
from this accounting per the task's own instruction not to treat pre-existing unrelated
uncommitted work as a regression. No test created a persistent strategy file, created a git
branch, launched a real subprocess, contacted an external service, consumed real credentials, or
consumed cloud resources — the only subprocess-shaped primitive in this subsystem
(`Runner.execute`) was mocked in every dangerous-path test; the two tests that do NOT mock it
(§15 TEST 1's registry-shape check, TEST 10) never reach the `backtest` tool at all.

## 19. Residual Limitations

- A full end-to-end test driving a real (or fully internally-mocked) LLM ReAct reasoning loop
  through `vt_research()`/`vt_swarm()`/`vt_export()` themselves — rather than directly exercising
  the shared `run_backtest()` gate and the exact registry-construction calls these methods make —
  was not performed (§9, §17). This was a deliberate scope/cost decision: the underlying
  mechanism is now proven gated regardless of which of the three methods reaches it, and a full
  ReAct-loop integration test would require either real (slow, non-deterministic) LLM calls or an
  extensive mock of the loop's own internal reasoning, disproportionate to what the composition
  test (TEST 4) and registry-shape tests (TEST 1, 8, 9a) already establish together.
- `vt_swarm`'s actual `SwarmRuntime`/`run_worker()` execution path was traced by direct source
  reading (§3) to confirm it calls `build_filtered_registry()`, but was not itself driven
  end-to-end in a test (would require constructing a full swarm preset run) — the underlying gate
  it would reach is the same `run_backtest()` function already behaviorally proven gated.
- `mcp_server.py`'s dormancy (§14) was confirmed by a repo-wide search for importers/launchers
  within `core/`/`districts/` — not by proving no *external* tool (e.g. a Claude Desktop MCP
  config on the owner's machine) is configured to launch `vibe-trading-mcp` as a standalone
  process. If such a configuration exists, this task's fix already covers it (§14), so this
  limitation does not affect the security conclusion, only its "not runtime reachable from VECTOR"
  characterization.
- This task did not modify or investigate Task 59's other flagged items (Task 58F's incident-
  playbook handlers, `PhoneController`'s shared token scope, the remaining `vectorcode`/`vector_
  mlops` surfaces) — those remain open per Task 59's own recommendations.
- No other issue outside the vector_backtest ReAct/write-file/backtest execution primitive was
  discovered during this task.

## 20. Final Status

All required conditions for FIXED + BEHAVIORALLY VERIFIED are satisfied:

- [x] The ReAct backtest/write composition is secured (§7, §16 — TEST 4 directly proves it)
- [x] The real `PermissionGateway` is used (not a mock, not a second framework, §13)
- [x] Unauthorized execution fails closed (§15 TEST 2, TEST 4)
- [x] Gateway errors fail closed (§15 TEST 6)
- [x] LLM-generated tool arguments are treated as untrusted (§3 — no alignment assumption made
      anywhere in the design)
- [x] Public API reachability is accounted for (§8, §15 TEST 8)
- [x] Governor reachability is accounted for (§9, §15 TEST 9a)
- [x] Alternate relevant execution paths cannot bypass the boundary (§10, §14 — `run_shadow_
      backtest` and `mcp_server.py` both confirmed gated, §15 TEST 11a/11c)
- [x] No self-mint exists (§15 TEST 12a)
- [x] Behavioral composition tests pass (§15, §16)
- [x] No arbitrary Python was executed during testing (§15's mocking strategy, §18)
- [x] No dangerous real subprocess was launched (§18)
- [x] No leaked artifacts remain (§18)
- [x] Regression baseline has no new deterministic failures (§17 — one confirmed non-deterministic
      flake, unrelated to this change; full tracked baseline identical)

Final trace (S0 not implemented … S5 behaviorally verified) for each scoped path:

| Path | entry | AgentLoop | tool registry | write_file/backtest | permission boundary | approval/rejection | persistence | runner | dynamic import | strategy execution |
|---|---|---|---|---|---|---|---|---|---|---|
| `POST /api/investment/research` | S3 | S3 | S3 | S3 (both present) | **S5** | **S5** | S3 (write_file, inert alone) | not reached unless approved | not reached unless approved | not reached unless approved |
| `Governor -> vt_research` | S3 | S3 | S3 | S3 | **S5** | **S5** | S3 | not reached unless approved | not reached unless approved | not reached unless approved |
| `Governor -> vt_swarm` | S3 | S2 (traced, not driven end-to-end) | S3 (via build_filtered_registry) | S3 | **S4/S5** (shared function TEST-verified; full worker path not separately driven) | S4/S5 | S3 | not reached unless approved | not reached unless approved | not reached unless approved |
| `Governor -> vt_export` | S3 | S2 (traced, not driven end-to-end) | S3 | S3 | **S4/S5** (shared function) | S4/S5 | S3 | not reached unless approved | not reached unless approved | not reached unless approved |

The dangerous path has no S3→S5 execution route without authorization on any of the four scoped
entry points.

**58G — FIXED + BEHAVIORALLY VERIFIED**

Per the task's explicit stop condition: not proceeding to Task 58F or the 7-day experiment. The
next decision is deferred to a review of this artifact.
