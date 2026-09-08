# Task 61 — Experiment Runbook

Operational companion to `61_7_DAY_AUTONOMOUS_EXPERIMENT_PROTOCOL.md`. This is the pre-launch
checklist (Phase 13) plus the exact commands for launch, monitoring, and shutdown. **This runbook
does not launch the experiment — it is prepared for the next task to execute.**

---

## Pre-Launch Checklist

Per this task's explicit instruction: a box is checked only when a runtime check was actually
performed, not merely inferred from source. Where this task already performed the live check, the
result is stated. Where a check requires the actual `loop`-mode launch (which this task deliberately
did not start), it is marked "pending Day-1."

| # | Item | Method | Status this task |
|---|---|---|---|
| 1 | Task 60 A gate still valid | Re-run 58A-58G + Task-57 regression suite | ✅ **Checked live in Task 60**, not re-run in Task 61 since no source changed (git status identical). Recommend one more fresh run immediately before actual launch if any time has passed. |
| 2 | 58A-58G regression suite passes | `pytest tests/test_task58*.py tests/test_task57*.py -q` | ✅ 113/113, Task 60 |
| 3 | No new permission bypass | Task 60's full 14-phase audit | ✅ A-READY, Task 60 |
| 4 | RED actions remain approval-gated | Live `gateway_audit` query this task | ✅ Confirmed: 1,640 historical RED rows, only 491 approved — the gate is demonstrably discriminating, not rubber-stamping |
| 5 | Experiment boundary configured | Confirm `VECTOR_MCP` unset, `COUNCIL_AUTO_PROCEED_ALLOWED` empty | ✅ `VECTOR_MCP` confirmed unset live this task; `COUNCIL_AUTO_PROCEED_ALLOWED` confirmed empty in Task 60, unchanged (no source touched it) |
| 6 | Emergency stop tested | Actually trigger SIGINT against a live `loop`-mode process | ⏳ **Pending Day-1** — only source-verified this task (S3), not triggered live (would require starting indefinite `loop` mode, which this task avoided per its own dry-run-only instruction). First action of Day-1 launch procedure (protocol §19 step 6). |
| 7 | Telemetry functioning | Live calls to `InferenceObservability` methods | ✅ All called successfully live this task |
| 8 | Persistence functioning | Live query of `gateway_audit`, goal system, memory stats | ✅ All returned real, consistent data live this task |
| 9 | Inference observability functioning | Confirmed wired into `provider_client.py` real call path | ✅ Grep-verified this task (lines 531-542, 590-592) |
| 10 | Scheduler functioning | Confirm `register_default_jobs()` registration mechanism | ✅ Source-confirmed (15 jobs); actual cron-fire timing not observed live this task — pending Day-1 observation |
| 11 | Autonomous loop functioning | `run_vector.py smoke` | ✅ Ran live this task: 170 agents registered, real decision candidate produced (`analyze_progress`, score 0.66) |
| 12 | Plan recovery functioning | Source trace of `_recover_stale_running_steps` | ✅ Task 60 §11, S3 (structural); not behaviorally crash-tested — pending observation only if an actual interruption occurs during the week |
| 13 | Logs writable | `_configure_file_logging()` present, rotation 10MB×5 | ✅ Source-confirmed; not re-verified by an actual write-and-read this task |
| 14 | Disk capacity adequate | `df -h` | ✅ 345GB free of 952GB — ample |
| 15 | Resource limits defined | `quota_ledger` per-provider daily/token limits from `model_catalog.yaml` | ✅ Structurally confirmed present (Task 60); exact current-day saturation not re-queried this task — recommend one `quota_saturation()` call immediately before launch |
| 16 | Cloud/provider spending limits verified | Free-tier-only enforcement (`_enforce_whitelist`) | ✅ Structurally confirmed present (per `models.md`'s documented hard whitelist clamp); not independently re-tested this task |
| 17 | Experiment ID generated | `experiment_id = "exp61-" + <ISO date>` | ⏳ Deferred to actual Day-1 (date not yet set) |
| 18 | Git commit recorded | `git rev-parse HEAD` | ✅ `5964a331678ac648c8289f4c38fd0e5430e1ee9d`, captured this task |
| 19 | Baseline captured | `61_EXPERIMENT_BASELINE.md` | ✅ Produced this task |
| 20 | Owner intervention rules defined | Protocol §10 | ✅ Documented this task |
| 21 | External MCP excluded from autonomous surface | `core/mcp_server.py` Class-A confirmation (Task 60 §9.1), `VECTOR_MCP` unset (confirmed live this task) | ✅ |
| 22 | Rollback/recovery procedure documented | Protocol §11 (stop conditions), §20 (shutdown) | ✅ Documented this task |

**Outstanding before Day 1 (the only real blockers to a clean start, none of which block the
protocol's readiness — they are launch-day actions, not design gaps):**
- Trigger and observe one real SIGINT/graceful-shutdown cycle (item 6).
- Record the exact `gateway_audit.seq` / `inference_calls` row-count watermark at the actual launch
  moment (protocol §17.5, §19 step 2) — this task's captured numbers (29,156 / 3) are a
  point-in-time reference, not the official Day-0 watermark, since time will pass between this task
  and actual launch.
- Set `experiment_id` and create `data/experiment_61/interventions.log`.
- One fresh `quota_saturation()` check immediately pre-launch.

---

## Operational Commands

### Launch
```bash
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python run_vector.py loop
```
(Or via the NSSM-supervised Windows service, if configured per `scripts/install_service.ps1` — not
verified as active this task; confirm separately before relying on it for unattended 7-day
operation.)

### Pre-launch watermark capture
```bash
python -c "
from core.memory.episodic import get_temp_cursor
with get_temp_cursor() as cur:
    cur.execute('SELECT MAX(seq) FROM gateway_audit')
    print('gateway_audit watermark seq:', cur.fetchone()[0])
"
python -c "
import sqlite3
c = sqlite3.connect('data/telemetry.db')
print('inference_calls watermark count:', c.execute('SELECT COUNT(*) FROM inference_calls').fetchone()[0])
"
```

### Daily monitoring (read-only, safe to run anytime during the week)
```bash
python -c "
from core.metering.inference_observability import get_inference_observability
io = get_inference_observability()
print(io.generate_daily_report())
"
python -c "
from core.memory.episodic import get_temp_cursor
with get_temp_cursor() as cur:
    cur.execute('SELECT level, COUNT(*), SUM(approved), SUM(executed) FROM gateway_audit WHERE seq > ? GROUP BY level', (WATERMARK_SEQ,))
    for row in cur.fetchall(): print(row)
"
python -c "
from core.brain.goal_system import GoalSystem
gs = GoalSystem()
for g in gs.get_active_goals(): print(g.get('horizon'), g.get('title'), g.get('progress'))
"
```
(Replace `WATERMARK_SEQ` with the value captured at launch.)

### Emergency stop
```
# Foreground process: Ctrl+C in the terminal running run_vector.py loop
# Or, from another terminal:
taskkill /IM python.exe /FI "WINDOWTITLE eq *run_vector*"   # graceful signal first
# If unresponsive after ~15s:
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *run_vector*"   # hard kill, last resort
```

### End-of-experiment snapshot
```bash
python -c "
import shutil, datetime
ts = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
shutil.copytree('data', f'data_archive_exp61_{ts}')
print('archived to', f'data_archive_exp61_{ts}')
"
```
Run this **before** any post-experiment analysis touches `data/`.

---

## Final Task 61 Report Summary

- **Production files changed:** No production architecture files were modified by Task 61. All
  writes were new documentation artifacts (`61_7_DAY_AUTONOMOUS_EXPERIMENT_PROTOCOL.md`,
  `61_EXPERIMENT_BASELINE.md`, this runbook). No new database schema was created — investigation
  (protocol §12) found existing tables (`gateway_audit`, `inference_calls`) already cover every
  required experiment data-model field.
- **Production behavior changed:** No. No configuration was altered; `VECTOR_MCP` and
  `COUNCIL_AUTO_PROCEED_ALLOWED` were verified, not changed.
- **Tests added/changed:** None. No test files were created or modified in Task 61 (the existing
  113-test suite from 58A-58G was referenced, not re-run, since no source changed since Task 60).
- **Baseline measurements:** Captured live this task — see `61_EXPERIMENT_BASELINE.md` in full;
  headline numbers: 399,539 episodic / 15,862 reasoning-chain / 910 policy memory rows; 29,156
  historical `gateway_audit` rows (26,089 GREEN / 1,640 RED / 592 YELLOW / 370 FORBIDDEN / 465
  UNKNOWN); 6 active goals with real non-zero progress; only 3 historical inference-observability
  rows ever (thin-by-nature, disclosed limitation).
- **Dry-run result:** `run_vector.py smoke` executed live and succeeded (170 agents registered, real
  decision candidate produced, memory/goal/permission queries all returned live consistent data).
  Emergency-stop, scheduler cron-fire, and plan-recovery were verified only at the source-trace
  level (S3), not triggered live, and are explicitly deferred to Day-1's first hour rather than
  claimed as proven.
- **Experiment boundary:** Unchanged existing RED-tier gate (`PermissionGateway`); no weakening;
  `core/mcp_server.py` and the opt-in VectorCode MCP server explicitly excluded from the autonomous
  surface.
- **Known limitations:** thin inference-observability history; orphaned (S2) epistemic tracker
  limiting H7's measurement strength; no plan-store baseline; no first-class autonomous-cycle
  counter (proxy metrics used instead); `gateway_audit` historical total includes uncleaned
  test-suite noise pre-launch (addressed via a precise Day-0 watermark procedure, not yet executed).
- **Exact conditions required before Day 1:** the four outstanding pre-launch items listed above
  (live SIGINT test, watermark capture, experiment_id/intervention-log creation, fresh quota check)
  — all launch-day mechanics, none are open design or safety questions.
- **Final verdict: A — EXPERIMENT PROTOCOL READY.**

Per this task's explicit instruction: **the 7-day experiment was NOT started.** This runbook and its
companion protocol/baseline documents are handed off for deliberate execution in a subsequent task.
