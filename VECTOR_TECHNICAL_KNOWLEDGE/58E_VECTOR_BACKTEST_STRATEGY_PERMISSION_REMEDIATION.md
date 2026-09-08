# Task 58E — Vector Backtest Strategy-Code Permission Remediation

## 1. Executive Summary

Task 59 traced `districts/investment/backtest_agent.py`'s `vt_backtest(strategy_code=...)` and
found a real, ungated, Governor-reachable path that writes caller-supplied Python to disk and
invokes the vendored `vector_backtest` runner's dynamic-import mechanism — currently non-functional
only because of an unrelated path mismatch, which Task 59 explicitly warned "MUST NOT be treated
as a security boundary." This task closes that gap: `BacktestAgent.vt_backtest()` now gates
**unconditionally** (not only when `strategy_code` is supplied) through a real
`PermissionGateway.execute(Action(...))` call before any strategy-code write or backtest
invocation, following the identical minimal pattern proven in Tasks 58A–58D. The path mismatch
itself was deliberately **not** repaired (see §6/§11) — the gate is designed and tested to remain
correct and sufficient regardless of that mismatch's status.

**A separate, more severe alternate route to the same dangerous execution primitive was
discovered during this task** — `BacktestAgent.vt_research()`/`vt_swarm()`/`vt_export()`'s ReAct
`AgentLoop` unconditionally registers a `write_file` tool and a path-correct `backtest` tool
(neither gated by `enable_shell_tools`), reachable from a real public API endpoint
(`POST /api/investment/research`). This is **outside `vt_backtest`'s scope** per this task's
explicit instructions and was **not fixed** — documented in §10 as a residual finding with a
recommended follow-up task, per the task's "STOP, document, don't expand scope" instruction.

**58E — FIXED + BEHAVIORALLY VERIFIED** (for `vt_backtest` specifically — see §10/§15 for the
scope boundary of that claim).

## 2. Task 59 Finding

Task 59 (§6, "Vector Backtest Audit") found: `BacktestAgent.vt_backtest(strategy_code=...)`
writes caller-supplied Python to `run_dir/signal_engine.py`; the vendored `backtest/runner.py`
reads from `run_dir/code/signal_engine.py` (a path the agent never creates) and would, if that
mismatch didn't exist, dynamically import and instantiate that code via
`importlib.util.spec_from_file_location` + `spec.loader.exec_module()` +
`getattr(module, "SignalEngine")()`. Zero `PermissionGateway` reference existed anywhere in
`backtest_agent.py`. The vendored runner's own AST scrubber (`_validate_signal_engine_source()`)
explicitly only rejects top-level executable statements — its own code comment (re-read fresh
this task, unchanged) acknowledges "a method body still runs on instantiation."

## 3. Pre-Fix Call Chain

Re-traced fresh this task (not trusted from Task 59's description) by re-reading
`districts/investment/backtest_agent.py` and `districts/investment/vector_backtest/backtest/
runner.py` in full — both confirmed unchanged since Task 59:

```
Governor.dispatch(task_type="vt_backtest")
  -> capability match (self.capabilities includes "vt_backtest") -> agent.run(task)
  -> task_type == "vt_backtest": return await self.vt_backtest(codes=..., strategy_code=p.get("strategy_code"), ...)
     -> [PRE-FIX] def _run():
            from backtest.runner import main as bt_main, BacktestConfigSchema
            run_dir = self._runs_dir() / f"bt_{uuid.uuid4().hex[:8]}"   # fresh dir every call
            run_dir.mkdir(...)
            (run_dir / "config.json").write_text(...)                   # REAL FILE WRITE (harmless — config only)
            if strategy_code:
                (run_dir / "signal_engine.py").write_text(strategy_code, ...)  # REAL FILE WRITE of caller code
            bt_main(run_dir)                                            # reads run_dir/code/signal_engine.py — NOT FOUND today
        result = await loop.run_in_executor(None, _run)
```

Inside `bt_main()` (`runner.py`, re-read fresh): `signal_path = run_dir / "code" / "signal_engine.py";
if not signal_path.exists(): print(error); sys.exit(1)` — confirmed this branch still fires with
the current, unmodified `backtest_agent.py` write path, so `bt_main()` currently exits before ever
reaching `_load_module_from_file()`/`engine_cls()`. `run()`'s dispatch table:
`elif task_type == "vt_backtest": return await self.vt_backtest(codes=p.get("codes", p.get("tickers", ["AAPL"])), ..., strategy_code=p.get("strategy_code"), ...)` — unconditional, no gate.

## 4. Root Cause

Same class as Findings A/B/C/D: a district-agent capability Governor's ordinary exact-match
routing can reach directly performs a real, consequential local side effect (persist caller-
supplied code to disk, invoke a mechanism that dynamically imports and instantiates it) with no
authorization boundary anywhere in the call chain. The vendored runner's AST scrubber and the
accidental path mismatch are the only things standing between an unapproved call and real code
execution — neither is an authorization mechanism.

## 5. Strategy-Code Origin Analysis

Traced how `strategy_code` reaches `vt_backtest()`, per the task's explicit requirement not to
assume its source:

- **`run()`'s dispatch**: `p.get("strategy_code")` where `p = task.get("params", task)` —
  whatever the caller's `task` dict contains. This is the path both Governor-routed and directly-
  shaped calls use.
- **Governor exact-match / LLM-classified routing**: Governor does not itself construct or
  validate `strategy_code` — it passes the caller's original `task` dict through unmodified to
  `agent.run(task)`. A `task_type="vt_backtest"` request with an LLM-classified marker
  (`task["_llm_classified"]`) could originate from `classify_chat_intent()`'s free-text chat
  classification (`core/city/governor.py`), meaning `strategy_code` could, in principle, be
  populated from an LLM's own interpretation of a chat message if the LLM happened to invent that
  exact parameter name and content — not the primary expected path, but not ruled out either.
- **Direct agent-to-agent or planner call**: no production code was found (repo-wide search, §10)
  that constructs a `vt_backtest` task with `strategy_code` programmatically — the parameter exists
  purely as a caller-supplied string; VECTOR's own code never generates one internally.
- **`vt_export(strategy_code=...)`**: a *different* method on the same agent accepts a
  `strategy_code` parameter too, but forwards it as **prompt text** into the ReAct `AgentLoop`
  (`f"Load the {skill} skill and convert this strategy to {target} format:\n\n{strategy_code}"`)
  — it does not call `vt_backtest()` or write to `signal_engine.py` at all, so it is not part of
  this specific finding's chain (though see §10's residual finding about the ReAct loop's own
  tool registry).
- **No autonomous/scheduled trigger**: repo-wide search (§10) found no cron, scheduler, or
  autonomous-loop direct caller of `vt_backtest`/`BacktestAgent`.

**Conclusion**: `strategy_code` is ordinary, untrusted caller input at the `vt_backtest()`
boundary — it must be treated as attacker/LLM-controlled regardless of which specific upstream
caller supplied it, consistent with how Findings A/B/C/D were all remediated.

## 6. Path-Mismatch Analysis

Confirmed, byte-for-byte, this task: `backtest_agent.py`'s `_run()` writes to
`run_dir / "signal_engine.py"`; `runner.py`'s `main()` reads from
`run_dir / "code" / "signal_engine.py"`. These are different paths — the mismatch is real and
unchanged since Task 59.

**Decision: this task does NOT fix the path mismatch.** Reasoning:

- The task's own instructions lead with "Do NOT automatically repair the path mismatch" as the
  first, most prominent directive in that section — repairing it is only conditionally sanctioned
  ("if fixing it is necessary to preserve intended functionality after authorization").
- It is **not necessary** to satisfy this task's actual security objective. The required
  invariant — "an unapproved `vt_backtest` cannot execute caller/LLM-supplied strategy code" — is
  fully satisfied by gating the method regardless of whether the mismatch exists: an unapproved
  call never reaches the write or `bt_main()` call at all, so the mismatch's presence or absence
  is irrelevant to that guarantee.
- Fixing it would make this task's own change the thing that, for the first time, turns a
  currently-inert (broken) execution primitive into a genuinely working one. That is a much larger
  and riskier change than "add a permission gate" and edges into "redesign the backtest engine,"
  which the task explicitly forbids. A security remediation task making a dangerous capability
  newly functional, as a side effect, is backwards from its own mandate.
- The task explicitly asked for a diagnostic test proving the gate holds even if the mismatch
  were corrected (§12, TEST 9) — satisfying that requirement gives the same assurance a real fix
  would, without taking on the redesign risk.

This is a **documented, deliberate scope decision**, not an oversight — flagged again in §11/§15.

## 7. Remediation Design

Reused the exact `Action`/`PermissionGateway.execute()` pattern already established and proven in
Tasks 58A–58D — re-confirmed fresh this task by re-reading `districts/investment/finagent_agent.py`
(58B) and `districts/coding/mlops_agent.py` (58C) as the closest precedents (both gate a single
entry-point method fully, before any real side effect, using the agent's own
`self._gateway = PermissionGateway()`). No dedicated RED action already exists that semantically
represents "execute arbitrary strategy code in a backtest" — `execute_code` is the closest
existing RED action but is architecturally tied to `VectorSandbox`'s specific
`run_code_safe(code, timeout)` interface (a bare code string, no `run_dir`/config/multi-file
concept), and forcing `vt_backtest`'s very different execution shape (persisted files, a separate
process invocation, engine/data-loading parameters) through that specific mechanism would be a
redesign, not a reuse — so a new, dedicated `"vt_backtest"` action_type was added instead,
matching the same choice already made for `"launch_terminal"`, `"hf_train"`, and
`"run_experiment_cycle"` in the three prior tasks.

**Gate scope — unconditional, not only when `strategy_code` is truthy.** Investigated whether
`vt_backtest()` has any safe, non-consequential invocation shape that could reasonably be left
ungated (per the task's explicit "determine whether the current architecture actually needs to
execute caller-supplied Python" instruction). Re-read `runner.py`'s `main()` fresh: it
**unconditionally** requires `run_dir/code/signal_engine.py` to exist — there is no default or
fallback signal engine anywhere in the traced code, and every call gets a **fresh**
`uuid.uuid4()`-named `run_dir` (confirmed: no reuse of a prior run's directory is possible), so a
`strategy_code`-less call can never accidentally pick up a leftover file from an earlier approved
run either. In the current architecture, every functional invocation of `vt_backtest()` — with or
without an explicit `strategy_code` argument this call — depends on strategy code reaching that
path one way or another for the backtest to do anything at all; a `strategy_code=None` call is,
today, a guaranteed no-op/failure (confirmed via runner.py's early exit), not a distinct "safe
default backtest" mode. Given that, and matching the simplicity of the established one-gate-per-
method pattern, the gate applies to the whole method unconditionally.

## 8. Permission Classification

`"vt_backtest"` added to `core/config.py`'s `PermissionConfig.red` list. RED because caller-
supplied Python may be dynamically imported and executed with **no genuine sandbox** — the AST
scrubber, the path mismatch, the fixed working directory, local-only execution, and the absence
of cloud credentials were all explicitly considered and explicitly rejected as substitutes for
authorization, per the task's own instruction. Not classified GREEN merely because it is "a
backtest." Not added to `RED_INTERACTIVE_TOOLS`: confirmed via the alternate-entry-point audit
(§10) that nothing routes an owner-typed/spoken command directly to this action_type.

## 9. Implementation

Two files changed:

**`core/config.py`**: added `"vt_backtest"` to `PermissionConfig.red`, with an inline comment
matching the established 58B/58C/58D comment style, explicitly noting the unconditional-gate
rationale from §7.

**`districts/investment/backtest_agent.py`**:
- Added `from core.loop.permission_gateway import PermissionGateway, Action`.
- Added `self._gateway = PermissionGateway()` to `__init__`.
- `vt_backtest()` rewritten: immediately after the existing log line and before the (otherwise
  byte-for-byte unchanged) `_run()` closure definition, added
  ```python
  try:
      gate_result = await self._gateway.execute(Action(
          action_type="vt_backtest",
          params={
              "codes": codes, "start_date": start_date, "end_date": end_date,
              "source": source, "engine": engine, "interval": interval,
              "has_strategy_code": bool(strategy_code),
              "strategy_code": strategy_code or "",
              "summary": (
                  f"Run backtest engine={engine!r} source={source!r} on {codes} "
                  f"({start_date}..{end_date})" +
                  (f" — executes {len(strategy_code)} chars of caller-supplied "
                   f"Python as the trading signal engine (dynamically imported "
                   f"and instantiated by the backtest runner, no sandbox)."
                   if strategy_code else
                   " — no caller-supplied strategy code for this call.")
              ),
          },
          proposed_by=self.name,
      ))
  except Exception as e:
      logger.error(...); return {"status": "blocked", "reason": f"gateway unavailable: {e}"}
  if not gate_result.approved:
      logger.warning(...); return {"status": "blocked", "reason": gate_result.reason}
  ```

No changes to `permission_gateway.py`, `governor.py`, `vector_sandbox.py`, the vendored
`vector_backtest/` package, or any other file.

## 10. Alternate Entry-Point Analysis

Repo-wide search (after implementing the fix) for every production reference to `vt_backtest`,
`BacktestAgent`, `runner.py`/`bt_main()`, the strategy-code write operation, and dynamic
`signal_engine` loading:

```
core/api/routers/investment.py   — POST /research -> agent.run({"type": "vt_research", ...})
                                    GET  /research/skills -> agent.run({"type": "list_skills", ...})
                                    (NEITHER calls task_type="vt_backtest" directly)
core/city/governor.py            — "vt_backtest": "investment" (district-hint map entry, not a caller)
core/config.py                   — the new permission-tier entry + its comment (not a caller)
districts/investment/vector_backtest/__init__.py  — docstring listing capability names (not code)
districts/investment/__init__.py — `"BacktestAgent"` module export (not a caller)
```

**No production caller invokes `task_type="vt_backtest"` other than through
`Governor.dispatch()`'s ordinary capability-match, a direct `BacktestAgent().vt_backtest(...)`
call, or `BacktestAgent.run()`'s own dispatch table** — all three funnel through the single,
now-gated `vt_backtest()` method (behaviorally confirmed, §12 TEST 6/7). **No alternate entry
point bypasses this specific gate.**

**CONFIRMED, SEPARATE finding — outside `vt_backtest`'s scope, NOT fixed by this task.** While
tracing `core/api/routers/investment.py`'s two real endpoints, found that `POST /research`
(`vt_research()`) — and, by the same mechanism, `vt_swarm()`/`vt_export()` — construct a real
ReAct `AgentLoop` via `build_registry(persistent_memory=..., include_shell_tools=cfg.get(
"enable_shell_tools", False))`. Re-read `districts/investment/vector_backtest/src/tools/__init__.py`
fresh: `_SHELL_TOOL_NAMES = {"bash", "background_run"}` is the **only** set gated by
`include_shell_tools`. `districts/investment/vector_backtest/src/tools/backtest_tool.py`
(`name = "backtest"`) and `write_file_tool.py` (`name = "write_file"`) are **both unconditionally
registered** regardless of that flag. `backtest_tool.py`'s `run_backtest(run_dir)` reads from
`run_path / "code" / "signal_engine.py"` — the **correct** path (no mismatch) — and spawns
`backtest/runner.py` as a real subprocess (`src.core.runner.Runner(timeout=300).execute(...)`) if
that file exists. This means: an LLM driving `vt_research()`/`vt_swarm()`/`vt_export()` — reachable
from the real, public `POST /api/investment/research` endpoint, or via `Governor.dispatch()`'s
same capability-match mechanism for `vt_research`/`vt_swarm`/`vt_export` — could use its own
always-available `write_file` tool to place a `code/signal_engine.py` (and a `config.json`) into
some `run_dir`, then call its own always-available `backtest` tool with that `run_dir`, reaching
**real, path-correct, subprocess-executed arbitrary code**, entirely bypassing
`BacktestAgent.vt_backtest()` — and therefore this task's new gate — completely. This was not a
contrived edge case constructed to find a bypass; it surfaced directly while tracing "every
production caller" as instructed. Per the task's explicit "if you discover another security issue
outside vt_backtest: STOP... document... recommend a separate task... do not silently expand
scope" instruction, this is **not fixed here**. **Recommended follow-up: Task 58G — Vector
Backtest ReAct Tool-Registry Permission Remediation** (gate `vt_research`/`vt_swarm`/`vt_export`
themselves, and/or gate the `backtest`/`write_file` tools specifically within the vendored
registry, before either can reach a real file write or real subprocess execution). Given this
route has **no accidental protection at all** (unlike `vt_backtest`'s path-mismatch-blocked
state), it is arguably higher-severity and should be prioritized at least as highly as 58F.

## 11. Vendored Runner Analysis

Re-read `districts/investment/vector_backtest/backtest/runner.py`'s relevant section in full
this task (unchanged from Task 59's trace):

- **Write location** (in `backtest_agent.py`, unfixed): `run_dir / "signal_engine.py"`.
- **Read location** (in `runner.py`'s `main()`): `run_dir / "code" / "signal_engine.py"` — the
  mismatch confirmed again, byte-for-byte, this task.
- **Dynamic import mechanism**: `_load_module_from_file()` — `importlib.util.spec_from_file_location`
  + `module_from_spec` + `spec.loader.exec_module(module)`.
- **Instantiation/execution**: `engine_cls = getattr(signal_module, "SignalEngine"); ...
  signal_engine = engine_cls()`, then `market_engine.run_backtest(config, loader, signal_engine,
  run_dir, ...)` — real Python execution of every method the class defines, called during the
  real backtest run.
- **Subprocess usage**: `runner.py`'s own `main()` does not itself spawn a subprocess (the
  dynamic import runs in-process) — but §10's alternate path (`backtest_tool.py`) invokes
  `runner.py` **as a subprocess** via `src.core.runner.Runner.execute(entry_script=backtest/
  runner.py, run_path, cli_args=[str(run_path)])`, a different, separate invocation mechanism from
  `backtest_agent.py`'s in-process `bt_main(run_dir)` call.
- **AST validation**: `_validate_signal_engine_source()` parses the file and rejects any top-level
  `ast.Expr`/executable statement — re-confirmed this only inspects `tree.body` (module-level
  statements), not the bodies of `class`/`def` nodes within it, so a payload placed inside
  `SignalEngine.__init__` or any of its methods is not inspected by this scrubber at all and
  would execute normally once the class is instantiated or its methods are called.
- **Path validation**: `safe_run_dir()` whitelists the `run_dir` argument itself against a
  configured root list (`VIBE_TRADING_ALLOWED_RUN_ROOTS` plus defaults) — this defends against a
  caller pointing the loader at an arbitrary filesystem location, but does not validate the
  *content* written to a legitimately-allowed `run_dir` at all.

This task did **not** modify any of the above — the vendored package is untouched. As established
in §6, the path mismatch remains, deliberately.

## 12. Behavioral Tests

New file: `tests/test_task58e_vector_backtest_strategy_permission_remediation.py` — 13 tests, all
exercising the REAL `PermissionGateway.execute()`, `Governor.dispatch()`, and
`BacktestAgent.run()`/`.vt_backtest()`, with only `backtest.runner.main` (the external execution
boundary `vt_backtest()`'s `_run()` closure calls — mocked directly on the `backtest.runner`
module, reliably, since `districts/investment/backtest_agent.py` inserts `vector_backtest/` onto
`sys.path` once at import time rather than per-call, unlike `vector_mlops`'s namespace-swap
mechanism, verified working end-to-end before this file was written) and the human-notification
boundary (`PermissionGateway._notify`/`_wait_for_confirmation`) replaced. Every test repoints
`BacktestAgent._runs_dir()` at an isolated pytest `tmp_path` (never the real repo or the real
`~/.vector/vector_backtest/runs/` directory). `permission_gateway.py`'s own gating logic runs for
real throughout, per `.claude/rules/testing.md`'s "No Mocking: permission_gateway.py."

| # | Test(s) | What it proves |
|---|---|---|
| 1 | `test_1_unapproved_vt_backtest_does_not_persist_or_execute` | Unapproved (council REJECT) call never writes any `.py` file, never creates even a bare `run_dir`, never reaches the real (mocked) `bt_main`; `PermissionGateway.execute` spied and confirmed actually invoked. |
| 2 | `test_2_gateway_unreachable_fails_closed` | A raised gateway exception fails closed — no persistence, no execution. |
| 3 | `test_3_approved_vt_backtest_reaches_persistence_and_mocked_execution` | Approved call reaches the real (mocked) `bt_main`; the exact `strategy_code` string is found written to disk. |
| 4 | `test_4_gate_precedes_persistence_and_bt_main` | Call-order spy proves `gateway.execute` happens strictly before `bt_main`; a check inside the mocked `bt_main` confirms `config.json` already exists by the time it's called (persistence happens between approval and execution, never before approval). |
| 5 | `test_5_action_content_correct_and_no_unnecessary_exposure` | The real `Action` has `action_type="vt_backtest"`, `proposed_by="BacktestAgent"`, exact `codes`/`start_date`/`end_date`/`source`/`engine`/`has_strategy_code`/`strategy_code` values, a `summary` describing real code execution — and exactly the expected param keys, nothing extra. |
| 6 | `test_6a_governor_dispatch_unapproved_..._blocked`, `test_6b_..._approved_..._reaches_mocked_execution` | The REAL `Governor().dispatch({"type": "vt_backtest", ...})`, with a real `BacktestAgent` registered, cannot bypass the boundary. |
| 7 | `test_7_direct_vt_backtest_call_cannot_bypass_gate`, `test_7b_run_dispatch_reaches_same_gate` | Direct method call and `run()`'s own dispatch both hit the identical gate. |
| 8 | `test_8_no_strategy_code_still_gated_and_reflects_absence_in_action` | Confirms the deliberate unconditional-gate design (§7): a `strategy_code=None` call is still gated, with `has_strategy_code=False` correctly visible in the Action. |
| 9 | `test_9_gate_blocks_unapproved_even_with_corrected_path_simulated` | The explicitly-requested path-mismatch diagnostic: `bt_main` is mocked to simulate a "fixed" runner that reads from wherever `backtest_agent.py` actually writes today (i.e. as if the mismatch were corrected) — an unapproved call still never reaches the point of dynamic import. Proves the real gate, not the accidental path bug, is what blocks it. |
| — | `test_10a_..._no_self_mint_and_gates_before_side_effect`, `test_10b_..._is_red_tier` | Source inspection: no `grant_control` self-mint; gate call/approval-check precede the `_run()` closure in source order; `vt_backtest` classified RED in the real `CONFIG`. |

## 13. Regression Results

**Targeted**: 13/13 pass; all 10 dangerous-path tests individually isolated
(`pytest path::test_name`), each `exit=0`. Post-isolation check: `~/.vector/vector_backtest/runs/`
contains no leaked artifacts (confirmed empty); `git status --short` shows only this task's own
legitimate file changes.

**Relevant** (`tests/test_task58a_...` 12, `tests/test_task58b_...` 16, `tests/test_task58c_...`
16, `tests/test_task58d_...` 10, `tests/test_task57_capability_bypass_diagnostic.py` 6,
`tests/test_task57_device_control_bypass_diagnostic.py` 4, `tests/test_governor.py`,
`tests/test_governor_taint_block.py`, `tests/test_regression_governor_capability_routing.py`,
`tests/unit/test_permission_gateway.py` + `tests/unit/test_permission_gateway_extra.py`,
`tests/test_permission_gateway.py`, `tests/integration/test_phase_a7_council_red_tier.py`,
`tests/test_llm_council.py`, `tests/test_trust_ladder.py`, `tests/test_karpathy_lab_run_wiring.py`):
first run showed the same 4 pre-existing, already-root-caused failures (identical to every prior
58-series task's regression run) **plus one additional failure**,
`tests/test_trust_ladder.py::test_explicit_rejection_feeds_ladder` (`IndexError:
ladder.status()[0]` — an empty list). Investigated rather than dismissed:

1. Ran in isolation alone: **passes**.
2. Ran paired only with this task's new test file: **passes**.
3. Re-ran the exact same full battery (including this task's new file) a second time: **passes**
   — the failure did not reproduce.
4. Ran the exact same full battery **without** this task's new file: only the 4 known failures,
   no trust-ladder failure.
5. Inspected the failing test's own fixture (`gateway_with_ladder`, `tests/test_trust_ladder.py:
   109`): it already uses a properly isolated in-memory `TrustLadder(conn=sqlite3.connect(
   ":memory:"))` per test — not a shared-persistent-storage issue like the `blog_dedup` case found
   in Task 58B's regression sweep.

This is a **non-deterministic, order/timing-sensitive flake** (confirmed by direct reproduction
of both the failing and passing outcome from the identical battery, with only run-to-run timing
differing) — most likely `_when_pending()`'s polling helper (`tests/test_trust_ladder.py`'s own
docstring: "poll until the gateway registers the pending event... the notify call before it may
spend real wall time, so poll on the clock") occasionally losing its race against the real,
shared, process-wide `PermissionGateway` singleton (`PermissionGateway.__new__` — re-confirmed in
Task 58D — always returns the one process-wide instance) under the added real-`gateway.execute()`
call volume this task's own new tests contribute to a large combined session. **Not caused by any
production code change in this task** — `core/config.py`'s change is a pure list addition, and
`backtest_agent.py`'s change touches nothing `trust_ladder.py` depends on. Not treated as a
regression, consistent with the identical evidentiary standard applied to `test_openwa_
absorption.py`'s order-dependent flake in Task 58B's own regression section.

**Full tracked baseline** (`tests/unit` + `tests/integration`, excluding `test_planning.py`'s 2
independently pre-existing broken tests): **8 failed / 0 errors / 29 skipped — exact same 8
failing test names, exact match to the documented baseline**
(`2212 collected / 2175 passed / 8 failed / 0 errors / 29 skipped`). Zero new failures in the
tracked scope.

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

Per this task's scope discipline, the rest of `tests/` (districts, root-level, remaining
directories) was not re-swept this task — Tasks 58B/58C each already performed that full sweep
and root-caused every unrelated pre-existing failure found there; this task's 2-file, additive-
plus-one-method change has no plausible mechanism to affect any of those files, and the tracked
baseline comparison above already demonstrates zero regression in the mechanism that would
actually be affected (permission/Governor routing).

**Static/lint/type checks**: `ruff` and `mypy` are **not available** in this environment
(`command not found`) — same as every prior task this session. `py_compile` and a live `import`
of both modified modules succeed cleanly.

## 14. Security Boundary Verification

Per the task's explicit ban on claiming behavioral verification from source/config/test-existence
alone:

- **TEST VERIFIED, mocked-boundary**: TEST 4's call-order assertions (§12) directly prove
  `gateway.execute` precedes `bt_main`, and prove `config.json` (persistence) already exists by
  the time the mocked execution boundary is reached — not merely that both occur somewhere.
- **TEST VERIFIED, path-mismatch-independent**: TEST 9 (§12) is the specific evidence the task
  asked for — a simulated "corrected path" scenario still shows an unapproved request never
  reaching the point of dynamic import, proving the real `PermissionGateway` decision, not the
  accidental bug, is the operative boundary.
- **Isolated dangerous-path verification**: all 10 tests that can reach the mocked execution/
  rejection paths were run individually, each `exit=0`; post-sweep check confirmed zero leaked
  files under the real `~/.vector/vector_backtest/runs/` directory and zero unexpected git
  changes.
- **Alternate-entry-point verification, scoped correctly**: §10 confirms no caller can reach
  `vt_backtest()` itself without the new gate — and explicitly, honestly documents the one
  alternate route (`vt_research`/`vt_swarm`/`vt_export`'s ReAct tool registry) that reaches the
  *same class* of dangerous primitive through a *different* method entirely, which this task's
  gate does **not** cover and was never intended to (per the task's own scope: "This task
  addresses ONLY... vt_backtest(strategy_code=...)").
- **Fail-closed verification**: TEST 1 (rejection) and TEST 2 (gateway exception) both
  behaviorally confirm zero persistence and zero execution.
- **No self-mint**: TEST 10a confirms no `grant_control` call exists anywhere in `vt_backtest()`.

**Explicit statement on the path mismatch, as required**: the mismatch **remains** — this task
made no change to either the write path or the read path. The authorization boundary remains
valid regardless of whether the mismatch is ever corrected in the future because the gate sits at
the top of `vt_backtest()`, strictly before the write, and does not depend in any way on whether
the subsequent write-then-read paths agree with each other — an unapproved call never reaches
either operation, and TEST 9 directly demonstrates this holds even under a simulated "corrected"
scenario.

## 15. Residual Limitations

- **The alternate ReAct-tool-registry route (§10) remains open and unfixed** — this is the most
  significant residual limitation of this task. `vt_research`/`vt_swarm`/`vt_export`, all
  Governor-reachable and `vt_research` reachable from a real public API endpoint, can reach the
  same class of arbitrary-code-execution primitive via always-registered `write_file` + `backtest`
  tools, with **no path mismatch or other accidental protection** and **no permission gate**.
  Recommended as **Task 58G**, and flagged as at least as urgent as Task 58F.
- The path mismatch (§6) was deliberately left unfixed — `vt_backtest()` remains functionally
  non-operational for real backtests today (approval alone does not make it succeed), which is an
  existing, separate functional defect, not something this security task needed to resolve.
- This task did not modify or investigate Task 59's other flagged items (`execute_playbook`'s
  destructive handlers, `PhoneController`'s shared token scope, the remaining `vectorcode`/
  `vector_mlops` surfaces) — those remain open per Task 59's own recommendations.
- No other issue outside `vt_backtest`'s own chain was discovered during implementation beyond
  the one explicitly documented in §10.

## 16. Final Status

All required conditions for FIXED + BEHAVIORALLY VERIFIED are satisfied, **specifically for
`BacktestAgent.vt_backtest()`**:

- [x] A real permission boundary exists (`PermissionGateway.execute(Action(...))`, not a mock,
      not source-level classification alone)
- [x] Correct permission classification exists (`"vt_backtest"` RED in `core/config.py`, per §8)
- [x] Authorization precedes strategy-code persistence (§12 TEST 1, TEST 4)
- [x] Authorization precedes execution (§12 TEST 1, TEST 4, TEST 9)
- [x] Rejection fails closed (§12 TEST 1)
- [x] Gateway errors fail closed (§12 TEST 2)
- [x] Alternate production entry points into `vt_backtest()` specifically cannot bypass the gate
      (§10 — none found for this method; the one alternate route found reaches a *different*
      method and is explicitly out of this task's scope, documented not silently ignored)
- [x] Behavioral tests demonstrate the boundary, not merely source presence (§12, §14)
- [x] No real arbitrary strategy code was executed during testing (§12's mocking strategy; §14's
      isolation confirmation)
- [x] Regression results show no new failures (§13 — 4 pre-existing failures plus one confirmed
      non-deterministic, unrelated flake; full tracked baseline identical to the documented
      baseline)

**58E — FIXED + BEHAVIORALLY VERIFIED**

This status applies to `vt_backtest(strategy_code=...)` specifically, as scoped by the task. It
does **not** extend to the separate ReAct-tool-registry route documented in §10/§15, which remains
an open, unfixed, confirmed alternate path to the same class of primitive — recommended as Task
58G. Per this task's explicit stop condition: not proceeding to 58F or the 7-day experiment.
