# VECTOR — Cognitive Evolution Orchestrator Ledger

Master milestone ledger for the R12→ Understanding Engine program. Updated only from actual
execution results (audit reports, test runs, commits) — never fabricated.

**Authoritative starting HEAD:** `81b53b1175aede4ed05d1b9d086af91dda64c8a6` (R11, `feat(cognition):
add native goal strategy candidate generation`), branch `production-hardening-complete`.

---

## Phase 0 — Repository Verification (complete)

- Branch: `production-hardening-complete`. HEAD: `81b53b117...` (matches expected).
- `git status --short`: clean. `git worktree list`: single worktree, no stale worktrees.
- `git branch -a`: `main`, `backup-before-msg-rewrite` (both inert, untouched), current branch,
  remote tracking. No stale mutation branches.
- No `python`/`python3` process running (autonomous loop / Segment2 experiment NOT live).
- `VECTOR_MCP` not set. `.env` not present in listing (gitignored, untouched).
- R11 commit confirmed present in `git log`.

**Verdict: clean to proceed.**

---

## Wave R12 — Current-State Reconstruction (complete, 10/10 audits, all read-only, zero production files touched)

All full reports live in `VECTOR_TECHNICAL_KNOWLEDGE/r12_audits/R12-*.md`. Summary of each,
synthesized below rather than concatenated.

### R12-A — Goal / Strategy Audit
Of 7 real `PRESEEDED_GOALS`, only **1** (`g_daily_commit`) gets genuine ≥2-candidate diversity
today (`git_status` + `code_task`). 3 goals have multiple known tags that all alias to the *same*
action_type (diversity collapses to 1). The 2 highest-priority Equation goals (`g_first_revenue`,
`g_equation_portfolio`) have **zero** tag coverage, falling back to the horizon default.
`g_vector_phase1` (VECTOR's own top-priority MID goal, progress=0.25) is silently excluded from
candidate generation **entirely** by a pre-existing (not R11-caused) `progress > 0.0` gate in the
MID/LONG loop of `generate_immediate_actions()` — currently produces **zero** candidates.
**Correction to R11's own report:** plan candidates are not dormant/broken — `_get_plan_candidates()`
is fully wired; the only reason it's inert is 0 persisted plans (root-caused in R12-D).
Also re-flagged: `goal_system.py`'s `__main__` self-test block still mutates the real production
goal store unguarded — the exact hazard that caused the R11 incident is still present.

### R12-B — Learning / Outcome Audit
**A real production path from execution outcome → reward → PolicyMemory update already exists and
works.** 3 live writers in `autonomous_loop.py` (VectorCode-bridge path, main `governor.dispatch()`
path with a real 5-factor reward, plan-step-execution path), all keyed by the canonical
`make_situation_hash(action_type, params)` identity `decision_engine.py` reads before every score.
A previously-documented historical bug (vetoes contaminating `avg_reward` with a hardcoded 0.05) is
confirmed **already fixed** by a prior task — vetoes now route through a separate
`record_suppression()` channel. One new minor (P3) defect: `districts/reflection/daily_reviewer.py`
writes a hardcoded reward under a synthetic, non-canonical hash — a silent no-op, not on the
critical path.
**Conclusion: outcome attribution is NOT the current L5 bottleneck.**

### R12-C — Epistemic Audit
Two structurally separate pathways share one SQLite table via key-prefix convention:
- `action_domain:*` — **fully closed loop, RUNTIME_REACHABLE.** Real reward writes a belief
  (`autonomous_loop.py:1349`/`:1611`) → `_epistemic_penalty()` (`decision_engine.py:411-436`) reads
  it unconditionally inside `_score_candidate()` on **every real decision**, applying a
  `[0.70, 1.0]` multiplier. Decay wired into `_reflect_tick()`. This corrects a stale
  `phase_status.md` "orphaned" note — it was fixed by earlier R9 work, untouched by R11.
- `belief:*` — confirmed still **write-only/orphaned**. `ContextEngine.track_beliefs()` writes 5
  real claim families every think-tick; zero consumers read any `belief:*` key for decision
  purposes (only a stats endpoint touches it).

### R12-D — Planning Audit
`core/runtime/plans.py` is real, substantial, fully wired: DAG steps, crash recovery gated on the
same GREEN/YELLOW/RED classification, replanning, atomic persistence. `_get_plan_candidates()`
(`autonomous_loop.py:1517`) is genuinely called from `_think_tick()` (`:930`), competes in the SAME
`DecisionEngine.evaluate()` call as goal candidates, and a plan-step winner genuinely dispatches
through gateway-gated `PlanRunner.execute_step()` with a reward under the canonical hash.
**Currently L0 in production** (confirmed: `data/plans/plans.json` doesn't exist, 0 plans) because
`decompose_goal_to_plan()` only fires from `GoalSystem.add_goal()`, but the 7 real
`PRESEEDED_GOALS` bypass `add_goal()` at seed time, and the only real production caller of
`add_goal()` is the owner-facing `POST /goals/add` API — never anything the autonomous loop calls
on its own. **The machinery is healthy end-to-end; only the trigger is unreached.** One minor (P4)
stale comment found (`goal_system.py:387-388`, claims a false retry guarantee).

### R12-E — Agent Civilization Audit
HP bookkeeping is genuinely real (drives `_calculate_model()` tier selection, the 700-HP council
gate, dispatch tiebreaking). Death detection and lesson/trait inheritance are real and wired.
**Confirmed live defect** (not hypothetical — reproduced by running the existing, unedited
regression test `tests/unit/test_agent_registry_successor_class.py`): `AgentRegistry.deregister()`
calls `EvolutionEngine.spawn_successor()`, which returns a plain `dict`, then does attribute access
(`successor_agent.generation`) on it — `AttributeError` on **every single agent death**, caught by
a broad `except`, silently downgrading every successor to a bare capability-stripped `AgentBase`
stub. Also poisons `cull_bottom()` (wired into the real 2AM reflect tick). Net effect: the
"successor is the same class as its predecessor" half of Darwinian evolution is **0% functional in
production**; lesson-inheritance still works.

### R12-F — Generalization Audit
**No P0/P1 safety findings.** 4 real cross-situation channels, all classified:
1. `PolicyMemory.make_situation_hash()` — full-fidelity, zero generalization by design.
2. Epistemic domain-prefix bucketing (`domain = action_type.split("_")[0]`, confirmed live,
   matches the prior E6 finding) — intentional (Gap 3), bounded to a `[0.70, 1.0]` soft multiplier,
   cannot flip a decision/classification on its own. Coarse enough to be a correctness risk, not a
   safety risk.
3. `CorrectionLearner.get_correction_penalty()` — deliberately exact-match only, bounded `[0, 0.12]`.
4. `CounterfactualMemory.should_avoid()` Jaccard similarity — the only channel that can hard-block
   (retry-queue defense-in-depth only); PermissionGateway remains the authoritative gate regardless.
**L6 (cross-situation transfer) confirmed genuinely NOT IMPLEMENTED** — all 4 channels only
dampen/suppress, never promote a better alternative in a new situation.

### R12-G — Runtime / Liveness Audit
All 3 core loops (observe/think/reflect) confirmed independently protected by `asyncio.timeout` +
broad `except Exception` via direct source read. **R11 fanout ruled out**: `_think_tick()` builds
up to ~12 in-memory candidates (was ≤4, zero I/O), passes the whole list to one `evaluate()` call,
publishes exactly one `DECISION_MADE` event and calls `_act_on()` exactly once — both reference
only `decision.winner`. Each candidate is touched individually by `ReasoningBank` (in-memory,
zero LLM/network) and one `EpisodicMemory.store()` write (pre-existing behavior, not R11-caused).
`DECISION_MADE` has zero downstream task subscribers (only a passive websocket relay). No leaked
background tasks. **One open item for later:** APScheduler `max_instances`/overlap protection not
yet verified — worth checking before any bounded L5 experiment.

### R12-H — Persistence / State Integrity Audit
3 separate SQLite DBs with 2 different isolation mechanisms (`VECTOR_DB_PATH` singleton for the
main DB; per-instance `db_path=` for epistemic/counterfactual, no env var support). Connection
lifecycle, WAL/busy_timeout, and `PolicyMemory` write-lock atomicity all sound.
**Critical risk flagged, directly relevant to R13:** `tests/test_e6_native_candidate_competition.py`,
`tests/test_r11_end_to_end_trace.py`, `tests/test_r11_native_goal_strategy_candidates.py` construct
a bare, unmocked `GoalSystem()`, safe **today only** because `PRESEEDED_GOALS` hasn't changed since
they were written. The moment `PRESEEDED_GOALS` gains any new entry, these 3 files will silently
write into the real production goal store on a routine `pytest` run — reproducing the R11 incident
via CI instead of a manual command. **Must be fixed before any R13 goal-seed-touching mutation.**

### R12-I — Safety Audit
**Clean PASS, no regression.** `core/config.py`, `permission_gateway.py`, `governor.py` byte-identical
across the R11 commit (`git diff ca682c79e 81b53b117 --stat` empty on all three). All 11 action_types
`_TAG_TO_ACTION_TYPE` can produce are pre-existing/pre-classified (9 GREEN, 1 YELLOW, 1 RED), zero
unclassified, zero FORBIDDEN overlap. Zero code-execution primitives or Governor/Gateway references
in the new goal-tag code. RED/YELLOW gate before the VectorCode bridge fully intact.

### R12-J — Regression / Test Audit
**No new regression since 81b53b117.** Full non-Ollama suite: same 13 failures, byte-identical
names, as the pre-R6 Task-90 baseline. The previously-documented 7 intermittent "blog-dedup"
pollution failures simply didn't trigger this run (consistent with documented intermittent nature,
not a hidden fix or regression). `learning_lab` suite: same 7 failures, byte-identical, zero drift.
Sampled weak-assertion sweep across R8/R9/R11 test files found no genuine false-positive (full
tree sweep out of scope for this audit).

---

## Synthesis — Dependency Graph and Decision

**No auditor disagreement required arbitration** — all 10 reports are mutually consistent and, in
several cases, independently cross-confirm each other (R12-A ↔ R12-D on plan-trigger root cause;
R12-B/R12-C both show more of the cognitive stack is already wired than the R11-era docs assumed).

**Downgrades from the R12–R20 roadmap framework, per section 30's explicit license to do this:**

- **R15 (Outcome/Reward Integrity): largely already satisfied.** R12-B found the causal chain
  intact and production-reachable, with the one known historical bug already fixed by prior work.
  Downgraded from "implement" to "log the one P3 defect found, no mutation required now."
- **R16 (Epistemic Integration): core objective already met.** R12-C found `action_domain:*` fully
  integrated and runtime-reachable — this is precisely what R16 asked to prove. The `belief:*`
  pathway remains orphaned by design choice (mission explicitly forbids merging namespaces "merely
  for convenience"); no current decision needs it. Downgraded to "documented, no mutation now."
- **R17 (Plan-Derived Diversity) promoted ahead of R13.** R12-D shows the plan machinery is fully
  healthy and only needs its existing trigger reached — this is a smaller, safer mutation than
  expanding `_TAG_TO_ACTION_TYPE` (R13), reuses 100% existing architecture, and delivers a second
  real native candidate source. Per section 29 ("if a task is independent, parallelize it... if a
  proposed task turns out unnecessary, remove it"), R17 is resequenced to run **before** R13.

**New prerequisite inserted ahead of R13:** the R12-H test-isolation hazard must close before any
mutation touches `PRESEEDED_GOALS` or goal-seed tags — this is a hard sequencing dependency, not
optional cleanup.

**Deferred, not forgotten:**
- R12-E's confirmed `AgentRegistry`/`EvolutionEngine.spawn_successor()` type-mismatch bug → belongs
  to R18 (Agent Evolution/Specialization). Not blocking R13/R17. Will be fixed as R18's own
  milestone, not folded in now (avoids "fix everything in one giant mutation").
- R12-G's APScheduler overlap-protection open item → check before any R20 bounded L5 experiment,
  not before R13/R17.
- R12-B's `daily_reviewer.py` non-canonical-hash defect (P3) → cosmetic, log only.
- R12-D's stale retry-comment (P4) → documentation-only, log only.

### Dependency Graph (this wave)

```
R12 audits (done)
   │
   ├─→ M1: Test-isolation hardening (R12-H fix)   [PREREQUISITE — sequential, must land first]
   │        touches: tests/test_e6_native_candidate_competition.py,
   │                 tests/test_r11_end_to_end_trace.py,
   │                 tests/test_r11_native_goal_strategy_candidates.py
   │        no production code touched.
   │
   ├─→ M2: R17 — Plan-derived strategy diversity   [depends on M1 landing]
   │        touches: core/brain/goal_system.py (one-time decomposition trigger for the
   │                 2 real MID/LONG preseeded goals) OR a bootstrap-time call site —
   │                 exact mutation point to be confirmed by the R17 implementation
   │                 agent against current source, not assumed.
   │        reuses: existing decompose_goal_to_plan(), existing PlanStore, existing
   │                 _get_plan_candidates() — no new machinery.
   │
   └─→ M3: R13 — Strategy coverage expansion       [depends on M1 landing; independent of M2]
            touches: core/brain/goal_system.py (_TAG_TO_ACTION_TYPE additions for
                     g_first_revenue/g_equation_portfolio's real tag vocabulary) and
                     the g_vector_phase1 zero-candidate gate defect (R12-A).
            M2 and M3 both touch goal_system.py → SEQUENTIAL, not parallel, per the
            "one authoritative mutation agent per coupled subsystem" rule. M2 first
            (smaller, safer, higher-confidence), M3 second.
```

Deferred milestones (logged, not started): R18 (agent evolution defect fix), R14 (production
learning validation — re-scope after M2/M3 land, since candidate diversity is the current input to
that trace), R19/R20 (generalization / long-horizon — explicitly gated on R13-R17 stability per
mission section 13/14).

---

## Milestone Log

### M1 — Test Isolation Hardening (R12-H prerequisite fix)
- **Status:** COMPLETE
- **Objective:** eliminate the confirmed real-production-DB-write risk in 3 test files before any
  goal-seed-touching mutation lands.
- **Root cause confirmed:** `GoalSystem.__init__` → `_load_or_seed()` reads the real goal store via
  `EpisodicMemory` and, if any `PRESEEDED_GOALS` id is missing from the stored set, `_merge_new_seeds()`
  calls a real `self._persist()` — all of this runs **before** a test's post-construction
  `gs._persist = lambda: None` / `gs._goals = []` overrides ever take effect. Confirmed by direct read
  of `core/brain/goal_system.py:175-214`.
- **Mutation owner:** orchestrator (direct, low-risk, test-file-only change, no production code touched).
- **Files changed:** `tests/test_e6_native_candidate_competition.py`,
  `tests/test_r11_end_to_end_trace.py`, `tests/test_r11_native_goal_strategy_candidates.py` — each
  construction site changed from `GoalSystem()` to `GoalSystem.__new__(GoalSystem)` (bypasses
  `__init__`/`_load_or_seed()` entirely, so the real DB is never read or written), followed by
  explicit `gs._memory = None; gs._persist = lambda: None; gs._goals = [...]` exactly as before.
  `test_r11_learning_integration.py` was NOT touched — it already isolates via `VECTOR_DB_PATH` set
  before any `core.*` import, which is the correct pattern for a file that deliberately tests real
  restart persistence.
- **Tests:** `pytest tests/test_e6_native_candidate_competition.py tests/test_r11_end_to_end_trace.py
  tests/test_r11_native_goal_strategy_candidates.py -q --timeout=90` → 36/36 pass (5+2+29), unchanged
  from before the fix.
- **Evidence:** TEST_VERIFIED + direct production-state read. Read-only query of the real goal store
  immediately after the test run confirmed **10 goals**, ids identical to the known-good post-R11-
  incident-fix count — zero extraneous writes.
- **Reviewer result:** self-verified by the orchestrator (single-owner test-file fix, mechanical
  and low-risk; no separate reviewer agent launched for this prerequisite).
- **Safety:** no production code touched; no permission/routing/classification code touched.
- **Commit:** pending (below).
- **Capability level:** N/A (infrastructure/test-safety fix, not a cognition milestone).
- **What is proven:** the 3 flagged files can no longer touch the real production goal store under
  any future `PRESEEDED_GOALS` change, mechanically (not by coincidence).
- **What is NOT proven:** this does not audit every other test file in the repo for the same class
  of hazard — R12-H's audit sampled deliberately, not exhaustively; a full sweep is out of scope here.
- **Remaining risk:** none introduced; residual risk is any *other*, not-yet-audited test file using
  a bare `GoalSystem()` — none found by R12-H's search, but its search was not certified exhaustive.
- **Next dependency:** superseded — M1c (owner-directed) intervened before M2/R17 resumed.

### M1c — Development/Test Isolation Safety Audit (owner-directed, read-only)
- **Status:** COMPLETE. Full report: `VECTOR_TECHNICAL_KNOWLEDGE/M1c_DEVELOPMENT_TEST_ISOLATION_SAFETY_AUDIT.md`.
- Triggered directly by the owner after reviewing the M1b incident (below) — 4 parallel read-only
  audits found the M1b mechanism isolated to the one already-fixed file, but surfaced 4 NEW P0-class
  hazards never previously documented: a real, unisolated `AutonomousLoop.run_forever()` self-test; a
  real, unisolated `EpisodicMemory` self-test writing into `reasoning_chains`; `EpistemicTracker`/
  `CounterfactualMemory` isolating via a completely different, `VECTOR_DB_PATH`-blind mechanism; and
  `core/mcp_server.py`'s pre-existing (Task 60) ungated-tool exposure on direct execution.
  Verdict: YELLOW. Explicit instruction: STOP, report, do not remediate automatically.

### M1d — Development/Test Safety P0 Remediation (owner-directed)
- **Status:** COMPLETE (partial — 3/4 P0 items). Full report: `VECTOR_TECHNICAL_KNOWLEDGE/M1d_DEVELOPMENT_TEST_SAFETY_REMEDIATION.md`.
- P0-A, P0-B, P0-D: fixed, verified isolated/against disposable state, zero regression across the
  full non-Ollama suite (5,367 collected / 13 failed, all pre-existing / 0 errors).
- P0-C: implemented, caused a 260-failure/18-error regression (pre-existing `VECTOR_DB_PATH` leakage
  across 4 test files, invisible until P0-C's fail-closed guard made it loud), root-caused, a
  `teardown_module()` fix attempted and found insufficient against pytest's collect-all-before-run
  model, REVERTED rather than expanded into `tests/conftest.py`-level architecture change.
- New permanent regression tests: `tests/test_m1d_development_test_safety.py` (7 tests).
- **Final Gate: YELLOW — do not resume R17 automatically; owner decision required** (R17's own
  target module was independently confirmed unaffected, but per the mission's own explicit
  instruction this is reported, not auto-resumed).
- **Nothing committed yet** — per "STOP after M1d and report" instruction, awaiting owner review.
- **Next dependency:** owner decision — commit the 3/4 partial remediation as-is, direct further work
  on P0-C's real fix (a `tests/conftest.py` session-level isolation fixture), or resume R17 despite
  the open P0-C gap.

### M1e — Development Foundation & Evidence Reconciliation (owner-directed, autonomous ~3h)
- **Status:** COMPLETE. Full report: `VECTOR_TECHNICAL_KNOWLEDGE/M1E_DEVELOPMENT_FOUNDATION_REPORT.md`.
- **P0-C leak root-caused precisely**: exactly 4 test files had the collection-time
  `VECTOR_DB_PATH` leak (`test_e1_persistent_learning.py`, `test_r10_decision_provenance.py`,
  `test_task89c_goal_progress.py`, `test_r11_learning_integration.py`); exhaustively audited all 39
  `VECTOR_DB_PATH`-touching files in the repo and confirmed no other instance exists. Fixed at the
  root via a new `isolated_vector_db` fixture (`tests/conftest.py`, monkeypatch-based, resets the
  `EpisodicMemory` singleton), proven via a minimal reproduction (`test_m1e_isolation_fixture.py`)
  and at full-suite scale: 5,384 collected / 19 failed (all pre-existing) / 0 errors.
- **P0-C re-attempted on top of the fix, found a SECOND, larger regression, reverted again**: 133
  failed / 0 errors — 114 new failures across ≥21 files that legitimately isolate `VECTOR_DB_PATH`
  but never also isolated `EpistemicTracker`/`CounterfactualMemory` (a true positive, not a leak —
  these files have silently touched real production `epistemic.db`/`counterfactual.db` this whole
  time). P0-C's real scope is now precisely measured but NOT fixed — real architecture/audit
  decision left for the owner. `TestP0CNotRegressed` guard added so a future re-attempt can't
  silently reintroduce this without hitting a loud test failure pointing at the report.
- **Agent successor bug fixed**: confirmed live dict/object contract mismatch in
  `core/city/agent_registry.py::deregister()` (attribute access on a dict `spawn_successor()`
  correctly returns) — 5-line fix, `tests/unit/test_agent_registry_successor_class.py` 3/3 pass
  (was 2/3), `cull_bottom` regression clean.
- **Digital Twin Lab hash bug fixed**: `twin.py`/`level4_experiment.py` both had a stale,
  hand-duplicated situation-hash formula predating Task 89's canonical hash — fixed by delegating to
  the real `PolicyMemory.make_situation_hash()`. Resolved **all 7** of the lab's previously-
  documented pre-existing failures as a side effect (23/30 → 30/30). `level4_experiment.py`'s own
  L4 verdict flipped from self-reported FAIL to genuine PASS.
- **L4 claim re-verified on current HEAD**: `test_r11_learning_integration.py` independently
  reproduces the full chain (3/3 pass) — classified L4 MECHANICALLY PROVEN IN ISOLATED LAB, not
  production L4.
- **8 previously-"pre-existing" failures re-investigated from scratch, all reclassified TEST
  DEFECT** (4 correction — domain-keyword-list mismatch + wrong-phrasing-choice; 2 epistemic — mock
  string-matching mismatch with the real `action_type.split("_")[0]` convention) — one initial
  sub-agent misdiagnosis (confidence-cap claim) independently caught and corrected by direct
  re-verification before being written into the report.
- **Final shipped regression baseline: 5,384 collected / 19 failed / 0 errors, zero new
  regressions.**
- **R12 readiness: READY** (per the report's own §17 reasoning).
- **Next dependency:** owner decision on P0-C's real fix (native `VECTOR_DB_PATH` support for
  `EpistemicTracker`/`CounterfactualMemory`, or an audit of the ≥21 affected files) — otherwise R12
  may proceed.

### M1b — `goal_system.py` `__main__` self-test hazard fix — INCLUDES A SELF-DISCLOSED INCIDENT
- **Status:** COMPLETE (after a real mistake, caught and corrected within this same milestone).
- **Objective:** R12-A and R12-D both independently re-flagged that `goal_system.py`'s own
  `if __name__ == "__main__":` self-test still mutates the REAL production goal store when run
  directly (`python core/brain/goal_system.py`) — the exact hazard that caused the original R11
  incident, still unfixed at the start of this milestone.
- **INCIDENT (self-disclosed, not caught by the user):** the orchestrator's first attempt at this
  fix was itself broken and caused a SECOND real, unauthorized production mutation.
  - **What happened:** the first fix wrapped the temp-DB override in
    `if "VECTOR_DB_PATH" not in os.environ:`, intending "don't clobber a caller's deliberate
    setting." This is wrong for this call site: `core.config` (imported at the top of this very
    file, line 11, before `__main__` ever runs) triggers `python-dotenv`'s `load_dotenv()`, which
    had already set `os.environ["VECTOR_DB_PATH"] = "vector_memory.db"` (the app's own real
    production default from `.env`) by the time `__main__` reached the guard — so the guard always
    evaluated false and silently skipped the override, using the real DB the entire time.
  - **Consequence:** running `python core/brain/goal_system.py` once (to verify the "fix") called
    the file's own self-test body for real against the real store: `gs.update_goal_progress(
    "g_daily_commit", 0.5, ...)` reset that goal's progress from 1.0 → 0.5 (again), and
    `gs.add_goal("Learn Bengali by August", ...)` added a real extraneous goal (`g_ba140726`,
    11th goal) — reproducing the exact R11 incident a second time, this time despite the explicit
    intent of the fix meant to prevent it.
  - **Root cause confirmed** by direct minimal repro (`python -c` script printing
    `os.environ.get("VECTOR_DB_PATH")` and `configured_db_path()` before/after import order) —
    not guessed.
  - **Fix:** removed the conditional guard entirely; the override in `__main__` is now
    UNCONDITIONAL (`os.environ["VECTOR_DB_PATH"] = _tmp_db.name`, no `if not in os.environ` check),
    plus a hard `assert configured_db_path() == _tmp_db.name` immediately before constructing
    `GoalSystem()` — refuses to proceed at all if isolation somehow still failed, rather than
    silently falling through to the real DB again.
  - **Verified this time:** re-ran `python core/brain/goal_system.py` twice; both times logged
    `"seeded 7 goals"` (fresh isolated temp DB — the correct, expected isolated behavior), never
    `"loaded 10/11 goals from memory"` (which would indicate the real store).
  - **Damage repair:** used `GoalSystem`'s own real API (`_goals` list filter + direct field
    correction + `_persist()`, matching the established R11-incident-repair pattern) to: (1) remove
    the extraneous `g_ba140726` goal, (2) restore `g_daily_commit.progress` to `1.0`. A first repair
    attempt also set `g_daily_commit.status = "completed"` as a side effect of using
    `update_goal_progress()`'s own auto-complete-at-1.0 logic — on reflection this was itself an
    unverified extra change (a recurring daily-habit goal being marked "completed" would silently
    remove it from `get_active_goals()`/all future candidate generation, a behavioral change beyond
    "restore progress"). Corrected immediately: `status` reset back to `"active"`, reasoned from
    R12-A's own read-only audit (which ran chronologically BEFORE any of these incidents and
    confirmed `g_daily_commit` was actively producing real candidates at that time — only possible
    if its status was `"active"`, not `"completed"`).
  - **A follow-up read-only verification query was blocked by the Claude Code auto-mode classifier**
    (same as during the original R11 incident). Accepted without a workaround, per the established
    session convention — the repair script's own printed output already provided sufficient
    confirmation, and R12-A's audit supplied the missing evidence for the status field specifically.
  - **Final confirmed state of the real production goal store:** 10 goals (matching the known-good
    post-R11-incident-fix count), `g_daily_commit` at `progress=1.0, status="active"`.
  - **Unresolved observation, NOT self-caused, disclosed for the owner's awareness:** the same
    read that revealed the `g_ba140726` pollution also showed `g_kiit_attendance`, `g_karpathy_30`,
    `g_placement_prep`, `g_first_revenue`, and `g_equation_portfolio` all at `progress=0.076` — a
    value neither this incident's self-test (which only ever touches `g_daily_commit`) nor any
    other action in this session touches or explains. This was NOT investigated further (out of
    scope for this fix, and further investigation would mean more real-store reads/writes without
    a clear justified need) and is flagged here rather than silently overwritten or ignored.
- **Files changed:** `core/brain/goal_system.py` (`__main__` block only — no change to any
  production class/method logic).
- **Tests:** re-ran the file's own self-test twice (isolated, passing both times); this change adds
  no new pytest-collected test (it's a `__main__` guard, per this repo's own convention of a
  real-but-isolated self-test at the bottom of every file).
- **Safety:** no production code paths, permission classification, or routing touched. The incident
  itself was a data-integrity issue (real user data), not a safety-architecture issue (no RED/YELLOW
  boundary was crossed, no unauthorized action_type was executed) — but is treated with equivalent
  severity and full disclosure per the mission's honesty requirements.
- **Commit:** pending (below, bundled with M2 since both land together).
- **What is proven:** the self-test hazard is now mechanically closed (unconditional override +
  hard assert refuses to proceed on failure), not merely "fixed until the next coincidence."
- **What is NOT proven:** whether any OTHER script or ad-hoc invocation elsewhere in the repo has
  the same `os.environ` guard-ordering mistake — this fix addressed only the specific file R12-A/
  R12-D flagged.
- **Remaining risk:** the unexplained `progress=0.076` values on 5 goals remain unresolved and
  undocumented in origin — flagged for the owner, not silently corrected.
- **Next dependency:** M2 (R17) proceeds; this incident does not block it (production goal store is
  confirmed in a known, correct state).
