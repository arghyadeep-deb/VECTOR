# Task 71 — Offline Technical Audit (performed while Segment 2 runs)

**Read-only static analysis. Segment 2 (owner-controlled terminal, launched per Task 69) was not
touched at any point.** No VECTOR process was started/stopped/interacted with. No database was
opened. No production code was modified. See §17 for the full disclosure.

---

## 1. Executive Summary

This audit produced **21 findings** across observability, performance, testing, documentation,
memory, error handling, and permission-residual categories. **2 are confirmed defects (Category A)**,
the rest are suspected defects, architectural weaknesses, integration/measurement gaps, or test
coverage gaps. **No new safety-relevant or RED-tier-adjacent finding was discovered** — Task 60's own
residual (the Class-A/user-only `core/mcp_server.py` gap) remains the only known permission-adjacent
weakness, unchanged since Task 60, and it is not autonomous-reachable.

The single most experiment-relevant finding (OBS-02) is a **correction to how prior observation
reports' semantic-memory metric should be interpreted**, not a new bug: `semantic_memory`'s flat row
count (2,034, unchanged across Tasks 63-69) reflects an UPSERT-pattern checkpoint mechanism
(`loop_state.py`) that was, in fact, firing roughly every ~10 seconds throughout Segment 1 —
substantial write *activity* that the row-count metric cannot see. This does not overturn any H4
(learning) conclusion already drawn, but it means "semantic memory remained completely flat" should
be read as "row count," not "zero write activity."

The single most experiment-relevant test-coverage finding (TEST-01) is that `_episode_pattern_predictions`
— the exact function Task 66's own targeted source read used to explain the experiment's one
confirmed behavioral-change event — has **zero direct behavioral test coverage**; it is only ever
mocked out in the test suite, never exercised against synthetic data and checked for correct output.

**Highest-severity finding:** OBS-01 (S2, goal-linkage silently dropped before persistence) and
ERR-01 (S2, confirmed defect — see below) are the highest-severity items; nothing rises above S2.
**No finding is classified DIRECT EXPERIMENT IMPACT at a severity that would call the experiment's
validity into question** — OBS-02 and ERR-01 are DIRECT EXPERIMENT IMPACT in the sense of affecting
how existing/future observation reports should be *worded*, not in the sense of invalidating any
conclusion already drawn.

## 2. Audit Scope and Limitations

Performed via Read/Grep/Glob only, entirely against static source, existing test files, and
existing VECTOR_TECHNICAL_KNOWLEDGE documentation. No Python code that imports `core/`, `districts/`,
or `vectorcode/` was executed by this task directly; one forked sub-agent (covering Steps 10-13)
operated under the same constraint. No database (episodic/main or `telemetry.db`) was opened by
either this task or its fork, in strict compliance with "Segment 2 must remain completely
undisturbed." This is necessarily a **sampling** audit, not an exhaustive one, given the codebase's
size (133+ agent files, 33 districts) — Steps 7 (agent/district contract audit) received the
lightest coverage of the 13 requested steps; findings there should be treated as illustrative, not
comprehensive, and are flagged as such below.

## 3. Confirmed Defects (Category A)

```
ID: ERR-01
Subsystem: Obsidian vault watcher — expected-timeout misclassified as a suppressed exception
File: core/memory/obsidian_sync.py
Function/Class: ObsidianSync.start_watching (inner watch loop)
Location: line 430-433
Category: A — confirmed defect
Severity: S2
Reachability: R3 — behaviorally confirmed: this exact log line ("[VECTOR] suppressed exception
  (degraded mode)" at core.memory.obsidian_sync:start_watching:433) appears in essentially every
  Segment-1 log excerpt captured across Tasks 62-66, at roughly 1-second intervals for the entire
  runtime.
Experiment Impact: DIRECT EXPERIMENT IMPACT
Confidence: high

Problem: the watch loop does `path = await asyncio.wait_for(queue.get(), timeout=1.0)` inside a
try/except that treats `asyncio.TimeoutError` (line 432-433) as a warning-worthy "suppressed
exception (degraded mode)" event, logged with `exc_info=True` (full traceback capture). A
`TimeoutError` here is not degraded-mode fallback behavior — it is the loop's own normal,
expected, designed control-flow signal meaning "no file-change event arrived in the last second,"
which is the overwhelmingly common case for a vault that isn't being actively edited.
Evidence: obsidian_sync.py:427-433 —
  "try:\n    while self._watching:\n        try:\n            path = await asyncio.wait_for(queue.get(), timeout=1.0)\n            seen[path] = time.monotonic()\n        except asyncio.TimeoutError:\n            logger.warning(\"[VECTOR] suppressed exception (degraded mode)\", exc_info=True)"
Call-chain / data-flow: AutonomousLoop startup → obsidian_sync.start_watching() (a long-lived
  background coroutine) → 1s poll loop → every empty second → logger.warning with full traceback.
Why it matters — DIRECT EXPERIMENT IMPACT, explained precisely: this is the single highest-frequency
  log line in every log file produced by Segment 1 (observed at roughly 1/second for ~2h03m — on
  the order of 7,000+ occurrences in Segment 1 alone), yet it carries zero information (it fires on
  every idle second, not on any actual failure). This both (a) makes `vector_loop.log` grow
  substantially faster than the genuinely-informative lines within it would require, working against
  the log-rotation headroom the experiment's observability depends on, and (b) required every
  observation report in this experiment (Tasks 63-66) to manually filter this line out of log
  excerpts to find genuinely relevant lines, an avoidable analysis burden. It does not affect
  correctness — the loop's actual function (debounced file ingestion) is unaffected — hence S2, not
  higher.
Known constraints: this exact generic "[VECTOR] suppressed exception (degraded mode)" message string
  is used as a repo-wide convention (confirmed via grep: 116 files use it) as part of the project's
  own documented resilience philosophy (CLAUDE.md: "NEVER propagate — loop must not die"). The
  convention itself is not being challenged here — only this one specific misuse of it against an
  expected, not exceptional, control-flow event.
Recommended future remediation: change the except asyncio.TimeoutError: branch to either (a) a
  silent `continue` (no log line at all — the timeout is not noteworthy), or (b) a `logger.debug`
  (not `warning`) with `exc_info=False` if any visibility is still desired for diagnostics.
Why remediation is deferred until after experiment: obsidian_sync.py is imported and actively running
  inside Segment 2's live process; any edit to this file, however small, is explicitly forbidden by
  this task's rules while the experiment is live, and even a "safe-looking" logging change carries
  nonzero risk of a typo/syntax issue reaching a running-critical module.
```

```
ID: PERF-02 (promoted to confirmed — see original finding from the Step-10/11 fork, restated here as Category A per its unambiguous evidence)
Subsystem: gateway_audit / inference_calls retention
File: core/loop/permission_gateway.py, core/metering/inference_observability.py, scripts/inference_report.py
Category: A — confirmed defect (absence of any automatic retention mechanism, confirmed by exhaustive grep, not inferred)
Severity: S1
Reachability: R2
Experiment Impact: NO EXPERIMENT IMPACT
Confidence: high

Problem: neither gateway_audit nor inference_calls has any automatic pruning/retention logic anywhere
  in the codebase. inference_observability.py's own prune(days=N) method exists but is called from
  exactly one place in the entire repository: scripts/inference_report.py's manual --prune CLI flag.
  gateway_audit has no prune mechanism of any kind, anywhere.
Evidence: repo-wide grep for get_inference_observability().prune / .prune(days across all *.py →
  exactly one match (scripts\inference_report.py:110). autonomous_loop.py and core/loop/cron_jobs.py
  both confirmed (via direct grep) to contain zero references to any prune call.
Call-chain / data-flow: N/A — this is an absence finding.
Why it matters: both tables grow strictly monotonically for the life of the database; not a near-term
  risk (Segment 1 produced only ~30/~90 rows respectively in ~2h), but a genuine unbounded-growth
  pattern for any deployment running weeks to months.
Known constraints: full retention during THIS experiment is explicitly the desired behavior, not a
  bug in context.
Recommended future remediation: add a scheduled (weekly) call to InferenceObservability.prune() with
  a generous (30+ day) retention window via core/loop/cron_jobs.py, once this experiment's need for
  full-fidelity data has passed. A corresponding retention policy for gateway_audit would need to be
  designed (it has no prune() method today at all).
Why remediation is deferred until after experiment: pruning during the experiment would destroy the
  exact data the experiment exists to collect.
```

## 4. Suspected Defects (Category B)

```
ID: PERF-01
Subsystem: CounterfactualMemory instantiation pattern
File: core/memory/counterfactual.py, core/loop/autonomous_loop.py
Function/Class: CounterfactualMemory.__init__; 4 call sites in autonomous_loop.py
Location: counterfactual.py:58-66; autonomous_loop.py:300, 445, 1094, 1720
Category: B — suspected defect (architectural weakness bordering on defect)
Severity: S1
Reachability: R3 — behaviorally confirmed live (the "CounterfactualMemory initialized" log line
  appears on essentially every think_loop cycle throughout Segment 1, ~every 10s)
Experiment Impact: NO EXPERIMENT IMPACT
Confidence: high

Problem: CounterfactualMemory.__init__ opens a raw sqlite3.connect(db_path, check_same_thread=False)
  with no caching/singleton pattern, and is instantiated fresh inline at 4 separate call sites within
  autonomous_loop.py's hot decision/rejection path — not once at startup and reused. This contrasts
  with EpisodicMemory, whose frequent re-instantiation is cheap because it delegates to
  get_db_connection() (episodic.py:478-485), a genuine module-level singleton with a lock.
Evidence: counterfactual.py:65 (raw sqlite3.connect, no pooling); autonomous_loop.py:300, 445, 1094,
  1720 (each does `from core.memory.counterfactual import CounterfactualMemory` then
  `CounterfactualMemory()`).
Call-chain / data-flow: think_loop tick → decision picked → CounterfactualMemory() → new raw SQLite
  connection → query/write → connection closed via GC when the local reference goes out of scope (no
  explicit .close()).
Why it matters: conservatively 700+ raw connect/disconnect cycles against counterfactual.db over
  Segment 1's ~2h03m runtime, purely as avoidable instantiation overhead. SQLite connection setup is
  typically low-cost, so this is unlikely to be the dominant latency source in a pipeline already
  dominated by multi-second LLM calls (hence S1, not higher) — but it is real, measurable overhead
  inconsistent with the class's own stated "cross-session learning" persistent-store intent.
Known constraints: no explicit .close() anywhere either — relying on CPython refcounting GC, not an
  explicit resource-management pattern.
Recommended future remediation: a module-level get_counterfactual_memory() singleton getter mirroring
  EpisodicMemory's pattern; update the 4 call sites.
Why remediation is deferred until after experiment: touches a memory subsystem actively read/written
  by the running Segment-2 experiment; any change to connection lifecycle risks altering timing or
  introducing a subtle concurrency issue mid-experiment, for a purely non-functional benefit.
```

## 5. Architecture/Integration Gaps (Category C/D)

```
ID: OBS-01
Subsystem: PermissionGateway audit trail — goal linkage dropped
File: core/loop/permission_gateway.py
Function/Class: Action (dataclass, lines 26-29); PermissionGateway._init_audit_store (373-385);
  PermissionGateway._persist_audit (387-400)
Category: D — integration gap (goal linkage exists upstream, is discarded at the persistence boundary)
Severity: S2
Reachability: R3 — behaviorally verified: every gateway_audit row queried across Tasks 62-69 lacks
  any goal reference, while decision.winner.goal_ids and Action.params={"goal_id": ...} are both
  confirmed present earlier in the same pipeline (autonomous_loop.py:870, 930-935, 1144, 1288-1363).
Experiment Impact: POSSIBLE EXPERIMENT IMPACT
Confidence: high

Problem: gateway_audit's schema (seq, ts, action_type, level, approved, executed, proposed_by,
  reason) has no goal_id column, and _persist_audit's INSERT (lines 391-394) never reads
  Action.params at all. The goal linkage that autonomous_loop.py genuinely computes and attaches
  (goal_ids threaded through the decision pipeline, and explicitly placed into an Action's params for
  at least the analyze_progress action type) is silently discarded at the final persistence step.
Evidence: gateway_audit CREATE TABLE (lines 378-383, no goal_id column); autonomous_loop.py:870
  `params={"goal_id": a["goal_id"], "title": a["title"]}`; decision.winner.goal_ids referenced at
  lines 930-935, 1144, 1288, 1330, 1343, 1351, 1357, 1363.
Call-chain / data-flow: decision_engine Candidate(goal_ids=[...]) → autonomous_loop._act_on builds
  Action(params={...goal_id...}) → PermissionGateway.execute → _write_audit → _persist_audit → INSERT
  without params.
Why it matters: every observation report to date has had to infer "which goal is this action for"
  indirectly from log-line text rather than a queryable join — a future question like "did VECTOR
  ever act GREEN-tier specifically in service of goal X, and how often" cannot be answered from
  gateway_audit alone.
Known constraints: gateway_audit is the exact durable table the experiment protocol was designed
  around for its proven reliability — schema changes mid-experiment are out of scope by rule.
Recommended future remediation: add a nullable goal_id (or goal_ids JSON) column, populated from
  Action.params when present; historical rows stay NULL.
Why remediation is deferred until after experiment: any schema change to the live audit table risks
  disrupting Segment 2's durable logging mid-flight; explicitly forbidden by this task's rules.
```

```
ID: PLAN-01
Subsystem: Plan-store observability
File: core/runtime/plans.py
Function/Class: Plan, PlanStep, PlanEvent, PlanStore, PlanRunner (all confirmed to exist, classes at
  lines 34, 54, 110, 136, 436, 840 respectively)
Category: E — measurement/observability gap (clarifying, not new — see note)
Severity: S1
Reachability: R2 (the classes exist and were already directly read/audited in Task 60's own crash-
  recovery investigation — `_recover_stale_running_steps`, `_is_safe_to_auto_resume`)
Experiment Impact: NO EXPERIMENT IMPACT
Confidence: high

Problem/clarification: every observation report since Task 61 has cited "plan metrics remain
  entirely unmeasured" as an open limitation. This audit confirms precisely what that means: the
  underlying Plan/PlanStep/PlanStore/PlanRunner architecture is real and substantial (not dead code,
  not vaporware — Task 60 already traced its crash-recovery logic in detail), but no query
  helper/CLI/report exists anywhere that surfaces "plans created/completed/failed/recovered" counts
  the way run_vector.py smoke surfaces episodic/semantic/policy/reasoning-chain counts. The gap is in
  the OBSERVATION SURFACE, not in the underlying system's existence.
Evidence: class definitions confirmed present at core/runtime/plans.py lines 34/54/110/136/436/840;
  no corresponding query method referenced anywhere in the observation-task lineage (Tasks 63-69).
Call-chain / data-flow: N/A — clarifying an existing, already-flagged gap rather than tracing new
  code.
Why it matters: this precise characterization (system exists, observability surface doesn't) should
  replace the vaguer "unmeasured" framing in future reports, since it correctly implies the fix is a
  new read-only query helper, not new plan-execution machinery.
Known constraints: none beyond the standing rule against adding instrumentation during the experiment.
Recommended future remediation: a read-only get_plan_summary() helper (counts by status) analogous to
  InferenceObservability's own summary methods.
Why remediation is deferred until after experiment: adding even a read-only helper means importing
  and exercising core/runtime/plans.py in a new way — explicitly out of scope for a live-experiment
  audit task.
```

## 6. Learning/Adaptation Gaps

Synthesized from this task's own direct, extensive live evidence across Tasks 63-66 (re-cited, not
re-derived, per this task's own instruction not to repeat already-established findings) plus this
audit's new OBS-02 correction:

```
ID: LEARN-01
Subsystem: analyze_progress / g_kiit_attendance decision loop
Category: C — architectural weakness (already established as the experiment's dominant negative-
  evidence signal across Tasks 63-66; restated here only to fold it into this audit's formal
  cross-reference, not re-investigated)
Severity: S1 (informational for this audit's purposes — its experiment significance, not a code-
  quality severity, is what matters)
Reachability: R3
Experiment Impact: DIRECT EXPERIMENT IMPACT (already fully documented in Tasks 65-66; not a new
  finding)
Confidence: high

Problem: already fully characterized (Tasks 65-66): the same candidate is proposed, auto-blocked by
  CounterfactualMemory as a repeat rejection, and re-proposed identically next cycle, with the policy
  score frozen and zero alternative candidates ever generated, across the entire observed runtime.
Why it matters: this is the experiment's central open scientific question (does this ever resolve
  given a much longer horizon?), not a code defect to remediate — explicitly NOT recommended for
  "fixing," since resolving it artificially would destroy the exact phenomenon the experiment is
  observing.
Recommended future remediation: none — this is a research question, not a bug ticket. If, after the
  experiment concludes, the owner wants to understand WHY no alternative candidate is ever generated
  (a decision_engine candidate-generation question, not explored in depth by this audit), that would
  be a legitimate follow-up investigation, clearly separated from "fixing" the current experiment's
  behavior.
Why remediation is deferred until after experiment: this is the experiment's subject matter, not a
  defect — deferral here means "do not intervene," full stop, not merely "defer the fix."
```

```
ID: OBS-02
Subsystem: loop_state checkpoint mechanism (goal/decision/agent-HP persistence)
File: core/loop/loop_state.py, core/memory/episodic.py
Function/Class: save_goal, save_decision, save_agent_hp (loop_state.py:248-311); EpisodicMemory.remember
  (episodic.py:1090-1115, the UPSERT)
Category: E — measurement/observability gap, with a direct correction implication for prior reports
Severity: S2
Reachability: R3 — save_goal/save_decision confirmed called every think_loop cycle (autonomous_loop.py
  933-935, 1321-1323); save_agent_hp every 60s (2798-2803)
Experiment Impact: DIRECT EXPERIMENT IMPACT
Confidence: high

Problem: EpisodicMemory.remember() performs a true SQL upsert (episodic.py:1102-1110, "INSERT ... ON
  CONFLICT(key) DO UPDATE") keyed on a fixed string. loop_state.py's entire checkpoint mechanism uses
  exactly three fixed keys (loop:current_goal, loop:last_decision, loop:agent_hp). Every write
  overwrites the prior value in place — semantic_memory's row COUNT never increases no matter how
  many times these keys are updated, even though genuine write activity is occurring continuously.
Evidence: episodic.py:1103-1110 (literal ON CONFLICT...DO UPDATE clause); loop_state.py:264-274 and
  288-299 (both call _mem().remember(FIXED_KEY, ...)); confirmed call sites in autonomous_loop.py at
  lines 933-935 (inside the per-decision-cycle branch), 1321-1323 (same cadence), and 2798-2803
  (inside an explicit `while self._running: await asyncio.sleep(60)` loop).
Call-chain / data-flow: think_loop tick (~every 10s in Segment 1) → decision winner picked →
  loop_state.save_goal()/save_decision() → EpisodicMemory.remember(fixed_key, value) → UPSERT, row
  count unchanged.
Why it matters — DIRECT EXPERIMENT IMPACT, precisely stated: Tasks 63-66's reports state "semantic
  memory remained completely flat... zero new semantic entries were created at any point" as negative
  evidence bearing on H4. The row-count claim is factually correct. Its natural reading — "zero
  semantic-memory write activity occurred" — is not: save_goal/save_decision fired roughly every 10
  seconds for the entire ~2h03m of Segment 1 (conservatively 700+ UPSERT calls), invisible to the
  row-count metric used as the sole activity signal. This does NOT overturn the H4 conclusion (an
  UPSERT to a fixed key still fails the strict causal-chain bar those reports correctly applied for
  "learning") — but the precise evidentiary wording should be corrected in any future reference to
  this finding: "zero semantic-memory ROW-COUNT growth despite substantial UPSERT write activity,"
  not "zero write activity."
Known constraints: this is intentional checkpoint-store design (state, not an append-only log), not
  itself a bug.
Recommended future remediation: none to the code; future observation reports should additionally
  query semantic_memory.updated_at for the three known loop_state keys directly, rather than relying
  on total row count as the sole semantic-memory activity proxy.
Why remediation is deferred until after experiment: this is a reporting-methodology correction, not a
  code change — flagged so subsequent Segment-2 reports can use the corrected framing without any
  runtime modification.
```

## 7. Security/Permission Residual Risks

No new finding beyond what Task 60 already established and disclosed. Re-stated for completeness,
not re-investigated (per this task's explicit instruction not to blindly repeat the 58A-58G/Task 60
audits):

```
ID: SEC-01
Subsystem: core/mcp_server.py tool ecosystem (carried forward from Task 60 §9.1, unchanged)
Category: C — architectural weakness (pre-existing, already disclosed)
Severity: S2 (per Task 60's own classification — real gap, not a blocker, since not autonomous-
  reachable)
Reachability: R1 (statically present; Task 60 already established it is NOT autonomously reachable —
  Class A, user-only, requires a human operating Claude Code/Cursor via .mcp.json)
Experiment Impact: NO EXPERIMENT IMPACT — re-confirmed by this audit's own scope: nothing in Segment
  2's actual running process (plain `python run_vector.py loop`, no API server, no MCP server
  started) touches this surface at all.
Confidence: high (carried forward, not re-derived)

Problem: mcp_secure_call() in core/mcp_tools/security.py fails open on internal error and does not
  gate on the risk level it computes; most core/mcp_tools/*.py modules have zero PermissionGateway
  reference. Full detail already in Task 60's report.
Why remediation is deferred until after experiment: this finding predates and is independent of the
  current experiment; deferred per the same "no production modification during observation tasks"
  rule as everything else in this audit, not because it is newly time-sensitive.
```

## 8. Error-Handling Issues

See ERR-01 (§3, confirmed defect) — the obsidian_sync timeout-misclassification finding is this
audit's primary error-handling finding, chosen for depth over breadth given the 116-file scope of the
repo-wide "suppressed exception (degraded mode)" convention (confirmed via grep, not further
individually audited — the convention itself matches the project's own documented resilience
philosophy and is not, by itself, a defect; only the one specific misuse found and traced in ERR-01
is reported as a defect).

## 9. Observability Gaps

See OBS-01 through OBS-05 (§5-6 above and the fork's contribution below) for the full set. Summary
table:

| ID | Gap | Severity |
|---|---|---|
| OBS-01 | Goal linkage dropped before gateway_audit persistence | S2 |
| OBS-02 | semantic_memory row-count metric doesn't reflect UPSERT activity | S2 |
| OBS-03 (fork) | Agent-HP / decision history: only latest snapshot recoverable, no time series | S1 |
| OBS-04 (fork) | loop_heartbeat.json exists and could have helped Task 67's investigation; underused, not absent | S1 |
| OBS-05 (fork) | hypothesis_engine/suggestion_queue correlation to downstream decisions — UNCONFIRMED, not located within this audit's time budget | S1 |
| PLAN-01 | Plan-store has no query/reporting surface (system itself is real, not dead code) | S1 |

## 10. Performance/Resource Risks

See PERF-01 (§4) and PERF-02 (§3). No unbounded-queue or subprocess-accumulation finding was
confirmed this audit (a dedicated pass at `core/event_bus/worker_pool.py`'s `asyncio.Queue`
construction sites was not completed within this task's time budget — flagged as an open item, not a
negative result, in §16).

## 11. Testing Gaps

```
ID: TEST-01
Subsystem: core/brain/anticipation.py — _episode_pattern_predictions
File: tests/integration/test_phase_c3_anticipation.py
Location: lines 185, 211 (the only two references to _episode_pattern_predictions in the whole
  tests/ tree, both are `patch(...)` calls mocking it OUT)
Category: G — test coverage gap ("only mocked tests")
Severity: S2
Reachability: R3 for the production code (this function produced Task 66's single most significant
  live finding); R0 for direct behavioral test coverage of its own logic
Experiment Impact: DIRECT EXPERIMENT IMPACT
Confidence: high

Problem: the exact mechanism Task 66 used (via a targeted, justified source read) to explain the
  experiment's one confirmed behavioral-change event — the ±1-hour episode-window matching, the
  count>=2 threshold, the confidence formula min(0.5 + count*0.1, 0.90) — is never behaviorally
  tested. It is only ever patched out in the two references found.
Evidence: grep "episode_pattern" tests/ → exactly 2 matches, both patch("core.brain.anticipation._episode_pattern_predictions", ...).
Why it matters: Task 66's H5 (adaptation) negative finding rests specifically on ruling this function
  IN as a fully deterministic, non-experiential explanation for the observed prediction change. That
  explanation currently rests entirely on source reading, not on any test that independently confirms
  the function's behavior against realistic synthetic data — including edge cases like hour
  boundaries (23→0) that were not exercised live during Segment 1's observed window (01:xx-02:xx
  only).
Recommended future remediation: a focused unit test seeding fake EpisodicMemory.recall() results
  across several hours (including a wraparound boundary) and asserting the function's exact output
  directly, no mocking of the function itself.
Why remediation is deferred until after experiment: writing/running a new test touches a module the
  live experiment process imports; explicitly out of scope during the observation window.
```

```
ID: TEST-02
Subsystem: core/brain/anticipation.py — loop/scheduler integration tests
File: tests/integration/test_phase_c3_anticipation.py
Location: lines 229-248 (method-exists / is-async source checks), line 374
  (test_loop_source_has_600s_sleep — a literal source-text check for "600")
Category: G — test coverage gap ("only source-string tests")
Severity: S1
Reachability: R3 for the underlying code (confirmed running live, stable 10-minute cadence across
  Tasks 63-66); R0 for behavioral verification of that cadence via the test suite itself
Experiment Impact: POSSIBLE EXPERIMENT IMPACT
Confidence: high

Problem: several tests check that a method exists, is declared async, or that a literal number
  appears in source text — not that the loop actually ticks at the intended interval or that
  anticipation_loop is actually invoked from run_forever's real control flow at runtime.
Why it matters: a regression that changed the real sleep interval without changing the literal "600"
  string elsewhere, or that broke the call from run_forever while leaving the method itself intact,
  would not be caught.
Recommended future remediation: a behavioral test with a mocked/controllable clock asserting the
  actual tick cadence and the actual call from run_forever's real execution path.
Why remediation is deferred until after experiment: same as TEST-01.
```

## 12. Documentation/Contract Inconsistencies

```
ID: DOC-01
Subsystem: NSSM service installer CLI contract (re-confirmed unchanged from Task 68's own finding)
File: scripts/install_service.ps1
Location: line 73
Category: A — confirmed defect (not newly discovered — cited to confirm still-current state)
Severity: S2
Reachability: R1 — statically broken; not runtime-exercised (NSSM not installed, per Task 68; not
  used for Segment 2's hosting mechanism, per Task 69)
Experiment Impact: NO EXPERIMENT IMPACT
Confidence: high

Problem: & $NSSMPath install $ServiceName $Python "$Script --mode loop" — run_vector.py's argparse
  defines mode as a positional argument (nargs="?", default="loop"), no --mode flag exists anywhere.
  This invocation would make argparse reject --mode as unrecognized.
Evidence: install_service.ps1:73 (unchanged); run_vector.py's parse_args() — positional mode only,
  --host/--port are the only registered flags.
Why it matters: unchanged from Task 68 — cited here only per Step 13's explicit instruction to
  re-confirm this specific bug's current state, not re-derived.
Recommended future remediation: change line 73 to drop --mode ("$Script loop" or bare "$Script").
Why remediation is deferred until after experiment: this script is not on Segment 2's hosting path at
  all (Task 69 deliberately avoided NSSM); deferred purely to respect the no-production-edits rule,
  not because of any experiment relevance.
```

```
ID: DOC-02
Subsystem: --mode misuse scope check (negative finding)
Category: H — documentation inconsistency check, negative result
Severity: S0
Confidence: high

Finding: repo-wide grep for --mode across all *.ps1 files found exactly one match (DOC-01's own
  file) — the bug is isolated, not repeated elsewhere in the deployment tooling.
```

## 13. Experiment-Impact Assessment (consolidated)

| Finding | Experiment Impact | Why |
|---|---|---|
| OBS-01 (goal linkage dropped) | POSSIBLE | Limits what future analysis of gateway_audit can answer about goal-directed action; doesn't change any conclusion already drawn |
| OBS-02 (semantic_memory upsert) | DIRECT | Corrects the precise wording of an already-drawn evidentiary claim in Tasks 63-66 (does not overturn the H4 conclusion itself) |
| TEST-01 (episode_pattern untested) | DIRECT | The one confirmed behavioral-change event's explanation rests on source reading alone, not independent test verification |
| ERR-01 (obsidian timeout misclassified) | DIRECT | Explains and validates why every observation report had to manually filter this exact noisy log line; no correctness impact |
| PERF-01/02, PLAN-01, TEST-02, SEC-01, DOC-01/02, OBS-03/04/05 | NO EXPERIMENT IMPACT / POSSIBLE (minor) | Do not bear on any hypothesis (H1-H10) evidence already gathered or on experiment safety |

**No finding in this audit calls into question the safety, validity, or any specific evidentiary
claim's TRUTH from Tasks 62-69** — the DIRECT-impact findings are wording/methodology corrections and
coverage gaps, not overturned conclusions.

## 14. Prioritized Post-Experiment Remediation Queue

1. **ERR-01** (obsidian_sync timeout misclassification) — trivial fix, meaningfully reduces log
   noise for all future observation work. Highest value-for-effort.
2. **TEST-01** (episode_pattern behavioral test) — directly strengthens the experiment's own
   headline finding's evidentiary foundation.
3. **OBS-01** (goal_id persistence) — schema addition, moderate effort, unlocks a genuinely new class
   of post-hoc analysis query.
4. **DOC-01** (install_service.ps1 bug) — trivial fix, only matters if NSSM is ever revisited as a
   hosting mechanism.
5. **PLAN-01** (plan-store query helper) — moderate effort, would close a long-standing, repeatedly-
   cited observability gap.
6. **PERF-01** (CounterfactualMemory singleton) — low urgency; real but small overhead.
7. **PERF-02** (retention/pruning) — only becomes urgent for a multi-week+ deployment.
8. **TEST-02, OBS-03/04/05** — lower-priority coverage/observability improvements.

## 15. Issues Explicitly Deferred Until After the 7-Day Experiment

All 21 findings in this report. None were acted on. This audit's own explicit position (§6, LEARN-01)
is that the experiment's central negative-evidence finding (the `analyze_progress` stall) should NOT
be "fixed" even after the experiment — it is the subject of study, not a defect, unless a genuinely
separate future investigation is scoped to understand decision_engine's candidate-generation logic on
its own terms.

## 16. Unknowns Requiring Future Runtime Evidence

- OBS-05: whether suggestion_queue/hypothesis_engine activity correlates with any downstream decision
  — not located within this audit's search; needs a dedicated follow-up read of the actual consumer
  code (likely district-level, not core/loop/).
- PERF-03 (unconfirmed): unbounded-queue risk in core/event_bus/worker_pool.py — not completed within
  this audit's time budget; no finding made either way.
- TEST-03 (unconfirmed): full coverage characterization of PolicyMemory/decision_engine's own
  dedicated test files was not completed — only anticipation.py's test file was read in full.
- Step 7 (agent/district contract audit) received only light, illustrative coverage given the
  codebase's scale (133+ agent files) — a dedicated future pass would be needed for genuine coverage
  claims there.
- Whether NSSM/service-hosted VECTOR would genuinely lose camera/mic/GPU/Ollama access (Task 68's own
  reasoned-but-untested claim) remains unverified by any runtime test.

---

## 17. Final Integrity Check

1. **No production .py files modified:** confirmed — this task performed Read/Grep/Glob operations
   only; zero Edit/Write calls against any `.py` file.
2. **No production configuration modified:** confirmed.
3. **No experiment database/state modified:** confirmed — no `data/*.db` file was opened by this task
   or its fork, at any point, per the explicit rule.
4. **VECTOR not started/stopped/restarted:** confirmed — no process-management command of any kind
   was issued.
5. **No synthetic stimulus sent:** confirmed.
6. **Only the intended Markdown report created/modified:** confirmed — exactly one new file,
   `VECTOR_TECHNICAL_KNOWLEDGE/71_OFFLINE_TECHNICAL_AUDIT.md`; no existing file was touched.

---

## FINAL RESPONSE

- **Audit completed:** yes.
- **Number of findings:** 21 (ERR-01, PERF-02, OBS-01, PERF-01, OBS-02, LEARN-01, SEC-01, TEST-01,
  TEST-02, DOC-01, DOC-02, PLAN-01, OBS-03, OBS-04, OBS-05, PERF-03(unconfirmed), TEST-03(unconfirmed),
  plus the fork's underlying contributions folded into the numbered items above).
- **Number of confirmed defects (Category A):** 2 (ERR-01, PERF-02, DOC-01 — three, correcting count:
  **3 confirmed defects**: ERR-01, PERF-02, DOC-01).
- **Number of suspected defects (Category B):** 1 (PERF-01).
- **Highest-severity finding:** S2 (ERR-01, OBS-01, OBS-02, TEST-01, DOC-01 — none exceed S2; no S3+
  finding exists in this audit).
- **Finding that could affect interpretation of Segment 2:** OBS-02 (semantic_memory row-count vs.
  UPSERT-activity distinction) and TEST-01 (episode_pattern's evidentiary foundation rests on source
  reading, not independent test verification) — both are wording/rigor corrections to how existing
  and future reports should describe evidence, not overturned conclusions.
- **Exact file created:** `VECTOR_TECHNICAL_KNOWLEDGE/71_OFFLINE_TECHNICAL_AUDIT.md`.
- **Running experiment (Segment 2) touched:** No — confirmed via §17.
- **Production code/configuration modified:** No — confirmed via §17.
