# RG-0 FROZEN BASELINE

## 1. Repository

- **HEAD:** `60acc693697da6f2397c45382e231c8ccfd3fca2` — confirmed exact match to the mandated baseline.
- **Branch:** `production-hardening-complete`
- **Status:** clean except 5 pre-existing untracked items, all confirmed unrelated to VECTOR's own history (external, concurrent activity from another tool — none created, modified, or touched during RG-0):
  - `.claude/settings.local.backup-2026-09-14.json`
  - `docs/CODEX_VECTOR_V1_HANDOFF.md`
  - `docs/VECTOR_FORENSIC_AUDIT_REPORT_2026-09-15.md`
  - `docs/VECTOR_OS_LONG_TERM_VISION.md`
  - `tools/vector_dev_orchestrator/`
- **Worktrees:** 13 stray entries under `.vector_dev_worktrees/`, all correlated with the same unrelated external tool (12 at `830eb27b5`, one at `fe89038b5` — a real commit not on this branch's ancestry, itself an artifact of that same external tool's own automated commits). None inspected further; none touched.
- **R24/R25/R26 ancestry:** `git merge-base --is-ancestor` independently confirms `830eb27b5` (R24), `473fd22c5` (R25), and `789ca61a0` (R26) are all real ancestors of HEAD.

## 2. Runtime

- **VECTOR running:** **NO.** Process inspection (`Get-CimInstance Win32_Process`, both a targeted pattern match and a broad `python`-name scan) found no `run_vector.py`/`AutonomousLoop`/VECTOR-API process. Only two unrelated `pythonw.exe` processes belonging to a separate "AI video maker" worker-agent tool were present — not VECTOR.
- **Normal launch command:** `python run_vector.py api --host 0.0.0.0 --port 8000`, run from `scripts/vector_autostart.bat` (the real, owner-installed Windows-Startup launcher). This is confirmed to be THE production entry point (`run_vector.py`'s own code comment: "the three launch paths do not agree on setting VECTOR_API_RUN_LOOP themselves... this default does NOT belong in .env").
- **Working directory:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase`
- **Environment set by the launcher:** `VECTOR_API_RUN_LOOP=1`, `VECTOR_ENV=production`
- **Autonomous loop enabled by this command:** YES — `mode="api"` in `run_vector.py::main()` sets `os.environ.setdefault("VECTOR_API_RUN_LOOP", "1")` before starting the API, and the script's own comment confirms "the api server also runs the full autonomous brain."
- **Expected shutdown:** not scripted in `vector_autostart.bat` itself (no matching stop script found in this pass); the codebase's own prior NSSM-service documentation (`phase_status.md`) references `AppStopMethodConsole=1` (CTRL+C) as the graceful-shutdown convention, but this repo is NOT currently running under NSSM per this launcher — shutdown would be a direct process kill or CTRL+C of the console.
- **Expected persistent logs:** `%USERPROFILE%\.vector_ca\logs\vector_autostart.log` (rotates to `.log.1` past 50MB).
- **Relevant DB paths:** `vector_memory.db` (repo root, SQLCipher-encrypted — episodic/semantic/policy/reasoning-chains/agent-history/causal graph), `data/counterfactual.db`, `data/epistemic.db`, `data/telemetry.db` (all plain SQLite). Merkle audit chain: `%USERPROFILE%\.vector_ca\audit\chain.jsonl`.
- **Last watchdog-triggered restart:** `2026-08-09 00:01:22` (`watchdog_last_restart.marker`) — over a month stale relative to today, consistent with VECTOR having been deliberately left stopped.
- Reject-list check: `VECTOR_TEST_DATA_DIR`/`VECTOR_DB_PATH` overrides, test configs, and any alternate DecisionEngine/lab path were NOT part of this launch command — confirmed clean.

## 3. Production Watermarks

All values obtained via SELECT-only queries against already-existing tables (no class constructors with write-capable side effects were instantiated: no `GoalSystem()`, `DecisionEngine()`, `AutonomousLoop()`, `CausalGraph()`, `PolicyMemory()`, or `EpistemicTracker()` object was created).

| # | Metric | Value |
|---|---|---|
| 1 | Episodic memory count | 471,862 |
| 2 | Semantic memory count | 2,170 |
| 3 | PolicyMemory row count | 1,194 |
| 4 | PolicyMemory sample-count distribution | see below |
| 5 | CounterfactualMemory counts | rejections=30,504, scenarios=0, outcomes=0 |
| 6 | CausalGraph node count | 2,175 |
| 7 | CausalGraph edge count | 82 |
| 8 | CausalGraph hit_count distribution | see §4 |
| 9 | EpistemicTracker claim counts | claims=54, staleness_events=911 |
| 10 | Reasoning-chain count | 16,429 |
| 11 | Agent-history count | 1,178 |
| 12 | Active goals | 8 active / 10 total (raw `semantic_memory` key `goals_v1`, `GoalSystem` never instantiated) |
| 13 | Active plans | 0 — `data/plans/` does not exist on disk |
| 14 | Registered agents | **N/A** — `AgentRegistry` is in-memory-only, non-persisted (established fact from this session's own R23 work); with VECTOR stopped, there is no current registration state to read, not merely an unmeasured one |
| 15 | Inference telemetry count | `inference_calls`=19,240, `telemetry`=1,746, `mining_stats`=0 |
| 16 | PermissionGateway audit sequence/count | 181,858 entries (`%USERPROFILE%\.vector_ca\audit\chain.jsonl`, append-only JSONL, read via plain line count — merkle_chain.py module never imported) |
| 17 | Scheduler state | **N/A** — APScheduler jobs are in-process only, no persisted job store found; meaningless while VECTOR is stopped |
| 18 | Disk free space | 289.1 GB free / 662.54 GB used (C:) |
| 19 | VECTOR data-directory size | `data/` = 1,026.8 MB; `vector_memory.db` (repo root, separate from `data/`) = 338.52 MB |

**PolicyMemory sample_count distribution (real, full):** 0→80 rows, 1→538, 2→217, 3→242, 4→3, 5→51, 6→1, 7→1, 8→18, 12→1, 13→1, 16→2, 18→1, 25→1, 29→1, 32→1, 50→1, 95→1, 118→1, 122→1, 124→1, 201→10, 380→1, 29164→19.

## 4. Causal Data

- **Nodes:** 2,175
- **Edges:** 82
- **hit_count distribution:** `{1: 82}` — **every single real edge has exactly 1 observation.**
- **Edges clearing the ≥3 observation gate:** **0**

This independently reconfirms, on freshly-queried live data, the exact finding R24/R25/R26's own reports repeatedly disclosed: real production accumulation has not yet cleared `CAUSAL_MIN_OBSERVATIONS`/`SIMULATION_MIN_OBSERVATIONS=3` anywhere. Both `_causal_factor()` and `_simulation_factor()` are, right now, neutral (`1.0`) for every real candidate in live operation. (Edge count grew from 80 at the time of the R26 final audit to 82 now — 2 new real edges accumulated from this session's own test runs in the interim, each still at hit_count=1, consistent with normal test/production activity, not a seeding action taken during RG-0.)

## 5. Cognitive Fingerprints (SHA-256)

```
core/config.py                        b1a72523e58b7ece72b5509ef204161fcd6640b93067489f8382152a3d45b691
core/loop/decision_engine.py          59d27c7fd0ffcc36ba78777102a25a5f70c6b4f06355c0a0b9a53aba2299487e
core/loop/autonomous_loop.py          9e017f4beaa5423e0fcc8d9db5023176ad55f8bc357add8806f39f039efdfe72
core/memory/causal_graph.py           e44d0aee58003ef9bc1a15c7c887a24fa99ca5e9431f8ffa1e98ec120705f498
core/memory/policy.py                 0339b3d5058f03453cb878077614e19498ed5b584f2982e0225de533a8b595a6
core/memory/counterfactual.py         017571d1c563d0b93ca5c0dedc9a179f6e5f512c3da442b970cb6bd20932dc52
core/brain/epistemic_tracker.py       e7aae7be3acfdd99360cb10d69e07f1de0d7f9a75ae6f0c61112d67d9c07cdda
core/brain/goal_system.py             b12be930f9394e7a795e83c609d641c9b61f93f264087c660ec5ad7f084e7baf
core/runtime/plans.py                 4cb6ccdede500a1e643f566254f752015d0ca73a54b0c074f4566e8a3064fe1d
core/city/governor.py                 60a2b6b57444dca2dc85bd4b9bd21cc07599b6d21818b015f36ebe8efdbaa82f
core/loop/permission_gateway.py       a5da77177219bfd6cf899630790c60d792451c9154d724bec2cea97ab617de15
```

*(each is a genuine SHA-256, 64 hex characters — a transcription error in an earlier draft of this table truncated each value by 2 characters; corrected here after RG-A's own pre-run fingerprint re-check caught the discrepancy and traced it to the report, not to any file change — re-verified byte-identical via independent digest-length check. PlanRunner lives in the same `core/runtime/plans.py` file already fingerprinted above.)*

## 6. Safety State

- **Permission configuration:** `core/loop/permission_gateway.py::PermissionGateway._classify()` remains, per this wave's own repeatedly-independently-confirmed finding, a pure static function of `action_type` against `core/config.py`'s static GREEN/YELLOW/RED/FORBIDDEN lists — untouched by R24-R26.
- **Environment variables (SET/UNSET only):**

| Variable | Status |
|---|---|
| `VECTOR_MCP` | UNSET |
| `VECTOR_API_RUN_LOOP` | UNSET (would be set to `1` only by the autostart launcher itself at run time) |
| `COUNCIL_AUTO_PROCEED_ALLOWED` | UNSET |
| `VECTOR_DB_KEY` | SET (value never read or printed) |
| `VECTOR_DB_PATH` | SET (value never read or printed) |
| `VECTOR_TEST_DATA_DIR` | UNSET |
| `VECTOR_DATA_DIR` | UNSET |
| `VECTOR_DOMAIN_ROUTING` | UNSET |
| `ANTHROPIC_API_KEY` | UNSET |
| `OPENAI_API_KEY` | UNSET |

No autonomy-elevating or authorization-bypassing flag is currently active in this idle-process environment; paid-cloud keys remain absent, consistent with the codebase's own documented "free-tier only at runtime" policy.

- **Known plan-step asymmetry status:** **STILL PRESENT, confirmed by direct re-read.** `AutonomousLoop._act_on_plan_step()`'s current source contains zero references to `CounterfactualMemory`, `should_avoid`, `ThreatDetector`, or `_scan_threats` — the pre-existing (R19-R20-era), explicitly-not-fixed-by-R26 gap remains exactly as documented.

## 7. Evidence Capture Matrix

| Signal | Class | Source |
|---|---|---|
| **Observation/Context** | | |
| Situation/context snapshot | A | `Candidate.context_snapshot`, persisted nowhere directly today but reconstructible per-decision from `reasoning_chain`; real-time only observable via live logging |
| Owner presence | B | `[VECTOR][decision_engine] Winner: ...` and reasoning_chain entries logged at decision time; not separately persisted |
| **Goals** | | |
| Active goal | A | `semantic_memory` key `goals_v1` (raw SELECT, as used in this RG-0 itself) |
| Generated immediate actions | D | Not persisted independently of the `Decision`/`reasoning_chain` record produced by the same `evaluate()` call — only observable live via log capture at runtime |
| Plan-derived candidates | C | `PlanStep.actual_outcome`/plan events, if `data/plans/plans.json` existed (currently does not) |
| **Decision** | | |
| decision_id / candidate_id | B | Logged at `evaluate()` time (`[VECTOR][decision_engine] Winner: ...`); not stored in a queryable table today |
| candidate action_type/source/params | D | Only exists in-process during `evaluate()`; not persisted as a row anywhere — capturable only via live log/telemetry hook |
| score / reasoning_chain (all 6 factors) | D | Same — real, computed, logged, but not persisted to a queryable table; `reasoning_chain` exists on the in-memory `Candidate` only |
| PolicyMemory contribution | C | Derivable from `policy_memory` before/after row read (real, persisted) |
| Epistemic contribution | C | Derivable from `data/epistemic.db::claims` before/after |
| R21/R22/R23 factors (counterfactual/situational/capability/workload) | D | Not separately persisted; only inferable via log capture at decision time |
| R24 causal factor | C | Derivable from `causal_edges` before/after (real, persisted, state-scoped) |
| R25 simulated_consequence | D | Computed pre-scoring, not persisted independently — same log-capture-only status |
| R6 staleness behavior | B | Logged explicitly (`"R6 staleness: '...' suppressed after N consecutive wins"`) when it fires; otherwise silent |
| **Action** | | |
| Selected winner | B | `[VECTOR][decision_engine] Winner: ...` log line |
| Governor route | B | `[VECTOR][governor] dispatch ... -> district (action_type)` log line |
| Agent selected | B | Same dispatch log line; also `agent_history`/HP-award logs |
| PermissionGateway classification | A/B | `[VECTOR][gateway] ... classified as TIER` log line; tier itself is a pure, re-derivable static function (class A) |
| Approval/refusal | B | Real log lines for RED-tier owner-confirmation / RedTeamAgent verdict |
| Execution result | B | District-agent-specific log line (e.g. `[VECTOR][git_bot] Status on '...'`) |
| **Outcome** | | |
| Raw result | D | In-process dict, not persisted verbatim |
| Computed reward | B | `[VECTOR][act] <action> -> <status> reward=X.XXX` log line |
| Causal edge write | A | `causal_edges`/`causal_nodes` before/after (real, persisted, queryable — as demonstrated in §3-4 above) |
| PolicyMemory update | A | `policy_memory` before/after (real, persisted, queryable) |
| Epistemic update | A | `data/epistemic.db::claims` before/after |
| CounterfactualMemory activity | A | `data/counterfactual.db::rejections` before/after |
| Reasoning-chain persistence | C | `reasoning_chains` table exists and is real (16,429 rows) but this session's own investigation never confirmed every decision writes to it — treat row-count delta as the safe signal, not per-decision content, without further confirmation |
| **Learning** | | |
| Before/after PolicyMemory state | A | Direct SELECT, as demonstrated |
| Before/after CausalGraph state | A | Direct SELECT, as demonstrated |
| Before/after Epistemic state | A | Direct SELECT, as demonstrated |
| **Inference** | | |
| Provider/model/task/domain/latency/success/fallback | A | `data/telemetry.db::inference_calls` (19,240 real rows) — appears to be a genuinely real, structured, already-persisted per-call log |

**Bottom line for Phase F:** the cleanest, lowest-risk observation strategy is (1) a running log-tail/file-sink capture of VECTOR's own real stdout/loguru output during any benchmark run (covers every B/D-classified signal above, including full `reasoning_chain` content, without touching any DB), combined with (2) before/after SELECT-only snapshots of the 5 real DB files (A-classified signals) exactly as performed in this RG-0. Nothing in this matrix requires implementing anything new (no D-classified item is proposed to be built).

## 8. Observer Effect Audit

The watermarking performed in this RG-0 pass:

1. Used `core.memory.episodic.get_db_connection()` (the project's own real, already-established connection factory) but issued **only `SELECT` statements** against it — no `INSERT`/`UPDATE`/`DELETE`, and no call to any class's own write method (`update_from_outcome`, `add_edge`, `record_rejection`, `_persist`, etc.).
2. Explicitly avoided instantiating `GoalSystem()` (its constructor can call `_persist()` and write seed goals if `semantic_memory` were ever empty) — the `goals_v1` fact was read via a raw `SELECT ... FROM semantic_memory WHERE key = ?` instead.
3. Explicitly avoided instantiating `DecisionEngine()`, `AutonomousLoop()`, `PolicyMemory()`, `EpistemicTracker()`, or `CausalGraph()` as objects — every count came from a direct `SELECT COUNT(*)`/`GROUP BY` against the already-existing tables those classes own.
4. Used plain, unencrypted `sqlite3.connect()` for `data/counterfactual.db`, `data/epistemic.db`, and `data/telemetry.db` — no project code imported for those three files at all.
5. Read the merkle audit-chain count via plain `wc -l`/file read against `chain.jsonl` — `core/audit/merkle_chain.py` was never imported, so its constructor's `mkdir(exist_ok=True)` never ran.
6. Read `watchdog_last_restart.marker` and `scripts/vector_autostart.bat` via plain file I/O — no script was executed.
7. All process/git/filesystem checks (`git rev-parse`, `git status`, `git worktree list`, `Get-CimInstance Win32_Process`, `Get-PSDrive`, `Get-ChildItem -Recurse` for size) are inherently read-only OS/VCS operations.
8. The one necessary exception: `import core.memory.episodic` (and, transitively, `core.config`) does run at Python-module-load time — this triggers `python-dotenv` loading and Pydantic settings validation (both pure in-memory), and logs a few `loguru` lines, but performs no disk write. `get_db_connection()`'s underlying `_create_tables()` call issues only `CREATE TABLE IF NOT EXISTS`/`CREATE INDEX IF NOT EXISTS` against an already-fully-migrated production schema — verified idempotent (every one of those tables and their expected columns already existed, confirmed by every subsequent SELECT succeeding against them without error).
9. `evaluate()` was never called, no `Candidate` was ever constructed, no LLM was invoked, `Governor.dispatch()` was never called, and no permission-tier state was read or written beyond the static, pure `PermissionGateway._classify()` function (which was not even invoked here — its purity was re-confirmed by source read only).
10. The one scratch Python file written for this pass (`test_tmp/rg0_watermark.py`) was deleted immediately after use, leaving no artifact in the repository.

## 9. Known Limitations (Phase I, A-F)

- **A (R24 — reward expectation, not formal causal inference):** CONFIRMED, current source unchanged since R24's own commit; `_causal_factor()` remains a `hit_count`-weighted blended average, no do-calculus/confounder-adjustment code exists anywhere in the diff or since.
- **B (R25 — retrieval-based, not generative world-model):** CONFIRMED, current source unchanged; `_simulate_consequence()` remains a real categorical distribution over already-observed outcome labels, no forward/generative rollout code exists.
- **C (natural data sparsity):** CONFIRMED and **independently re-verified on fresh live data** (§4): 0 of 82 real edges clear the ≥3 gate; every edge is still at `hit_count=1`.
- **D (generalization unproven):** CONFIRMED — no new evidence of cross-task generalization of the six-factor loop exists beyond R21's own separately-scoped, already-documented axis.
- **E (long-horizon unproven):** CONFIRMED — R26's own report explicitly limited its claim to one real, traceable scenario; nothing in this RG-0 pass changes that (VECTOR has not been run since before this session, per the stale watchdog marker).
- **F (plan-step safety asymmetry):** CONFIRMED STILL PRESENT (§6) — not repaired, as instructed.

## 10. Integrity Declaration

**No source file, test file, configuration file, database, memory record, goal, plan, policy row, causal edge, epistemic claim, or benchmark state was created, modified, or deleted during RG-0.**

Specifically confirmed:
- `git status --short` before and after this pass is byte-identical (still only the 5 pre-existing, unrelated untracked files).
- Direct row-count comparison shows the causal-edge count grew by 2 (80→82) relative to the R26 final-audit snapshot — attributable to normal test/production activity between that audit and now, not to any action taken during this RG-0 pass itself (RG-0 issued zero write statements; this was independently confirmed by re-running the identical watermark query twice with no change in between).
- The one file this session wrote (`test_tmp/rg0_watermark.py`, a read-only probe script) was deleted after use.
- No commit was made. No file was staged.

## 11. Final Verdict

**READY FOR REALITY GATE**
