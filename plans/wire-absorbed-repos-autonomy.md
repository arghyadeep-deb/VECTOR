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

### Task 1.1: HandResult dataclass + episodic persistence ✅ DONE (2026-06-21)
- [x] `hands/result.py` — `.persist()` via `core.memory.episodic.get_temp_cursor()` (SQLCipher, not raw sqlite3), `event_type="hand_run"`. `tests/hands/test_hand_runner.py::test_hand_result_persists` + `test_hand_result_to_dict_has_all_fields` PASS · committed (auto-hook).

### Task 1.2: HandRunner.run_hand — real dispatch through governor ✅ DONE (2026-06-21)
- [x] `hands/runner.py::run_hand` — hydrates context (`ContextEngine.session_hydration_prompt()` + `hand.system_prompt`); `requires_approval=True` hands route through `PermissionGateway.execute()` (new `hand_*` action types registered in `core/config.py`'s GREEN/RED lists; new `hand_` branch in `permission_gateway.py::_execute_action` delegates to `Governor().dispatch()`); others call `_dispatch` → `Governor().dispatch()` directly. `asyncio.timeout` wraps every dispatch. Never raises (RULE 2) — verified via `test_run_hand_never_raises_on_dispatch_failure`. Committed (auto-hook).

### Task 1.3: Closed feedback loop ✅ DONE (2026-06-21)
- [x] `_record_episodic` (episodic + reasoning_memory), `_award_hp` (+50 ok / −30 error via `agent_registry`), `_update_policy` (`PolicyMemory.update_from_outcome`) — each called exactly once per run, verified both via stubbed counters (`test_closed_feedback_loop_calls_each_once`) AND live end-to-end with real, unstubbed implementations (real HP delta, real policy row). Committed (auto-hook).

### Task 1.4: register_all into the durable scheduler ✅ DONE (2026-06-21)
- [x] Added `on_demand: bool = False` field to `Hand` (`hands/registry.py`); set `True` for `browser`/`clip` — this also satisfies Task 3.2. `register_all(scheduler)` skips `on_demand` hands, reuses `core/loop/cron_jobs.py::_try_register`. `test_register_all_skips_on_demand_registers_seven` confirms exactly 7 registered, browser/clip excluded by flag not empty-string.
- [x] **Model-residency lock** — `HandRunner.MODEL_HEAVY_HANDS = {"researcher", "collector", "predictor", "trader"}`, serialized behind `self._model_lock` (`asyncio.Lock`). `test_model_heavy_hands_serialize_not_concurrent` proves two model-heavy hands triggered together do NOT run concurrently (second waits for the first's lock release) — real `asyncio.gather()`, not a mocked sequence.
- [x] **`MAX_LOADED_MODELS` discrepancy: RESOLVED empirically, not just by reading docs.** Loaded `vector-focus`, then loaded `vector-reasoning` while focus was still resident — `ollama ps` showed ONLY `vector-reasoning` afterward (focus fully evicted). Confirms `models.md`'s `=1` is correct; `brain/VECTOR/README.md`'s `=2` was stale (assumed smaller, no-longer-installed model builds — `gemma4:e4b`/`qwen3:8b` vs. the actual installed 9.3-9.6GB builds, which can't both fit a 12GB card). Fixed `README.md`'s VRAM budget table to reflect this.
- [x] Committed (auto-hook).

### Task 1.5: Start in autonomous loop ✅ DONE (2026-06-21)
- [x] `inspect.getsource(autonomous_loop)` confirmed to contain `HandRunner` + `register_all` (`test_autonomous_loop_starts_hand_runner`). `scheduler_loop()` calls `HandRunner().register_all(callable_scheduler)` in try/except, after `register_default_jobs`. `pytest tests/hands -v` + `integration_check.py` (51/51) PASS · committed (auto-hook).
- [x] **Bonus fix surfaced while wiring this**: `_get_scheduler()` was raising `TypeError` on construction (`TaskScheduler.__init__()` missing required `store` arg) — meaning `scheduler_loop()` returned early on `if scheduler is None`, before even reaching `register_default_jobs()`. Fixed by constructing a real `SchedulerStore(data_path("scheduler.db"))`. This surfaced the deeper Task 1.6 finding below.

### Task 1.6: Real callable scheduler (APScheduler) — unblocks hands AND the dead cron jobs ✅ DONE (2026-06-21)
**Root cause (verified 2026-06-20):** `_get_scheduler()` returns the prompt-based `TaskScheduler` (`core/scheduler/scheduler.py`: `create_task`→`_execute_task`→`system.ask`). It has no `add_job/schedule/register/add`, so `_try_register` silently no-ops — meaning BOTH the new hands AND the ~12 pre-existing cron jobs (2AM reflect, audit verify, daily review/journal, biometrics, DSPy) have never fired. APScheduler 3.11.2 IS installed; `_try_register` was written for its API. **This pre-existing gap, not Sonnet's work, blocks definition-of-done #1 ("runs proactively on a schedule").**
**Decision (owner-approved): Option (b) — APScheduler `AsyncIOScheduler` for callable cron/interval jobs; leave `TaskScheduler` for its LLM-prompt purpose.**
- [x] Failing test confirmed first: real `AsyncIOScheduler` + old `_try_register` code → only `subconscious-loop` (the one interval job) registered; all 12 cron-cadence jobs failed with "scheduler API mismatch" (`add_job(job_id=,cron=,fn=)` → `TypeError`; positional fallback → `LookupError: No trigger named "0 8 * * *"`).
- [x] `_get_callable_scheduler()` implemented in `autonomous_loop.py` → started singleton `AsyncIOScheduler`. `scheduler_loop()` passes it (not `TaskScheduler`) to `register_default_jobs()` and `register_all()`.
- [x] `_try_register`'s `add_job` branch now builds a real `CronTrigger.from_crontab(cron_expr)` and calls `add_job(fn, trigger=trigger, id=job_id, replace_existing=True)` — tried first, before the old generic-kwargs guesses (kept as fallback for other scheduler types). `_try_register_interval`'s existing APScheduler path already worked, unchanged.
- [x] `TaskScheduler` untouched. **Live-verified, not just tested**: real `AutonomousLoop()._get_callable_scheduler()` → `register_default_jobs()` → 13/13 (12 cron + 1 interval) + `HandRunner().register_all()` → 7/7 = **20 real scheduled jobs**, each with a correct, real `next_run_time` (e.g. `daily-eval-harness` at tomorrow 03:00, `weekly-venture-pipeline` at the correct Monday).
- [x] `pytest tests/hands tests/integration -v` (1453 passed / 25 skipped / 2 known non-blocking) + `smoke_test.py` (38/38) + `integration_check.py` (51/51) green · committed (auto-hook).
- [x] Phase 5 autonomy proof (`test_scheduler_fires_hands`) ran after this and passed — see Phase 5 below.
- [x] **Bonus fix found and fixed while verifying**: `tests/research_engine/test_experiment_designer.py`'s 2 template-selection tests were silently relying on the LLM path always failing/timing out (forcing a deterministic rule-based fallback) — once the Task 0.5b timeout fix (60s→120s) gave the LLM a fair shot, it sometimes succeeded and returned a different (correct, just non-rule-based) `experiment_type`, breaking the test's hardcoded string assertion. Fixed by pointing those tests' `ExperimentDesigner` at an unreachable Ollama URL (`http://127.0.0.1:1`) so they deterministically test rule-based template selection, which is what they actually intend — the LLM path has its own separate live test.

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
- research → ✅ ROUTING DONE (2026-06-21) — `researcher`→`deep_research` (route already existed in `governor.py`'s `DISTRICT_TASK_MAP`), `collector`→`osint_collect` (route was MISSING, added it next to `deep_research`). `HandRunner._TASK_TYPE_OVERRIDES` now maps both. Test: `tests/hands/test_hands_wired.py::test_task_type_overrides_match_governor_routes`. **Live proof still depends on Task 2.0** (the User-Agent scrub, in progress by a parallel agent) — don't trust `researcher`/`collector` as fully LIVE until that lands and is re-verified.
- investment → ✅ ROUTING DONE (2026-06-21) — `trader`→`trading_analysis` (route already existed). `auto-context: CONFIG["investment"]["watchlist"]` not yet wired into `HandRunner._hydrate()` — `extra_context` is currently always `{}` when the scheduler fires a hand; a watchlist-aware context injection is a real follow-up, not done here.
- intelligence → ✅ DECIDED 2026-06-21 (owner asleep — made the lower-risk call, flagging for review): **standalone service**, not a hand. Port mismatch fixed (`VECTORINTEL_HOST=http://127.0.0.1:8765` added to `.env`, matching the actually-running shadowbroker instance rather than restarting an owner-managed long-lived process unilaterally). Live-verified: `VectorIntelAgent.get_flights()` now returns real aircraft-tracking data (~3.5MB, real callsigns/registrations/GPS trails/emissions) — see `docs/capability_proofs/intelligence.md`, verdict now LIVE. **Not done, deliberately deferred**: the health-poll loop, and the "map 34 governed task types to a hand" alternative was not attempted — that's a real product-shape decision (does shadowbroker's OSINT data actually fit the Hand model's report-and-done shape, or does it need its own always-on monitoring loop?) that shouldn't be decided solo overnight. Owner: confirm standalone-service framing is right, and decide if a health-poll loop is wanted.
- content → `content` hand → `content_generate` (`requires_approval=True` — RED, publishing)
- scraper → ✅ DONE (2026-06-21) — NO standalone hand (correct, infrastructure not a capability). Live test added: `tests/integration/test_capability_live.py::test_web_scout_reaches_vector_scraper_and_returns_real_data` — `WebScout.fetch_page()` → `get_scraper().smart_fetch()` → `fetch()`/`fetch_stealth()` (already fixed in Task 0.5a) → confirmed real content ("Example Domain") flows through the full integration path, not just `vector_scraper` in isolation. PASS.

---

## PHASE 3 — Harden (no-interference guarantees)
- [x] Task 3.1: ✅ DONE (2026-06-21) — RED hands already gated through `PermissionGateway` since Task 1.2 (`_dispatch_via_gateway`). Added `HandRunner._maybe_notify()`: pages via `PermissionGateway().notify()` on `status in ("alert", "error")`. **Deviated from the literal `hp_delta>=50` clause deliberately** — `_award_hp` currently gives a flat +50 on every success, so `hp_delta>=50` as written would page on every routine run, which is spam and defeats "high-signal" filtering. Paging on alert/error matches the actual intent. Also fixed `run_hand()` to propagate a district agent's own `status` field (e.g. `"alert"`) through `HandResult` instead of always hardcoding `"ok"` on any non-exception dispatch — needed for this to mean anything. Tests: `test_alert_status_propagates_from_dispatch_output`, `test_alert_and_error_results_notify_pushover_not_routine_success` (confirms routine success does NOT page, alert and error both do, exactly once each).
- [x] Task 3.2: ✅ DONE (2026-06-21, landed inside Task 1.4 — see above) — `on_demand` field added, `browser`/`clip` set `True`, `register_all` skips by flag.
- [x] Task 3.3: ✅ DONE (already proven by Task 1.2's `test_run_hand_never_raises_on_dispatch_failure` + Task 1.6's `_record_job_run` EVENT_JOB_ERROR path) — a crashing hand returns an error `HandResult` (never raises, RULE 2) and a crashing scheduled job writes a `scheduler_job_run` row with `status=error` rather than killing the scheduler or the other registered jobs. No new test needed — this was already covered by existing evidence; flagging it explicitly here closes the Phase 3 checklist honestly rather than leaving it `[ ]` when the work was already done under a different task number.

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
- [x] Task 5.1: `tests/integration/test_absorbed_autonomy.py::test_scheduler_fires_hands` ✅ DONE (2026-06-21) — real `AsyncIOScheduler`, `'date'` trigger ~1.5s future, test never calls `run_hand()` directly (only `HandRunner._dispatch` stubbed). Proved: real `kind="hand_run"` episodic row, real HP delta (500→550.0), real `policy_memory` row (`update_from_outcome`, avg_reward=1.0). Full artifact in `docs/capability_proofs/_phase5_autonomy_proof.md`.
- [x] Task 5.2: ✅ DONE (2026-06-21) — `pytest tests/hands tests/integration -v`: 1453 passed, 25 skipped, 2 known non-blocking failures (Ollama warmth; unrelated pre-existing `.env`-dependent test). `smoke_test.py` 38/38. `integration_check.py` 51/51.
- [ ] Task 5.3: Confirm every capability has a LIVE verdict in `docs/capability_proofs/` (this is the real definition-of-done — not green stubbed tests).
- [ ] Task 5.4: Three-question shipped check: (1) hand_run rows appear with no prompt; (2) repeated failure moved policy reward; (3) restart → scheduled hands resume.

### Soak-window finding (2026-06-21, before Task 5.4's 24-48h soak) — cron observability gap, fixed
Caught during pre-soak review of `scripts/check_soak.py` itself: most of the
~12 cron jobs (`subconscious_loop`, biometrics, daily_review, dspy, etc.)
write nowhere observable in `episodic_memory` on a HEALTHY run — several
only write a row on FAILURE (`job_nightly_selfcheck`'s `"selfcheck_failure"`
fires only inside `if problems:`). A soak with no independent firing record
can't distinguish "cron is still dead" from "cron fired but only logs
failures" — and a missed window can't be retroactively recovered. Fixed:
`core/loop/autonomous_loop.py::_record_job_run` — an APScheduler
`EVENT_JOB_EXECUTED | EVENT_JOB_ERROR` listener wired in
`_get_callable_scheduler()` — writes `event_type="scheduler_job_run"`
(ok/error + job_id) for EVERY job the scheduler fires, independent of what
the job itself logs. `scripts/check_soak.py` rewritten to verify against
this ground truth for both cron jobs and hands, not guessed event_type
strings. Regression tests: `tests/hands/test_real_scheduler.py` (+2,
success + failure cases). This is permanent observability, not just
soak-window plumbing — "which scheduled jobs actually ran" should always
be answerable from the DB.

### Ollama model-warmth — investigated 2026-06-21, partially fixed, rest deferred to post-soak (owner's call)
**Root cause confirmed empirically, not guessed:** loaded `vector-focus`, then loaded
`vector-reasoning` while focus was still resident — `ollama ps` showed ONLY
`vector-reasoning` afterward. Separately, `nomic-embed-text` (323MB, used
across 37 files for embeddings/RAG) was found loaded mid-session, evicting
whatever reasoning/focus model was there — confirming this isn't just
"the model is big," it's genuine **cross-subsystem contention**: any other
Ollama consumer in VECTOR (embeddings, voice, council) competes for the
same single `OLLAMA_MAX_LOADED_MODELS=1` slot.

VRAM math (corrected — `vector-reasoning` is qwen3:14b, GQA with only 8 KV
heads not 40, `block_count=40`, `key_length=value_length=128`): KV cache at
the Modelfile's `num_ctx=32768` is ~2.5GB at Q8 quant, not the ~12GB a naive
full-attention estimate would suggest. Weights at Q4_K_M ≈ 9.25GB. The
~20GB `ollama ps` figure likely includes additional compute/scratch buffers
that scale with context length during prefill — not fully resolved
analytically; would need empirical measurement at a few `num_ctx` values to
pin down precisely.

**Fixed now (safe, no tradeoff):** `hands/registry.py` — `researcher`
(08:00→**03:00** daily) and `predictor` (Mon 09:00→**Mon 03:00**) moved
off-peak. Both are one-shot/non-urgent (deep research, weekly forecast) —
no reason they needed daytime slots. `collector` (every 4h) and `trader`
(every 2h) deliberately left alone — their entire value is *frequent*
monitoring; collapsing them to off-peak-only would defeat their purpose,
and that's a product-cadence decision, not a bug fix.

**Deliberately NOT done — needs owner sign-off, deferred to post-soak as agreed:**
1. Reducing `modelfiles/vector-reasoning.modelfile`'s `num_ctx` from 32768.
   The comment there ("High context for complex chains") was a deliberate
   choice for Council deliberation quality — `_handle_red_tier()` truncates
   context to 400 chars in practice, so the large window may be unused
   headroom, but degrading Council's actual reasoning capability without
   the owner evaluating that tradeoff isn't a call to make unilaterally.
2. `OLLAMA_MAX_LOADED_MODELS=1→2` — would let `nomic-embed-text` (323MB)
   coexist with `vector-focus` (3.6GB) without evicting it, comfortably
   within the 12GB card. Requires changing a persistent Windows env var
   AND restarting the `ollama serve` system process — a system-level
   change outside what should happen unattended.
The soak (whenever it runs) will show empirically whether off-peak
scheduling alone is sufficient or whether one of these two is still needed.

---

## Pre-flight for executor (Sonnet)
- Always `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` (Windows cp1252 crashes on `→`; also fix `scripts/smoke_test.py` to not print raw arrows).
- **Phase 0 is mandatory and first.** Do not build the engine before knowing what actually runs. Report the Phase 0 triage to owner before Phase 2.
- A capability is DONE only when its `docs/capability_proofs/<repo>.md` says LIVE. Stubbed-green ≠ done.
- Scheduler: read `core/scheduler/` + reuse `core/loop/cron_jobs.py::_try_register`. Don't invent one.
- DB: `core.memory.episodic.get_db_connection()`/`close_db_connection()` only (SQLCipher).
- TDD per task; never bundle; no deletion in Phases 0–3.
```
