# M1d — Development / Test Safety P0 Remediation

Scope: remediate ONLY the 4 P0 findings from `M1c_DEVELOPMENT_TEST_ISOLATION_SAFETY_AUDIT.md`
(section J). No broad refactor, no new architecture, no production behavior change beyond what each
specific P0 boundary required. Objective: make development/test paths fail closed instead of
trusting assumptions — not to redesign VECTOR.

**Starting HEAD:** `b156a4792` (unchanged — no commit made until this report's own gates pass).
Pre-checks (A–E) performed before any edit:
- `git status`/`git rev-parse HEAD`/`git branch`/`git worktree list`: clean, single worktree, HEAD
  matched expectation, only the pre-existing M1b uncommitted diff present.
- No VECTOR/Segment2 process running (2 unrelated `pythonw` processes belonging to a different
  project, `AI video maker\worker-agent`, confirmed via `Get-CimInstance Win32_Process` command
  line — not VECTOR).
- Read-only production goal-state watermark recorded via `EpisodicMemory.recall_fact("goals_v1")`
  (a real, pre-existing read-only method — no write performed): `sha256 =
  fe69f8a7c9579f9ab3b6a054062ba29da43967d6bab12c0d813802b8258a3c75`, 10 goals, `g_daily_commit`
  progress=1.0/status=active — matches the known-good post-M1b-repair state.
- No write performed against production state at any point in this milestone (verified below,
  post-fix, by re-reading the same watermark).

---

## P0-A — `core/loop/autonomous_loop.py` self-test

**Before:** `_smoke_test()` constructed a real `AutonomousLoop()` and called the real
`run_forever()` for 2 real seconds. `think_loop()`'s immediate first tick would construct a real
`GoalSystem()` and could produce a real winning candidate reaching `_act_on()` — meaning a real
GREEN-tier action (real district dispatch, real LLM calls) could genuinely execute.

**After:** `_smoke_test()` no longer calls `run_forever()`/`observe_loop()`/`think_loop()` at all
(per the mission's own "prefer a bounded isolated test over a real run_forever() path" principle).
It instead proves two things directly:
1. **Construction is genuinely lazy** — every lazy-getter-backed attribute (`_context_engine`,
   `_goal_system`, `_decision_engine`, `_governor`, `_gateway`, `_policy`, `_memory`, `_red_team`,
   `_hypothesis_engine`, `_ambient`, `_event_bus`, `_worker_pool`) is asserted `None` immediately
   after `AutonomousLoop()` — if a future change makes construction eager, this raises instead of
   silently proceeding to touch real state.
2. **The actual safety boundary** — `_act_on()` (the REAL production code, unmodified) is called
   directly with a synthetic RED `Candidate`, with `loop._gateway` replaced by a fully stubbed
   `PermissionGateway` (`classify()` → `"RED"`, `execute()` → denied) and
   `districts.coding.vectorcode_bridge.get_bridge` replaced by a guard that records whether it was
   ever reached. This reuses the exact pattern already proven in
   `tests/test_r11_end_to_end_trace.py`, not a new approach.

**Files changed:** `core/loop/autonomous_loop.py` (`_smoke_test()` + `__main__` block only — zero
change to any real production class/method).

**Verified:**
```
$ python core/loop/autonomous_loop.py
✅ autonomous_loop OK — isolated smoke test passed:
   {'lazy_construction_clean': True, 'lifecycle_ok': True, 'red_action_blocked_before_bridge': True}
```
No "Episodic memory DB connection established" / "loaded N goals from memory" log lines appeared
(confirming zero real store construction) — contrast with the pre-fix run, which touched the entire
real stack. Post-run watermark re-check: unchanged (`fe69f8a7c9...`).

---

## P0-B — `core/memory/episodic.py` self-test

**Before:** `__main__` constructed a real `EpisodicMemory()` with **no isolation attempt of any
kind** (not even a broken guard) and: overwrote the real `semantic_memory` row `owner_name` with a
hardcoded value, inserted a fabricated "Checked KIIT attendance" episodic row, and wrote fabricated
content into `reasoning_chains` — one of the five memory tables `.claude/rules/memory.md` documents
as becoming real LLM training data and marks "never touch."

**After:** applies the same pattern already established (and re-verified working) in
`core/brain/goal_system.py`'s own M1b fix: an **unconditional** `VECTOR_DB_PATH`/`VECTOR_DB_KEY`
override to a fresh temp file, followed by a hard `assert configured_db_path() == <temp file>`
immediately before constructing `EpisodicMemory()` — refuses to proceed if isolation somehow didn't
take effect, rather than silently falling through to the real DB. A **conditional** ("if not already
set") guard is explicitly NOT used here — `core.config`'s dotenv load (triggered by this file's own
top-of-file `from core.config import CONFIG`) already sets `VECTOR_DB_PATH` from `.env`'s real
production value before `__main__` ever runs, so a conditional guard would be a silent no-op (the
exact M1b mechanism).

**Files changed:** `core/memory/episodic.py` (`__main__` block only).

**Verified:**
```
$ python core/memory/episodic.py
✅ episodic.py OK — {'episodic_memory': 2, 'semantic_memory': 1, 'policy_memory': 0,
                     'reasoning_chains': 1, 'skill_memory': 0, 'agent_history': 0}
```
Real production DB re-queried afterward (read-only): `episodic_memory: 469533`,
`reasoning_chains: 16189` — orders of magnitude larger than the isolated run's counts, conclusively
proving the isolated temp DB and the real DB are different files. Goal watermark unchanged. Real
`owner_name` fact confirmed `None` (was never actually set in production, contrary to what the
pre-fix self-test's hardcoded overwrite might have implied).

---

## P0-C — `EpistemicTracker` / `CounterfactualMemory` isolation boundary

**STATUS: ATTEMPTED, CAUSED A REGRESSION, ROOT-CAUSED, REVERTED. Not shipped in this milestone.**
This is reported in full rather than quietly dropped, per the mission's own honesty and evidence
standards — including the mistake, not just the eventual clean state.

**Before:** both classes isolate ONLY via an explicit `db_path=` constructor kwarg — **`VECTOR_DB_PATH`
does not affect them at all.** Any test/self-test that isolates "everything" via `VECTOR_DB_PATH`
alone (this whole session's established convention) would silently and unknowingly leave these two
stores touching their real production files (`data/epistemic.db`, `data/counterfactual.db`) if
constructed with no explicit `db_path`.

**First implementation:** a small shared helper, `assert_isolated_or_default(default_path,
class_name)` in `core/memory/db_utils.py`, wired into both constructors, firing only when
`VECTOR_DB_PATH` diverges from the real configured production value (`CONFIG["db_path"]`) while the
class itself has no explicit `db_path`. In every other case (no override at all, or an override
matching production exactly) it was a pure no-op. Individually verified correct in isolation — all 5
target behaviors (no-op with no override, no-op with production-matching override, fail-closed with
a diverging override, both classes' constructors failing closed correctly, explicit `db_path=`
completely unaffected) confirmed against disposable state only. The targeted R6–E6/R9–R11/epistemic/
counterfactual regression suite (175+ tests, run as isolated per-file invocations) passed cleanly
with this change in place.

**Regression discovered by the full-suite run (this milestone's own required final gate,
`tests/ -q` with the established 8-file Ollama/subprocess exclusion):** **260 failures + 18 errors**
appeared — entirely new, not present in the documented 13-failure baseline. Root cause, confirmed by
direct traceback inspection (`districts/projects/doc_writer.py::DocWriter() → ContextEngine() →
EpistemicTracker() → assert_isolated_or_default() → RuntimeError`) and by reading the actual
mechanism:

1. Four test files (`test_e1_persistent_learning.py`, `test_r10_decision_provenance.py`,
   `test_task89c_goal_progress.py`, `test_r11_learning_integration.py`) each set
   `os.environ["VECTOR_DB_PATH"]` **unconditionally at module level**, with **no cleanup afterward** —
   a **pre-existing** gap (not introduced by this milestone), each file's own docstring already
   documents "must be run standalone."
2. pytest's standard collection model **imports every specified test module up front, before running
   any test** — so all four files' module-level overrides fire in sequence purely from being
   collected, leaving `VECTOR_DB_PATH` permanently pointed at whichever of the four ran last in
   collection order, for the **entire remainder of the pytest process** — affecting every other test
   file that runs afterward, regardless of file-listing order.
3. **Before P0-C**, this leakage was silent and harmless: any later, unrelated test constructing
   `EpistemicTracker()`/`CounterfactualMemory()` with no `db_path` simply, quietly wrote to one of
   these four temp files instead of the real DB — never surfaced as a failure. **P0-C's fail-closed
   guard turned this pre-existing, invisible leak into a loud `RuntimeError`** everywhere it was
   newly reachable — the true mechanism of all 260+ new failures.

**First fix attempt (also failed):** added a `teardown_module()` to each of the four leaking files,
restoring `VECTOR_DB_PATH`/`VECTOR_DB_KEY` to a captured "original" value. **Insufficient** —
verified by direct reproduction (`pytest test_e1... test_r10... test_task89c...
test_phase2_districts.py::test_doc_writer_readme` still failed identically afterward). Root cause:
because all four files' module-level code runs during the SAME collection pass, each file's
"original" capture is actually the PREVIOUS file's already-leaked temp path, not the true pre-suite
value — the restore chain is broken by construction, not by an implementation bug in the restore
logic itself. A correct fix would require capturing the true original before ANY test module is
collected (e.g. a `pytest_configure` hook or a session-scoped autouse fixture in the shared
`tests/conftest.py`) — genuine, if small, changes to test infrastructure shared by the entire
~5,000-test suite, not a change scoped to the 2 named P0-C classes.

**Decision: REVERTED.** Per the mission's own principles — "do not blindly add a new configuration
architecture," "a subsystem needs architectural redesign beyond current scope" is an explicit STOP
condition, and "Maximum retry: 3 attempts per specific defect... escalate rather than brute-force" —
continuing to chase this within P0-C's original scope would mean either (a) touching the shared
`tests/conftest.py` (a much larger blast radius than "the smallest existing-compatible mechanism"
the directive asked for), or (b) further, less-principled patching of the 4 leaking files with no
guarantee of full correctness. Reverted: `core/memory/db_utils.py`'s new helper, both classes'
`__init__` changes, and the 4 test files' `teardown_module()` additions — all restored to their
pre-M1d (HEAD `b156a4792`) state via `git checkout --`. Confirmed via the final full-suite run
(section below): failures back to exactly the documented 13, 0 errors.

**What this means the P0-C gap still is:** unchanged from M1c's original finding — real, but bounded
(no test currently observed to actually exercise the silent-real-write path in a way that corrupts
meaningful data; the same "harmless quiet redirect to whichever temp file happens to be active"
behavior that existed before this milestone). Not closed. Recommended as this milestone's own
explicit next-step item (see "Recommended next milestone" at the end of this report) — the correct
fix is a session-level test-isolation fixture in `tests/conftest.py` that captures and restores
`VECTOR_DB_PATH`/`VECTOR_DB_KEY` around EVERY test needing it, closing the leak at its true source
for all four files (and any other file with the same pattern) at once, which would then make a
`VECTOR_DB_PATH`-based fail-closed guard for `EpistemicTracker`/`CounterfactualMemory` safe to add
without this blast radius.

---

## P0-D — `core/mcp_server.py`

Treated separately from the self-test remediation above, per the mission's explicit instruction — a
tool-authorization gap (Task 60's own finding), not a persistent-state isolation gap.

**Correction to M1c's own framing, found while implementing this fix:** re-reading the exact
`__main__` block showed the BARE invocation (`python core/mcp_server.py`, no flags) does **not**
actually serve — it only builds the server object via `_make_server()` to print a tool summary,
never calling `main()`/`mcp.run()`. Only an invocation WITH `--transport`/`--port`/`--host` reaches
`main()` and actually starts serving. M1c's framing ("any developer... running this exact command")
was slightly imprecise on this point; the real, confirmed risk is specifically the documented
explicit-args entry point (`python core/mcp_server.py --transport sse --port 9000`, printed by the
file's own help text), not a bare accidental run.

**Constraint:** do not weaken MCP capabilities, do not redesign gating architecture (Task 60's
architectural gap is out of scope for this narrow milestone).

**Fix:** an unconditional, unmissable `logger.warning(...)` inside `main()`, placed immediately
before `mcp.run()` is ever reached (any transport), citing the exact Task 60 finding (ungated
`db_quarantine`/email-deletion/browser-action tools, fail-open wrapper) so a human about to actually
start serving cannot miss it. This extends the exact same pattern the file already used for its
SSE-non-localhost warning (`core/mcp_server.py:210-212`) rather than introducing a new mechanism.
Zero capabilities added or removed; zero change to what tools are exposed or how.

**Verified:** bare (no-args) invocation re-run — confirmed unaffected, still only prints the scaffold
summary, never reaches `main()`/`mcp.run()`. `main()` itself was **never invoked** during this
milestone's verification (per the explicit "do not execute MCP destructive tools" instruction) — the
warning's placement and content were verified by direct source reading and by
`tests/test_m1d_development_test_safety.py`'s structural check (warning text appears before
`mcp.run(` in `main()`'s source), not by actually running the server.

---

## Other M1c findings — explicitly classified, NOT remediated (out of P0 scope)

Per the mission's own instruction: "do not blindly modify all ~10 unclassified test files... only
remediate those explicitly classified P0." Classification recorded here for the record, no files
touched:

| File | Classification | Basis |
|---|---|---|
| `tests/test_e4_update_rule.py` | **DELIBERATE** | Real `PolicyMemory()`, uuid-unique keys per test — a documented, intentional collision-avoidance design (Task 89, Agent D), not an oversight. |
| `tests/test_policy_reward_identity.py` | **DELIBERATE** | Same uuid-unique-key pattern, PLUS a real, intentional schema-migration idempotency test against the real connection — own docstring explicitly documents the lack of isolation as a deliberate choice. |
| `tests/test_e2_outcome_attribution.py`, `tests/test_e3_learning_persistence.py`, `tests/test_task92_r7_decision_candidate_correlation.py`, `tests/test_counterfactual_block_penalizes_policy.py`, `tests/test_crawl4ai_provider_and_persistence.py`, `tests/unit/test_memory_stores.py`, `tests/test_point_system.py` | **UNKNOWN** | Not individually verified safe or unsafe by M1c; not touched here. |
| `tests/test_episodic_sqlcipher_cross_contamination.py` | **UNKNOWN (leaning read-only)** | M1c's partial inspection found the file's own comment confirms an intentional real-DB read (SQLCipher-opens-correctly check); not fully verified for a mutating call elsewhere in the file. |
| `core/memory/policy.py`'s own `__main__` self-test | **NOT P0** (was M1c's P1 item 5) | Same "unique-key, no isolation" pattern as the two DELIBERATE test files above; not named as P0 by the owner's M1d directive. Left unchanged. |
| `core/memory/unified.py::UnifiedMemory.counterfactual` | **NOT P0**, flagged as residual note | No surrounding try/except (unlike every other real call site). Moot for now since P0-C was reverted (see its own section above) — flagged so whoever eventually re-attempts P0-C knows this call site would need either a try/except added or independent verification that no test path reaches it unisolated. |
| `tests/test_e1_persistent_learning.py`, `test_r10_decision_provenance.py`, `test_task89c_goal_progress.py`, `test_r11_learning_integration.py` | **PRE-EXISTING GAP, NOT FIXED** | Each sets `VECTOR_DB_PATH` unconditionally at module level with no cleanup, leaking into every later test in the same pytest process. Discovered as the root cause of the P0-C regression (see above); a `teardown_module()` fix was attempted and found insufficient (pytest's collect-all-before-run-any model breaks the "capture original, restore after" approach across multiple such files). Reverted along with P0-C. Real, pre-existing, currently harmless (nothing fails from it today) — the correct fix is a shared `tests/conftest.py` fixture, out of this milestone's scope. |
| The `g_kiit_attendance` progress=0.076-vs-baseline-0.0 discrepancy | **UNCHANGED, per explicit instruction** | Not investigated, not altered. Still `UNKNOWN` provenance per M1c section I. |

---

## Adversarial review

Performed after implementation (and after P0-C's revert), against the actual current code, scoped to
the 3 P0 fixes that actually shipped (P0-A, P0-B, P0-D):

1. **Can dotenv reintroduce production configuration?** For P0-A/P0-B: no — the override is
   unconditional and happens after dotenv already ran but before any store construction, with a hard
   assert. Confirmed by two full re-runs each, watermark unchanged both times.
2. **Can an unset env var cause production fallback?** N/A for the shipped fixes — P0-A doesn't touch
   real stores at all; P0-B's override is unconditional, never reads an "is it set" branch.
3. **Can a constructor silently select the production DB?** No for P0-A/B (hard assert blocks it).
   (P0-C, which would have answered this for `EpistemicTracker`/`CounterfactualMemory`, was reverted
   — see its own section; this remains an open gap, not newly introduced.)
4. **Can a direct module execution bypass the isolation guard?** No — for P0-A/B the override/assert
   is the first executable code in the block, sequential, unconditional; there is no code path that
   reaches store construction without passing through it first.
5. **Can a self-test construct a second store before the guard?** No — verified by reading the full
   before/after diff of each `__main__` block; the override is the very first statement.
6. **Can a test import trigger production initialization?** No — `__main__` blocks only execute on
   direct script execution, never on `import`, by Python's own semantics; unaffected by this fix
   either way.
7. **Can autonomous_loop self-test reach Governor/PermissionGateway?** No — confirmed by the absence
   of any Governor/PermissionGateway initialization log line in the actual verification run; the only
   gateway touched is the pre-installed `MagicMock`.
8. **Can a test invoke real subprocess/network/device/MCP side effects?** No new ones introduced.
   P0-D's `main()`/`mcp.run()` was never invoked during this milestone's own verification.
9. **Can a future developer accidentally remove the isolation assertion without a failing test?**
   **This was a genuine gap prior to this step** — the P0-A/B fixes lived only inside `__main__`
   blocks (never pytest-collected). Closed for P0-A/B/D by adding
   `tests/test_m1d_development_test_safety.py` (7 tests): structural checks that the dangerous
   patterns (`run_forever()` call, absence-guarded override) are absent from the relevant source,
   behavioral checks that `_smoke_test()` genuinely runs isolated and blocks RED, and structural
   checks of the P0-D warning's presence and placement. For the reverted P0-C, this file instead
   guards the opposite direction — `TestP0CNotRegressed` fails loudly if `assert_isolated_or_default`
   is ever reintroduced into either constructor without also updating this report's regression
   analysis, so a future re-attempt cannot silently reintroduce the same full-suite blast radius.

---

## Testing summary

- **Targeted, per-P0 verification:** P0-A, P0-B, P0-D each individually verified against
  disposable/isolated state only — never against the real production DB for the fix itself (only
  read-only watermark re-checks against production, to prove NO change occurred). P0-C was also
  individually verified correct in isolation before the full-suite run exposed its blast radius (see
  its own section) — that verification remains true of the reverted code, it just wasn't sufficient
  on its own to justify shipping.
- **New permanent regression tests:** `tests/test_m1d_development_test_safety.py`, 7/7 passing
  (covers P0-A, P0-B, P0-D, plus a non-regression guard for reverted P0-C).
- **Relevant regression suite** (`test_e1_*` through `test_e6_*`, `test_r8_*` through `test_r11_*`,
  `test_task91_r6_*`, `test_task92_r7_*`, `test_policy_reward_identity.py`,
  `test_counterfactual_block_penalizes_policy.py`, the epistemic/counterfactual/governor/
  decision-engine-focused suites, the `learning_lab` R11 confirmation test): **all pass except 2
  pre-existing failures** (`test_epistemic_integration.py::test_different_domains_independent`,
  `test_epistemic_scoring.py::test_stale_domain_reduces_score`), confirmed via a `git stash`
  before/after comparison to be pre-existing and unrelated to this milestone (true both with and
  without the now-reverted P0-C changes).
- **Full non-Ollama baseline** (`pytest tests/ -q`, established 8-file Ollama/subprocess exclusion —
  `test_intent_matcher.py`, `test_agency_run_wiring.py`, `test_coding_reviewers_run_wiring.py`,
  `test_email_agent_permission_gate.py`, `test_red_interactive_tools_bypass.py`,
  `test_regression_governor_capability_routing.py`, `test_command_websocket_parity.py`,
  `test_mcp_server_main_dispatch_fix.py`): **5,367 collected, 13 failed, 0 errors.** All 13 failures
  cross-checked against `90_AUTHORITATIVE_REPOSITORY_BASELINE.md`'s documented Class-A/C baseline —
  **11 are byte-identical name matches**, and the remaining 2
  (`test_different_domains_independent`, `test_stale_domain_reduces_score`) are the same
  pre-existing pair confirmed above via `git stash`. **Zero new regressions.** (A first attempt at
  this run, before the 8-file exclusion was correctly applied, showed hundreds of unrelated Ollama
  timeout/connection failures — a testing-methodology error on this milestone's own part, not a
  code issue; corrected and re-run.)

## Files changed (complete list)

```
core/loop/autonomous_loop.py       — P0-A: _smoke_test() + __main__ rewritten
core/memory/episodic.py            — P0-B: __main__ isolation added
core/mcp_server.py                 — P0-D: unmissable warning before mcp.run()
tests/test_m1d_development_test_safety.py  — NEW: 7 permanent regression tests
```

P0-C's changes (`core/memory/db_utils.py`, `core/brain/epistemic_tracker.py`,
`core/memory/counterfactual.py`, and `teardown_module()` additions to 4 test files) were implemented,
found to regress the full suite, and reverted via `git checkout --` — none of those 7 files carry any
net change from this milestone. No file outside the 4 listed above was modified. No production
behavior changed for any caller of `core/loop/autonomous_loop.py`/`core/memory/episodic.py` that does
not run those files' own `__main__` self-test directly, and no change to `core/mcp_server.py`'s
actual tool set or gating.

## Final Gate

**YELLOW — REMEDIATION PARTIAL; DO NOT RESUME R17 AUTOMATICALLY. Owner decision required.**

Reasoning:
- **P0-A, P0-B, P0-D: fully remediated, verified, regression-clean.** These 3 close 3 of the 4 P0
  findings from M1c with no open blast-radius concerns — `core/loop/autonomous_loop.py`'s self-test
  can no longer execute a real action, `core/memory/episodic.py`'s self-test can no longer write real
  data (including the `reasoning_chains` training-data hazard), and `core/mcp_server.py`'s real
  serving path now carries an unmissable warning about its pre-existing ungated-tool gap.
- **P0-C: NOT remediated.** Implemented, caused a 260-failure/18-error regression when validated
  against the full suite (this milestone's own required final gate — the regression was caught by
  following the mission's own testing discipline, not missed), root-caused precisely, a first fix
  attempt found insufficient, and reverted rather than pursued into architectural territory (a shared
  `tests/conftest.py` fixture) beyond this milestone's explicit scope. The underlying gap it was
  meant to close (`EpistemicTracker`/`CounterfactualMemory` silently touching real production files
  when a test isolates via `VECTOR_DB_PATH` alone) remains open — bounded and currently harmless (no
  observed case where it actually corrupts meaningful data), but open.
- **This gate is not a full GREEN** because one of the 4 named P0 items is unresolved, and this
  report's own instructions define the gate in terms of the complete P0 set, not a majority. It is
  not RED because nothing unsafe was left in a worse state than before this milestone started — the
  regression was caught and reverted before being proposed for commit, not shipped.

**Does this block R17?** R17's own target module (`core/runtime/plans.py`) was independently
confirmed VERIFIED-ISOLATED in M1c and is unaffected by anything in this milestone. The P0-C gap does
not involve plan/goal persistence at all. A case could be made that R17 is safe to resume on its own
technical merits — but per this mission's own explicit instruction ("Do not proceed to R17
automatically even if GREEN... STOP after M1d and report to me"), and given this gate is YELLOW, not
GREEN, that decision is left to the owner rather than made here.

**What is committed:** only once the owner confirms — per this report's own commit policy, nothing
has been committed yet. Working tree currently contains: `core/loop/autonomous_loop.py`,
`core/memory/episodic.py`, `core/mcp_server.py`, `tests/test_m1d_development_test_safety.py` (all
new/modified from this milestone), plus the pre-existing M1b diff (`core/brain/goal_system.py`,
`COGNITIVE_EVOLUTION_ORCHESTRATOR.md`) and the M1c audit artifacts, all still uncommitted from before
this milestone began.
