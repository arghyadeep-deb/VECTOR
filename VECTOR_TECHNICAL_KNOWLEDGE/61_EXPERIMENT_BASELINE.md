# Task 61 — Experiment Baseline

All measurements below were captured live against the running repository during Task 61, via
read-only queries and one `run_vector.py smoke` run. No artificial autonomous tasks were injected.
Where a baseline could not be measured from existing telemetry, that is stated explicitly rather
than estimated.

**Capture timestamp (this task):** 2026-09-02, ~23:50-23:51 local (system clock).
**Git HEAD at capture:** `5964a331678ac648c8289f4c38fd0e5430e1ee9d`

---

## 1. Repository Health

- `git rev-parse HEAD`: `5964a331678ac648c8289f4c38fd0e5430e1ee9d`
- `git log -3 --oneline`:
  ```
  5964a3316 disable widget:close and workspace close sounds on standby
  dbc360990 disable closeWorkspace sound on lock/standby
  0116d52e3 disable standby lock sound per user request
  ```
  (Confirms recent commit history is unrelated frontend/UX work, not security-relevant — the
  58A-58G remediation diffs remain **uncommitted** on top of this HEAD.)
- `git status --short`: 124 modified/untracked paths — the full list matches Task 60 §16's
  disclosure exactly (58A-58G production edits + unrelated pre-existing owner work: intent
  classification pipeline, `core/metering/inference_observability.py`, `core/runtime/plans.py`,
  various `docs/`/`VECTOR_TECHNICAL_KNOWLEDGE/` artifacts).

## 2. Test Status

113/113 passing (`tests/test_task58a_*.py` through `test_task58g_*.py` + `test_task57_*.py`),
re-confirmed fresh in Task 60, not re-run again in Task 61 since no source changed between the two
tasks. Four known, non-security, pre-existing baseline test failures remain (Task 60 §13):
`test_proceed_high_confidence_returns_proceed` (council-defer-by-design), one mock-signature bug in
`test_permission_gateway.py`, two intent-matcher embedding-drift cases.

## 3. Inference Metrics

Live query via `InferenceObservability`:

```
daily_summary() for 2026-09-02:
  total_calls: 0, total_tokens: 0, ollama_calls: 0, cloud_calls: 0,
  autonomous_calls: 0, user_calls: 0, error_calls: 0, avg_latency_ms: 0
hourly_snapshot(): {'total_calls': 0, 'total_tokens': 0, 'avg_latency_ms': 0,
                     'ollama_calls': 0, 'error_calls': 0, 'period': 'last_hour'}
alert_check(): []
```

Historical `inference_calls` table (`data/telemetry.db`), full lifetime:
```
COUNT(*) = 3, MIN(utc_date) = '2026-09-01', MAX(utc_date) = '2026-09-01'
```

**Interpretation:** the instrumentation is confirmed wired into the real call path
(`core/inference/provider_client.py:531-542` success path, `:590-592` failure path — grep-verified
this task) — this is S3, runtime-reachable, not merely S1/S2. But it has recorded essentially no
real traffic yet: 3 calls total, ever, all from the day the file was created (2026-09-01). **This
baseline is thin by nature, not by measurement failure.** The 7-day experiment is this
instrumentation's first substantial dataset.

## 4. Autonomous Cycle Frequency

**Not directly measurable from existing telemetry** — `autonomous_loop.py` has no first-class
per-cycle counter distinct from the gateway/memory activity those cycles produce. Proxy measures
used instead (both directly measurable):

- `gateway_audit` total historical rows: **29,156**
- Episodic memory total rows: **399,539**

Neither is a "cycles/day" figure on its own; both will be delta-measured Day-1→Day-7 as the
practical substitute, per the main protocol document §6 (H1) and §17 (limitation #4).

## 5. Goal / Plan Activity

Live query, `GoalSystem.get_active_goals()`:

```
active goals: 6
  LONG   Maintain KIIT attendance above 75%                              progress=0.0
  MID    Complete VECTOR Phase 1 — 8 core districts                      progress=0.25
  MID    First ₹1 of product revenue from a stranger — wedge: AI cont... progress=0.076
  MID    Complete Karpathy playlist — 30 min/day                         progress=0.076
  LONG   Equation portfolio: graduate product 1 (₹1L+/month × 3 month... progress=0.076
  LONG   KIIT placement preparation — DSA + System Design                progress=0.076
```

(7 goals loaded from memory per the goal-system's own startup log; 6 returned as currently active —
consistent with the system's documented expiry/pruning behavior.)

**Plan-store summary (created/completed/failed/stalled counts): NOT captured this task.**
Disclosed explicitly as a baseline gap in the main protocol document (§8, §17.3) rather than
estimated or omitted silently.

## 6. Memory Activity

Live from `run_vector.py smoke`'s real `memory_stats` output:

```
episodic_memory:   399,539
semantic_memory:     2,034
policy_memory:          910
reasoning_chains:   15,862
skill_memory:           169
agent_history:       1,070
```

This confirms VECTOR is a long-running, substantially-used instance, not a fresh install — the
7-day experiment measures incremental change against this large existing base, not growth from
zero.

## 7. Learning Activity

`data/counterfactual.db` file size: **9.8MB** (Aug 12 mtime) — used as a rough proxy for
accumulated historical learning-artifact volume; no row-level count or before/after decision-score
comparison was performed this task (that comparison is inherently a within-experiment measurement,
not a baseline one).

`data/meta_cognition.db`: 520KB (Aug 13 mtime).
`data/person_models.db`: 60KB.
`data/suggestion_queue.db`: 36KB.

## 8. Permission Activity

Live query, full `gateway_audit` table:

```
total rows: 29,156

level        count   approved   executed
FORBIDDEN      370          0          0
GREEN       26,089     25,937     25,937
RED          1,640        491        377
UNKNOWN        465          0          0
YELLOW         592        426        426
```

Most recent 10 rows at capture time (all timestamped 2026-09-02T18:12:...+00:00 — these are from
Task 60's own regression-test run earlier the same day, not autonomous-loop activity; flagged
explicitly as pre-experiment test noise per the main protocol's §17.5):

```
play_music       GREEN  approved=1 executed=1
hf_train         RED    approved=0 executed=0
launch_terminal  RED    approved=0 executed=0
vt_backtest      RED    approved=0 executed=0  (x4 more, mixed approved=0/1)
```

**This table's historical total (29,156) includes an unknown proportion of test-suite-generated
rows accumulated across this session's own regression runs.** The exact Day-0 watermark (the
`seq` value at actual experiment launch) — not this task's capture moment — is what the real 7-day
delta measurement must use (protocol §17.5, §19 step 2).

## 9. Resource Consumption

- Disk: 952GB total, 607GB used, **345GB available (64% used)**.
- `data/` directory total size: **1.1GB**.
- Individual DB file sizes at capture:
  ```
  contacts.db            20KB
  counterfactual.db     9.8MB
  epistemic.db           20KB
  execution_ledger.db    12KB
  learning_courses.db    24KB
  meta_cognition.db     520KB
  person_models.db       60KB
  scheduler.db            20KB
  suggestion_queue.db     36KB
  tasks.db                12KB
  telemetry.db           204KB
  vector_memory.db          0 (empty — not the active episodic store; see below)
  ```
  Note: the active, encrypted episodic-memory store is opened via
  `core.memory.db_utils.configured_db_path()`, not the plainly-visible `vector_memory.db` (0 bytes,
  unused placeholder) — the real 399,539-row episodic store lives at whatever path that resolver
  returns, confirmed functioning via the live smoke-test query but its exact on-disk filename was
  not independently re-derived this task (out of scope; functionally verified instead).

## 10. Known Warnings at Baseline

1. Four pre-existing, non-security test failures (§2).
2. `epistemic_tracker.py` is S2 (orphaned — not called from `autonomous_loop`), per
   `phase_status.md`'s own tracked correction and re-confirmed in this task's component table.
3. `inference_observability`'s thin historical dataset (§3).
4. No plan-store baseline captured (§5).
5. `gateway_audit`'s historical total includes test-suite noise not cleanly separable from real
   autonomous activity without a precise Day-0 watermark (§8).

None of the above are new findings — all are either carried forward from Task 60 or are honest
disclosures of measurement gaps specific to this baseline capture.
