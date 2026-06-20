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

## PHASE 1 — Hand Execution Engine (orchestration foundation)

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
- [ ] Test PASS · `git commit -m "feat(hands): register scheduled hands"`

### Task 1.5: Start in autonomous loop
- [ ] Failing test: `inspect.getsource(autonomous_loop)` contains `HandRunner` + `register_all`.
- [ ] Modify `core/loop/autonomous_loop.py::run_forever` (after `register_default_jobs`, ~L1745–1845): `HandRunner().register_all(scheduler)` in try/except.
- [ ] Run `pytest tests/hands -v` + `python scripts/integration_check.py` PASS · `git commit -m "feat(loop): hands now execute"`

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

## PHASE 4 — Prune provably-dead code (optional, owner sign-off required)
- [ ] Task 4.1: Extend `scripts/capability_smoke.py --deadcode` → static import-graph from each district entrypoint into the absorbed lib; emit `docs/absorbed_reachability.md` (reached vs never-imported modules).
- [ ] Task 4.2: **Surface list to owner. Delete nothing without sign-off** (memory rule: never delete what you didn't create without surfacing). Quarantine candidates → move to `_attic/` first, run full suite, then delete in a later pass.

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
