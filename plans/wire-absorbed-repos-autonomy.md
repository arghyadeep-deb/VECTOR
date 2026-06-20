# Wire Absorbed Repos → Full VECTOR Autonomy — Implementation Plan (v2)

**Author:** Opus 4.8 (planning) · **Executor:** Sonnet 4.6 (execution)
**Date:** 2026-06-20 · **v2** — reordered after owner stress-test

**Goal:** Every absorbed CAPABILITY (research, trading analysis, OSINT/intelligence, content, scraping, coding-assist) **self-triggers on schedule AND produces real, verified, non-empty output**, with results fed back into memory/HP — all without owner interference.

**Definition of done (owner-chosen 2026-06-20):**
- ✅ Each capability runs proactively on a schedule (no prompt needed).
- ✅ Each capability has at least ONE **live, non-stubbed** run that produced real output, captured as proof.
- ✅ Results close the loop: episodic memory + HP + policy reward.
- ⚪ Dormant internal code is ACCEPTABLE. We are NOT chasing 100% line coverage of 870K LOC. Prune only what's *provably unreachable* (Phase 4), and only with owner sign-off.

**Why v2 reordered:** v1 built the orchestration engine first and proved it with *stubbed* tests (`monkeypatch _dispatch`) — which would go green even if the absorbed code is broken at runtime (853 surviving Fincept refs; `trading_conductor` has a bare `raise`; real runs need API keys + market data). v2 inverts this: **prove each capability actually runs and produces output FIRST**, then make it autonomous. You cannot wire autonomy onto a capability that doesn't work.

**Critical principle:** Two test layers, always.
1. **Unit (stubbed, fast, offline)** — proves orchestration *plumbing*.
2. **`@pytest.mark.live` (real dispatch, real output, credential-gated)** — proves the *capability*. Skips when keys absent, but MUST be run once per repo and its output captured to `docs/capability_proofs/<repo>.md`. **A capability is not "done" until its live proof exists.**

**Verified findings (2026-06-20):** governor 634 routes→131 districts (investment 9 routes, intelligence 34 routes); `hands/registry.py` 9 Hands orphaned (0 refs outside `hands/`); only `research_loop()` self-triggers (gated off, hardcoded topics); `_FINCEPT_BASE = Path(__file__).parent/"vector_finagent"` is relative (resolves OK); shadowbroker is partly a **standalone server** (`tools/start_shadowbroker.bat`), not loop-governed.

**Files:**
- Create: `scripts/capability_smoke.py`, `docs/capability_proofs/` (one .md per repo)
- Create: `hands/runner.py`, `hands/result.py`
- Create: `tests/hands/test_hand_runner.py`, `tests/hands/test_hands_wired.py`, `tests/integration/test_absorbed_autonomy.py`, `tests/integration/test_capability_live.py`
- Modify: `core/loop/autonomous_loop.py`, `core/loop/cron_jobs.py`, `hands/registry.py`, `core/config.py`

---

## PHASE 0 — Capability reachability + LIVE smoke (DO FIRST — defines the work)

Goal of this phase: for each absorbed repo, answer with evidence — *does the capability actually run and produce real output today?* This scopes everything and surfaces breakage before we invest in orchestration.

### Task 0.1: Reachability map
- [ ] Create `scripts/capability_smoke.py` — for each repo's district entrypoint (`districts/investment/finagent_agent.py`, `trading_conductor_agent.py`; `core/research_engine/auto_research_agent.py`; `districts/research/*`; `core/scraper/vector_scraper.py`; `districts/coding/coding_tools.py`; `districts/intelligence/*`), do an `importlib` import and list which submodules import-resolve vs ImportError.
- [ ] Run: `PYTHONUTF8=1 python scripts/capability_smoke.py --reachability` → writes `docs/capability_proofs/_reachability.md`.
- [ ] Commit: `git commit -m "chore: absorbed-repo reachability map"`

### Task 0.2: LIVE smoke — does each capability produce real output? (one per repo)
For EACH of: research_engine, investment(Fincept), trading, scraper, intelligence, coding_assistant —
- [ ] Add a `--live <repo>` mode to `scripts/capability_smoke.py` that invokes the real district agent ONCE with a minimal real input (e.g. research topic="test"; investment ticker="AAPL"; scraper url="https://example.com").
- [ ] Run it. Capture verbatim result to `docs/capability_proofs/<repo>.md` with one of three verdicts:
  - **LIVE** — produced real non-empty output. (record a sample)
  - **NEEDS-CONFIG** — ran but needs API key / data source (record exactly which env var / dep).
  - **BROKEN** — raised; record the traceback + root cause (likely a surviving original-path or absorbed-internal assumption).
- [ ] Commit per repo: `git commit -m "docs: capability proof — <repo> [LIVE|NEEDS-CONFIG|BROKEN]"`

### Task 0.3: Triage gate (decision point — surface to owner)
- [ ] Summarize Phase 0 in `docs/capability_proofs/_summary.md`: per repo = LIVE / NEEDS-CONFIG (which keys) / BROKEN (what to fix).
- [ ] **STOP and report to owner.** BROKEN repos need a fix sub-task before they can be made autonomous (a scheduled hand that crashes isn't autonomy). NEEDS-CONFIG repos need the owner to drop keys in `.env`. This triage decides the real Phase 2 workload.

**Phase 0 done = we KNOW, with evidence, which capabilities can be made autonomous now vs. need a fix/key first. No more guessing.**

---

## PHASE 0.5 — Fix bugs surfaced by triage (before scheduling those capabilities)

Per owner goal: a capability must PRODUCE REAL OUTPUT. These are "not working" features, not dead code — fix, don't skip.

### Task 0.5a: scraper — public API discards fetched content ✅ DONE (2026-06-20)
- [x] Failing live test: `fetch("https://example.com")` returns non-empty body.
- [x] Fix `core/scraper/vector_scraper.py:152` — reads `resp.text` (always empty) → use `resp.html_content`. Affects every `fetch()`/`quick_fetch()`. (Fixed all 3 call sites + the matching `html=` assignments.)
- [x] Live test PASS · capture proof → `docs/capability_proofs/scraper.md` (verdict→LIVE) · committed (auto-hook). Regression test: `tests/integration/test_capability_live.py::test_scraper_fetch_returns_real_content`.

### Task 0.5b: research_engine — pipeline runs but content is hollow ✅ DONE (2026-06-20)
- [x] Fix wrong method name: `EpisodicMemory.search()` → `.recall(topic, limit=5)` (exact same call signature, real accessor).
- [x] Sandbox experiment failed with 0 data points — root cause was NOT the Ollama 404 (that degrades gracefully to rule-based design as designed); it was `_default_experiment_code()`'s generated script calling `logger.info("STAT:...")`, but the sandbox's restricted `__builtins__` never defines `logger` and `SandboxExecutor._extract_stats()` only ever parses `STAT:` lines from **stdout** — fixed to `print(...)`. Also rewired `ExperimentDesigner`'s model default from the unmodified upstream `llama3.2` (never installed) to `CONFIG["models"]["reasoning"]`.
- [x] Re-run live smoke → report now contains real computed statistics (t=0.314, p=0.766, r=-0.430), not empty sections. Updated `docs/capability_proofs/research_engine.md` (verdict→LIVE) · committed (auto-hook). Regression test: `tests/integration/test_capability_live.py::test_research_engine_full_cycle_produces_real_statistics`.

### Task 0.5c: test isolation — live smoke must not fight a running server ✅ DONE (2026-06-20)
- [x] `scripts/capability_smoke.py --live` now sets `VECTOR_DB_PATH` to a fresh temp file before any VECTOR import, via the existing override seam in `core.memory.db_utils.configured_db_path()`. Proven with the original conflicting process (PID 48532) still running — zero process killing required.
- [x] Re-ran investment/trading/intelligence against the isolated DB. **Result: the DB-contention finding is fully resolved** — but doing so unmasked 2 separate, real, different bugs (investment: asyncio event-loop error in `VectorProviderModel._sync_call`; trading: missing `langgraph-checkpoint-sqlite` dep (fixed, pinned) + a deeper `WinError 3` empty-path bug inside `VectorTradingGraph`, not yet found). Both flagged for Phase 2, out of scope here. `intelligence`'s port mismatch is confirmed unrelated to DB/test isolation (it never touches `EpisodicMemory`) — still a one-line owner env fix, not code.
- [x] Committed (auto-hook). New test: `tests/test_capability_smoke.py` (4 tests) + `docs/capability_proofs/_summary.md` rewritten to reflect final state.

---

## PHASE 1 — Hand Execution Engine (orchestration foundation)

**ARCHITECTURE DECISION (resolved 2026-06-20, verified in code):** Hands run IN-PROCESS as scheduled coroutines inside the autonomous loop. `core/memory/episodic.py` already exposes a **module-level singleton connection** (`_db_connection`, `_db_lock`, `check_same_thread=False`). Therefore:
- Hands MUST use `get_db_connection()` — **never** instantiate a per-hand `EpisodicMemory()` with its own connection.
- The "two processes can't share the DB" issue Phase 0 saw is a *test* artifact (separate smoke process vs running server), NOT a production constraint. No multiprocess redesign.

### Task 1.0: DB concurrency hardening (do before 1.1) ✅ DONE (2026-06-20)
- [x] Confirmed neither pragma was set; added both to `_open_sqlcipher_connection` (`core/memory/episodic.py`): `PRAGMA busy_timeout = 5000`, `PRAGMA journal_mode = WAL`. Verified live: `PRAGMA journal_mode` → `wal`, `PRAGMA busy_timeout` → `5000` on the real DB.
- [x] In-process thread concurrency was already safe (pre-existing `test_concurrent_writes_no_database_locked` passed before this change too — the module-level singleton + lock already serializes that case). Added the test this task actually asked for — `test_second_connection_to_same_file_waits_not_hard_fails`: two separate connection objects to the same encrypted file (standing in for two processes), one holds `BEGIN IMMEDIATE` + sleeps 0.5s, the other's write now waits and succeeds instead of raising immediately. Plus `test_open_sqlcipher_connection_sets_busy_timeout_and_wal` confirming the pragmas directly.
- [x] All 6 tests in `tests/backend/test_memory_concurrency_safety.py` PASS · committed (auto-hook).

### Task 1.1: HandResult dataclass + episodic persistence
- [ ] Failing test `tests/hands/test_hand_runner.py::test_hand_result_persists`
  ```python
  from hands.result import HandResult
  def test_hand_result_persists():
      r = HandResult(hand="researcher", district="research", output="body", status="ok", hp_delta=50)
      assert r.persist() > 0 and r.to_dict()["status"] == "ok"
  ```
- [ ] Implement `hands/result.py` — `.persist()` via `core.memory.episodic.get_db_connection()`/`close_db_connection()` (SQLCipher only; never raw sqlite3), `kind="hand_run"`.
- [ ] Test PASS · `git commit -m "feat(hands): HandResult + episodic persistence"`

### Task 1.2: HandRunner.run_hand — real dispatch through governor
- [ ] Failing UNIT test (stubbed dispatch) — proves plumbing:
  ```python
  def test_run_hand_plumbing(monkeypatch):
      from hands.runner import HandRunner; from hands.registry import HandRegistry
      runner = HandRunner(); monkeypatch.setattr(runner, "_dispatch", lambda h,c: "stub")
      import asyncio; r = asyncio.run(runner.run_hand(HandRegistry().get("researcher"), {}))
      assert r.status == "ok" and r.output
  ```
- [ ] Implement `hands/runner.py::run_hand`: hydrate context (`ContextEngine.session_hydration_prompt()` + hand.system_prompt) → `_dispatch` routes via `core.city.governor.Governor` to `_task_type_for(hand)` district → `requires_approval` gates through `PermissionGateway` → `asyncio.timeout` → return HandResult (never raise; RULE 2).
- [ ] Test PASS · `git commit -m "feat(hands): HandRunner.run_hand via governor"`

### Task 1.3: Closed feedback loop
- [ ] Failing test asserts `_record_episodic`+`_award_hp`+`_update_policy` each called once per run (monkeypatched counters).
- [ ] Implement: after dispatch → episodic+reasoning_memory write, HP via `agent_registry` (+50 ok / −30 error), `policy.update_from_outcome(...)`.
- [ ] Test PASS · `git commit -m "feat(hands): close result→memory→HP→policy loop"`

### Task 1.4: register_all into the durable scheduler
- [ ] Failing test (FakeScheduler) asserts 7 scheduled hands registered (2 are on-demand).
- [ ] Implement `register_all(scheduler)` reusing `core/loop/cron_jobs.py::_try_register` (do NOT invent a scheduler). Skip hands with `on_demand=True` (add this field in Task 3.2), not by empty-string.
- [ ] **Model-residency awareness (surfaced by Phase 0.5 eviction finding).** With `OLLAMA_MAX_LOADED_MODELS=1` (confirm — models.md says 1, architecture.md says 2; resolve the discrepancy), every model-heavy hand both eats a ~58s cold-load AND evicts the resident interactive model (`vector-focus`), degrading voice latency. Therefore the runner MUST serialize model-heavy hand execution behind a single asyncio lock (`self._model_lock`) — never run two different-model hands concurrently — and SHOULD bias their cron times off-peak. Failing test: two model-heavy hands triggered together do not run concurrently (the second waits). This is a scheduler design constraint, not an afterthought.
- [ ] Test PASS · `git commit -m "feat(hands): register scheduled hands + model-residency serialization"`

### Task 1.5: Start in autonomous loop
- [ ] Failing test: `inspect.getsource(autonomous_loop)` contains `HandRunner` + `register_all`.
- [ ] Modify `core/loop/autonomous_loop.py::run_forever` (after `register_default_jobs`, ~L1745–1845): `HandRunner().register_all(scheduler)` in try/except.
- [ ] Run `pytest tests/hands -v` + `python scripts/integration_check.py` PASS · `git commit -m "feat(loop): hands now execute"`

### Task 1.6: Real callable scheduler (APScheduler) — unblocks hands AND the dead cron jobs
**Root cause (verified 2026-06-20):** `_get_scheduler()` returns the prompt-based `TaskScheduler` (`core/scheduler/scheduler.py`: `create_task`→`_execute_task`→`system.ask`). It has no `add_job/schedule/register/add`, so `_try_register` silently no-ops — meaning BOTH the new hands AND the ~12 pre-existing cron jobs (2AM reflect, audit verify, daily review/journal, biometrics, DSPy) have never fired. APScheduler 3.11.2 IS installed; `_try_register` was written for its API. **This pre-existing gap, not Sonnet's work, blocks definition-of-done #1 ("runs proactively on a schedule").**
**Decision (owner-approved): Option (b) — APScheduler `AsyncIOScheduler` for callable cron/interval jobs; leave `TaskScheduler` for its LLM-prompt purpose.**
- [ ] Failing test: `register_default_jobs(sched)` + `HandRunner().register_all(sched)` on a real `AsyncIOScheduler` → `len(sched.get_jobs()) == cron_jobs + scheduled_hands`; and a manually-triggered job actually invokes its Python callable (assert a side effect, e.g. a flag/episodic row).
- [ ] Implement `_get_callable_scheduler()` in `autonomous_loop` → started singleton `apscheduler.schedulers.asyncio.AsyncIOScheduler`. `scheduler_loop()` passes IT (not `TaskScheduler`) to `register_default_jobs()` and `register_all()`. Keep Sonnet's None-guard fix.
- [ ] Verify `_try_register`'s `add_job` branch builds a proper APScheduler `CronTrigger` from `"m h dom mon dow"` (add a tiny cron-string→`CronTrigger` adapter if it currently passes the raw string); `_try_register_interval` → `add_job(fn, 'interval', minutes=N, id=...)`.
- [ ] Leave `TaskScheduler` untouched for prompt tasks. Confirm the ~12 cron jobs now register (log count > 0).
- [ ] `pytest tests/hands tests/integration -v` + `integration_check.py` + full suite green · `git commit -m "fix(scheduler): APScheduler callable scheduler — hands + cron jobs now actually fire"`
- [ ] Phase 5 autonomy proof (scheduler-fires-hands) is only meaningful AFTER this task.

---

## PHASE 2 — Make each WORKING capability autonomous + prove live

Only for repos Phase 0 marked LIVE or NEEDS-CONFIG (after keys added). BROKEN repos get a fix sub-task first (scoped from Phase 0 tracebacks).

For EACH capability (research, investment, intelligence, content, OSINT-collector):
### Task 2.x: <capability> autonomous + live proof
- [ ] UNIT test: `HandRunner()._task_type_for(hand) == "<route>"` and route exists in `governor.py` (add route if missing).
- [ ] LIVE test in `tests/integration/test_capability_live.py`:
  ```python
  import pytest
  @pytest.mark.live
  def test_<cap>_produces_real_output():
      from hands.runner import HandRunner; from hands.registry import HandRegistry
      import asyncio
      r = asyncio.run(HandRunner().run_hand(HandRegistry().get("<hand>"), _real_ctx()))
      assert r.status == "ok"
      assert len(r.output) > 200            # real content, not a stub/error
      assert "error" not in r.status
  ```
- [ ] Run `pytest -m live -k <cap>` with keys present → PASS; capture output to `docs/capability_proofs/<repo>.md` (verdict → LIVE).
- [ ] `git commit -m "feat(hands): <cap> autonomous + live-proven"`

### Task 2.0: Scrub research_engine network provenance leak (BEFORE it goes autonomous)
A VECTOR web agent must not announce a third-party tool name to every site it hits. This becomes continuous once the research/collector hands are scheduled.
- [ ] Failing test `tests/integration/test_capability_live.py::test_no_foreign_user_agent`
  ```python
  import pathlib, re
  def test_no_foreign_user_agent():
      root = pathlib.Path("core/research_engine")
      bad = [p for p in root.rglob("*.py")
             if re.search(r"Local-Deep-Research", p.read_text(encoding="utf-8", errors="ignore"))]
      assert not bad, f"foreign provenance strings survive in: {bad}"
  ```
- [ ] Run → expect FAIL (4 hits incl. 3 User-Agent headers)
- [ ] Fix `search_engine_github.py:76`, `search_engine_nasa_ads.py:110`, `search_engine_openalex.py:105` → `User-Agent: "VECTOR-Research-Agent"`; replace the other hyphenated `Local-Deep-Research` strings. Detection sweep: grep hyphen/underscore/space/PascalCase + `User-Agent`/header/banner strings, not just import idents (the original audit missed this exact way).
- [ ] Run → expect PASS · `git commit -m "fix(research): scrub foreign User-Agent/provenance — VECTOR-branded"`

Sub-list to execute (confirm/adjust against Phase 0 results):
- research → `researcher`/`collector` hands → `deep_research`/`osint_collect` (do Task 2.0 first)
- investment → `trader` hand → `trading_analysis` (auto-context: `CONFIG["investment"]["watchlist"]`)
- intelligence → map the 34 governed task types to at least one scheduled hand OR document shadowbroker as a **standalone service** started by `tools/start_shadowbroker.bat` + add a health-poll loop (it is NOT a hand). **Decide with owner.**
- content → `content` hand → `content_generate` (`requires_approval=True` — RED, publishing)
- scraper → NO standalone hand; add a live test proving `web_scout`/`collector` reach `vector_scraper` and return real scraped data (it's infrastructure, correct as-is).

---

## PHASE 3 — Harden (no-interference guarantees)
- [ ] Task 3.1: RED hands gated through `PermissionGateway`; high-signal results (`hp_delta>=50` or `status=="alert"`) push via `pushover`. Test + commit.
- [ ] Task 3.2: Add `on_demand: bool` field to `Hand`; set True for `browser`/`clip`; `register_all` skips by flag. Test + commit.
- [ ] Task 3.3: A crashing hand returns an error HandResult and the scheduler keeps firing others. Test + commit.

---

## PHASE 4 — Classify unreached code; WIRE the useful, delete only the dead (owner rule)

**HARD GATE (owner rule 2026-06-20):** This phase runs ONLY after ALL capabilities are LIVE-proven (Phase 5 green). Deletion is the last thing, never before features work.

**"Unreachable" ≠ "deletable."** Unreached code splits into TWO buckets and they are handled OPPOSITELY:
- **NOT-WIRED-BUT-USEFUL** — a real capability/feature that just isn't connected to VECTOR yet → **WIRE IT (new hand/route/import). NEVER delete it.**
- **GENUINELY-DEAD** — redundant, superseded, serves no useful function (e.g. Qt desktop packaging, duplicate loaders, vendored test fixtures, demo scripts) → *eligible* for deletion, after sign-off.

- [ ] Task 4.1: Extend `scripts/capability_smoke.py --deadcode` → static import-graph from each district entrypoint into the absorbed lib; emit `docs/absorbed_reachability.md` listing every unreached module.
- [ ] Task 4.2: **Classify each unreached module** into `WIRE` vs `DEAD` (not "reached/unreached"). For each, one line of justification. A module is `DEAD` only if it has no plausible VECTOR use — being merely disconnected is NOT sufficient. When unsure → default to `WIRE`, never `DEAD`.
- [ ] Task 4.3: For `WIRE` items — add follow-up wiring tasks (hand/route/trigger), same pattern as Phase 2. These are capabilities to gain, not code to lose.
- [ ] Task 4.4: For `DEAD` items only — surface the list to owner. **Delete nothing without sign-off** (memory rule: never delete what you didn't create without surfacing). Quarantine to `_attic/` first → run full suite green → delete in a later pass.

---

## PHASE 5 — Autonomy proof (the shipped gate)
- [ ] Task 5.1: `tests/integration/test_absorbed_autonomy.py::test_scheduler_fires_hands` — fake fast clock, assert ≥1 hand produces a persisted HandResult with closed-loop side effects (episodic row + HP delta), offline.
- [ ] Task 5.2: Full suite green: `PYTHONUTF8=1 pytest tests/hands tests/integration -v` + `python scripts/smoke_test.py` + `python scripts/integration_check.py`.
- [ ] Task 5.3: Confirm every capability has a LIVE verdict in `docs/capability_proofs/` (this is the real definition-of-done — not green stubbed tests).
- [ ] Task 5.4: Three-question shipped check: (1) hand_run rows appear with no prompt; (2) repeated failure moved policy reward; (3) restart → scheduled hands resume.

---

## Pre-flight for executor (Sonnet)
- Always `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` (Windows cp1252 crashes on `→`; also fix `scripts/smoke_test.py` to not print raw arrows).
- **Phase 0 is mandatory and first.** Do not build the engine before knowing what actually runs. Report the Phase 0 triage to owner before Phase 2.
- A capability is DONE only when its `docs/capability_proofs/<repo>.md` says LIVE. Stubbed-green ≠ done.
- Scheduler: read `core/scheduler/` + reuse `core/loop/cron_jobs.py::_try_register`. Don't invent one.
- DB: `core.memory.episodic.get_db_connection()`/`close_db_connection()` only (SQLCipher).
- TDD per task; never bundle; no deletion in Phases 0–3.
```
