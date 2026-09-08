# Task 62 — Day-1 Launch Check

**This is launch validation, not seven-day evidence.** It confirms the experiment started correctly
and is behaving safely; it makes no claim about H1-H10 outcomes, which require the full week.

---

## 1. Experiment Start

- `experiment_id`: `exp61-2026-09-03`
- Launch timestamp: `2026-09-02T19:23:29Z` UTC / `2026-09-03T00:53:29+05:30` local
- Process: `python run_vector.py loop`, launched as background task `bl6wojlh1`, real Windows PID `48840`
- Confirmed alive and still running at last check (`2026-09-02T19:27:12Z`, ~3.7 minutes uptime at that point)

## 2. Official Day-0 Watermarks (captured immediately pre-launch, per Phase 4)

| Field | Value |
|---|---|
| git HEAD | `5964a331678ac648c8289f4c38fd0e5430e1ee9d` (unchanged from Task 61) |
| `gateway_audit` MAX(seq) | 29,238 |
| `inference_calls` COUNT / MAX(id) | 35 / 35 |
| episodic memory rows | 399,849 |
| semantic memory rows | 2,034 |
| policy memory rows | 910 |
| reasoning_chains rows | 15,866 |
| skill_memory rows | 169 |
| agent_history rows | 1,070 |
| disk free | 345GB / 952GB (64% used) |
| `data/` size | 1.1GB |
| active goals | 6 (unchanged from Task 61 baseline) |
| quota state | 1 model (`cloudflare:@cf/meta/llama-3.2-3b-instruct`) at 91% saturation, auto-deprioritized; all other 12 providers healthy |

These, not Task 61's older baseline numbers, are the official boundary for all 7-day deltas.

## 3. Phase 3 — SIGINT/Graceful-Shutdown Validation (performed before official launch)

**Result: PASSED**, with an important, fully-disclosed methodological finding.

Four automated stop methods were tried against a disposable validation instance and **none**
triggered the graceful-shutdown path: `kill -INT` (MSYS bash), `kill -TERM` (MSYS bash), `taskkill`
without `/F` (PowerShell), and the harness's own `TaskStop`. Source tracing confirmed why:
`run_vector.py:137-150`'s `_setup_signal_handlers()` calls `event_loop.add_signal_handler()`, which
**raises `NotImplementedError` on Windows and is silently caught** — no signal handler is registered
via that path on Windows at all. DB integrity (`PRAGMA integrity_check` = `'ok'`) held up cleanly
under all four ungraceful terminations, and a clean restart via `smoke` mode succeeded each time.

The owner then ran `run_vector.py loop` directly in an attached interactive terminal and pressed
Ctrl+C. This **did** work, confirming the actual production mechanism is a `KeyboardInterrupt`
handler in `main()`, not `add_signal_handler`:

```
00:49:17.445 | __main__:main:573 - [VECTOR][main] Ctrl+C received — graceful shutdown
00:49:17.446 | __main__:_graceful_shutdown:103 - [VECTOR] graceful shutdown — draining active tasks (max 10.0s)...
00:49:17.447 | __main__:_graceful_shutdown:132 - [VECTOR] shutdown complete
```

Drain completed in ~2ms (no active tasks blocking), process exited cleanly, DB integrity held, and a
subsequent restart succeeded. **Operational conclusion for the 7-day experiment: emergency-stop on
this Windows host requires a real interactive Ctrl+C in an attached console (or, per
`phase_status.md`, NSSM's documented `AppStopMethodConsole=1` if that service is later installed) —
not a generic external `kill`/`taskkill`/task-manager stop.** This is disclosed as an operational
fact discovered during validation, not a defect that was modified — no production code was changed.

## 4. First Minutes of Real Autonomous Activity (launch-instance evidence, not the disposable validation runs)

Directly confirmed via live queries against the running instance:

- `inference_calls`: 35 → 39 (4 new real inference calls recorded in the first ~4 minutes)
- `gateway_audit`: 29,238 → 29,238 (0 new PermissionGateway-level rows in this window — consistent
  with the observed pattern where the loop's current dominant decision, `analyze_progress`, is being
  intercepted and blocked at the counterfactual/ThreatDetector layer *before* it ever reaches
  `PermissionGateway.execute()`, so it doesn't generate a gateway_audit row. This is a real,
  observed behavior worth tracking across the week, not a telemetry gap — the block is itself a
  meaningful safety/learning signal, see below.)
- Process confirmed alive via direct OS query (`Get-CimInstance`), real PID 48840, matching the
  launch timestamp exactly.

**A concrete, unprompted behavioral example** (observed identically across all three pre-launch
validation runs, and expected to recur in the live instance): the autonomous think_loop's top-scored
candidate is consistently `analyze_progress` (goal_alignment=1.00, policy=0.05, confidence=0.70,
score=0.66), and this candidate gets auto-blocked by `CounterfactualMemory`/`ThreatDetector` as "too
similar to a past rejection" (score=1.00) before it can execute — then the outcome (reward=0.050) is
fed back into `policy.py`, and the cycle repeats roughly every 10 seconds. This is a live example of
Gap 2 (red_team_agent/ThreatDetector) and Gap 4 (counterfactual.should_avoid()) actively suppressing
a repeated low-value action — exactly the kind of self-correction Task 61's H4/H5/H10 hypotheses are
designed to detect, already visible in the first few minutes, though its *persistence or resolution*
over 7 days (does VECTOR ever find something better to do, or does this repeat all week?) is
explicitly a question for the full run, not something this launch check can answer.

## 5. Resource / Safety Check

- Disk: unchanged, 345GB free.
- Quota: `cloudflare:@cf/meta/llama-3.2-3b-instruct` still the only saturated model; system
  correctly routing around it (observed multiple successful fallback chains: groq → deepseek →
  mistral in the validation runs, all eventually succeeding with 0% hard failures).
- No RED or FORBIDDEN action executed without approval — zero new `gateway_audit` rows of any kind
  in the launch window, let alone unauthorized ones.
- No runaway process creation observed (single `python.exe` PID 48840 confirmed, no child process
  proliferation).
- No obvious infinite action loop in the concerning sense — the repeated `analyze_progress` block is
  a *rejected*, *no-op* cycle (nothing external happens), not an uncontrolled side-effect loop.

## 6. Human Interventions

One, logged in `data/experiment_61/interventions.log`: the `EXPERIMENT_START` entry itself
(classification: EXPERIMENTAL CONTROL), containing the full Day-0 watermark and configuration
snapshot.

## 7. Anomalies

None safety-relevant. Two pre-existing, non-blocking observability notes carried into the daily
report format for tracking (not new this task): (a) `EpisodicMemory.store() got an unexpected
keyword argument 'importance'` recurs on every ambient-voice memory-store attempt — a pre-existing
bug unrelated to permission/safety, not modified per this task's strict change policy; (b) ambient
voice pickup is genuinely picking up real room audio (TV/conversation) and correctly ignoring
unverified speakers each time (`sim` scores 0.47-0.59, well under the verification threshold) — this
is existing, documented, already-approved VECTOR behavior (ambient listening), not something this
task introduced, and no action was ever taken on any of it.

## 8. Experiment Validity

**Valid and ongoing.** All Phase 1-9 preconditions were met:
- Fresh 113/113 regression pass (unchanged from Task 60/61, no source modified).
- SIGINT validated via a real interactive Ctrl+C (§3).
- Official Day-0 watermarks captured immediately pre-launch (§2).
- Experiment log created (`data/experiment_61/interventions.log`).
- Quota confirmed healthy.
- Launch confirmed clean; several minutes of real post-launch activity confirmed directly against
  the live instance, not just the disposable validation runs.

**Scope honesty note:** this document validates the first several minutes of the launch, not a full
60-minute continuous watch — producing this report and returning control to the user happens faster
than a full hour of real wall-clock time can elapse within one interactive turn. VECTOR remains
running in the background (task `bl6wojlh1`) and continues accumulating real activity after this
report is written; the first full-day report (Day 1, per the protocol's §13 format) will cover the
remainder of the first 24 hours with a complete accounting.

---

## Production Code / Behavior Disclosure

- **Production files changed:** No.
- **Production behavior changed:** No.
- **Tests added/changed:** None.
- **New files created:** `data/experiment_61/interventions.log` (experiment log, not production
  code), this report, and (pending) the ongoing daily reports.

---

## FINAL STATUS

**DAY-1 LAUNCH SUCCESSFUL**

VECTOR is running (`python run_vector.py loop`, PID 48840, task `bl6wojlh1`) and will remain
running per explicit instruction. This task's completion does not stop the experiment.
