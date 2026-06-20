# Wire Absorbed Repos → Full VECTOR Autonomy — Implementation Plan

**Author:** Opus 4.8 (planning) · **Executor:** Sonnet 4.6 (execution)
**Date:** 2026-06-20

**Goal:** Make every absorbed capability (investment/Fincept, research_engine, trading, scraper, coding_assistant) run *proactively without owner interference* — not just be routable when asked.

**Architecture:** The absorbed repos are already (a) imported by district agents and (b) routable via `core/city/governor.py` (634 routes → 131 districts). What is MISSING is the **proactive trigger + closed feedback loop**. The intended proactive layer — `hands/registry.py` (9 scheduled "Hands") — is fully specified but **orphaned** (`HandRegistry` has zero references outside `hands/`; nothing executes it). This plan builds the missing **Hand Execution Engine**, wires it into the autonomous loop's scheduler, activates each absorbed repo through it, and closes the result→memory→HP→decision loop so VECTOR acts on what it produces.

**Root-cause findings (verified in code, 2026-06-20):**
- `HandRegistry` (9 hands w/ cron schedules + tools + system prompts) — defined, NEVER executed. Grep: 0 refs outside `hands/`.
- Only `research_engine` self-triggers (`autonomous_loop.research_loop()`), but it is gated behind `CONFIG["research_lab"]["enabled"]` (off by default) and uses **hardcoded** topics.
- 2 hands are `schedule=""` (manual-only): `browser`, `clip`.
- `cron_jobs.register_default_jobs()` and the Hand registry are two **separate, unconnected** systems.
- Capability outputs are not consistently fed back into `episodic`/`reasoning_memory`/`policy` (HP) — autonomy without learning.

**Scope note:** This is one deliverable (proactive autonomy) but 5 phases. Phase 0 is the foundation everything depends on — do it first, fully tested, before any other phase. Execute phase-by-phase; each phase is independently testable and committable.

**Files:**
- Create: `hands/runner.py` (Hand Execution Engine)
- Create: `hands/result.py` (HandResult dataclass + persistence)
- Create: `tests/hands/test_hand_runner.py`, `tests/hands/test_hand_result.py`, `tests/hands/test_hands_wired.py`
- Create: `tests/integration/test_absorbed_autonomy.py`
- Modify: `core/loop/autonomous_loop.py` (start HandRunner in `run_forever`)
- Modify: `core/loop/cron_jobs.py` (reuse `_try_register*` for hands OR expose helper)
- Modify: `hands/registry.py` (add executable `handler`/resolver hooks; fill the 2 empty schedules or mark explicitly `on_demand=True`)
- Modify: `core/config.py` (flip `research_lab.enabled`, add `hands` config block)
- Modify: `core/loop/autonomous_loop.py::research_loop` (dynamic topics from goals/context)

---

## PHASE 0 — Hand Execution Engine (FOUNDATION — blocks everything)

The linchpin. Until a Hand can actually run on schedule, nothing else is autonomous.

### Task 0.1: HandResult dataclass + memory persistence

- [ ] Write failing test `tests/hands/test_hand_result.py`
  ```python
  from hands.result import HandResult
  def test_hand_result_persists_to_episodic(tmp_path, monkeypatch):
      r = HandResult(hand="researcher", district="research",
                     output="report body", status="ok",
                     artifacts={"report_md": "..."}, hp_delta=50)
      row_id = r.persist()              # writes to episodic_memory
      assert isinstance(row_id, int) and row_id > 0
      assert r.to_dict()["status"] == "ok"
  ```
- [ ] Run: `pytest tests/hands/test_hand_result.py -v` → expect FAIL (module missing)
- [ ] Implement `hands/result.py`: `HandResult` dataclass; `.persist()` calls `core.memory.episodic.add_episode(kind="hand_run", ...)` via `get_db_connection()`/`close_db_connection()` (RULE: never open the encrypted DB with raw sqlite3); `.to_dict()`.
- [ ] Run: `pytest tests/hands/test_hand_result.py -v` → expect PASS
- [ ] Commit: `git commit -m "feat(hands): HandResult dataclass + episodic persistence"`

### Task 0.2: HandRunner executes one hand end-to-end

- [ ] Write failing test `tests/hands/test_hand_runner.py`
  ```python
  import asyncio
  from hands.runner import HandRunner
  from hands.registry import HandRegistry
  def test_runner_executes_hand_via_governor(monkeypatch):
      runner = HandRunner()
      hand = HandRegistry().get("researcher")
      # stub the district call so the test is offline/deterministic
      monkeypatch.setattr(runner, "_dispatch", lambda h, ctx: "stub report")
      result = asyncio.run(runner.run_hand(hand, context={"topic": "AI agents"}))
      assert result.status == "ok"
      assert result.hand == "researcher"
      assert result.output  # non-empty
  ```
- [ ] Run: `pytest tests/hands/test_hand_runner.py::test_runner_executes_hand_via_governor -v` → expect FAIL
- [ ] Implement `hands/runner.py::HandRunner.run_hand(hand, context)`:
  1. Build hydrated context: `ContextEngine().session_hydration_prompt()` + hand.system_prompt + context (RULE 1 — hydrate before every LLM call).
  2. `_dispatch(hand, ctx)` → route through `core.city.governor.Governor.route(task_type=..., district=hand.district)` so the hand runs as the district's agent (HP-bearing). Map each hand to a governor task_type (researcher→`deep_research`, trader→`trading_analysis`, collector→`osint_collect`, content→`content_generate`, lead→`lead_research`, predictor→`forecast`, vault_sync→`vault_sync`).
  3. `requires_approval` → if True, gate through `core.loop.permission_gateway.PermissionGateway` before acting (RED-tier hands wait for Pushover approval).
  4. Wrap in `asyncio.timeout(hand_timeout)`; on error return `HandResult(status="error", ...)` — never raise (RULE 2).
  5. Persist result; return it.
- [ ] Run test → expect PASS
- [ ] Commit: `git commit -m "feat(hands): HandRunner.run_hand end-to-end via governor"`

### Task 0.3: Closed feedback loop — result → memory → HP → policy

- [ ] Write failing test in `tests/hands/test_hand_runner.py`
  ```python
  def test_run_hand_closes_feedback_loop(monkeypatch):
      runner = HandRunner()
      hand = HandRegistry().get("researcher")
      calls = {"episodic": 0, "hp": 0, "policy": 0}
      monkeypatch.setattr(runner, "_record_episodic", lambda *a, **k: calls.__setitem__("episodic", calls["episodic"]+1))
      monkeypatch.setattr(runner, "_award_hp",        lambda *a, **k: calls.__setitem__("hp", calls["hp"]+1))
      monkeypatch.setattr(runner, "_update_policy",    lambda *a, **k: calls.__setitem__("policy", calls["policy"]+1))
      monkeypatch.setattr(runner, "_dispatch", lambda h, ctx: "stub")
      import asyncio; asyncio.run(runner.run_hand(hand, {}))
      assert calls == {"episodic": 1, "hp": 1, "policy": 1}
  ```
- [ ] Run → expect FAIL
- [ ] Implement feedback in `run_hand`: after dispatch, call `_record_episodic` (episodic + reasoning_memory), `_award_hp` (district agent via `agent_registry`, +50 ok / -30 error per HP rules), `_update_policy` (`core.memory.policy.update_from_outcome(action_type, situation, reward)`). This is what turns "it ran" into "it learns" — the difference between automation and autonomy.
- [ ] Run → expect PASS
- [ ] Commit: `git commit -m "feat(hands): close result→episodic→HP→policy feedback loop"`

### Task 0.4: HandRunner schedules all enabled hands into the durable scheduler

- [ ] Write failing test `tests/hands/test_hands_wired.py`
  ```python
  from hands.runner import HandRunner
  class FakeScheduler:
      def __init__(self): self.jobs = []
      def add_job(self, fn, *a, **k): self.jobs.append(k.get("id") or getattr(fn,"__name__",""))
  def test_runner_registers_scheduled_hands():
      sched = FakeScheduler()
      n = HandRunner().register_all(sched)
      # 7 hands have cron schedules (2 are on-demand only)
      assert n == 7
      assert any("researcher" in j for j in sched.jobs)
      assert any("trader" in j for j in sched.jobs)
  ```
- [ ] Run → expect FAIL
- [ ] Implement `HandRunner.register_all(scheduler)`: iterate `HandRegistry().list_enabled()`, skip `schedule==""` (on-demand), register each cron via the **existing** defensive helpers in `core/loop/cron_jobs.py` (`_try_register`) so we reuse the proven multi-API scheduler seam. Each job = `lambda h=hand: asyncio.run(self.run_hand(h, self._auto_context(h)))`.
- [ ] Run → expect PASS
- [ ] Commit: `git commit -m "feat(hands): register_all wires scheduled hands into durable scheduler"`

### Task 0.5: Start HandRunner in the autonomous loop

- [ ] Write failing test `tests/hands/test_hands_wired.py::test_loop_starts_hand_runner`
  ```python
  import inspect, core.loop.autonomous_loop as al
  def test_loop_starts_hand_runner():
      src = inspect.getsource(al)
      assert "HandRunner" in src and "register_all" in src
  ```
- [ ] Run → expect FAIL
- [ ] Modify `core/loop/autonomous_loop.py::run_forever` (near the existing scheduler/cron registration, ~line 1745–1845): after `register_default_jobs(scheduler)`, add `HandRunner().register_all(scheduler)` inside try/except (warn on failure, never crash startup).
- [ ] Run: `pytest tests/hands/ -v` and `python scripts/integration_check.py` → expect PASS
- [ ] Commit: `git commit -m "feat(loop): start HandRunner — 9 hands now actually execute"`

**Phase 0 done = the 9 'autonomous agents' are real for the first time.**

---

## PHASE 1 — Activate research_engine fully (closest to done)

### Task 1.1: Enable research_lab + dynamic topics from goals/context

- [ ] Write failing test `tests/integration/test_absorbed_autonomy.py::test_research_topics_are_dynamic`
  ```python
  from core.loop.autonomous_loop import AutonomousLoop
  def test_research_topics_are_dynamic(monkeypatch):
      loop = AutonomousLoop()
      topics = loop._research_topics()        # new helper
      assert isinstance(topics, list) and topics
      assert "recent advances in AI agents" not in topics or len(topics) > 2  # not ONLY hardcoded
  ```
- [ ] Run → expect FAIL
- [ ] Implement `AutonomousLoop._research_topics()`: pull from `goal_system.get_active_goals()` (LONG/MID horizons) + `context_engine` recent interests + epistemic tracker's known-unknowns (`core/brain/epistemic_tracker.py`). Replace hardcoded list in `research_loop()`.
- [ ] In `core/config.py` set `research_lab.enabled = True` (default-on for autonomy) and `schedule_interval_hours` sane (e.g. 6).
- [ ] Run → expect PASS
- [ ] Commit: `git commit -m "feat(research): dynamic topics from goals + enable research_lab"`

---

## PHASE 2 — Wire each absorbed repo's proactive path through Hands

One task per repo. Each: confirm the hand's `_dispatch` reaches real code (not a stub), with an offline test.

### Task 2.1: investment/Fincept via `trader` hand

- [ ] Write failing test `tests/integration/test_absorbed_autonomy.py::test_trader_hand_reaches_investment`
  ```python
  from hands.runner import HandRunner
  from hands.registry import HandRegistry
  def test_trader_hand_reaches_investment(monkeypatch):
      hits = {}
      import districts.investment.trading_conductor_agent as tc
      monkeypatch.setattr(tc, "VectorTradingGraph", lambda *a, **k: hits.setdefault("built", True) or object())
      # assert HandRunner maps 'trader' -> investment district task_type
      assert HandRunner()._task_type_for(HandRegistry().get("trader")) == "trading_analysis"
  ```
- [ ] Run → expect FAIL
- [ ] Implement `_task_type_for` mapping table in `HandRunner`; verify `trading_analysis` is in `governor.py` routes (it is — line ~193). Confirm `trader` hand's auto-context provides a watchlist (from `CONFIG["investment"]["watchlist"]`).
- [ ] Run → expect PASS · Commit: `git commit -m "feat(hands): trader hand -> investment district, proactive"`

### Task 2.2: research_engine OSINT via `collector` hand (every 4h)
- [ ] Same pattern: map `collector`→`osint_collect`; add route to `governor.py` if missing; auto-context = monitored targets from `CONFIG`. Test reaches `districts/research`. Commit.

### Task 2.3: content district via `content` hand (Mon/Wed/Fri)
- [ ] Map `content`→`content_generate`; `requires_approval=True` (RED — publishing). Verify gateway gating. Test. Commit.

### Task 2.4: scraper — confirm it stays infrastructure (no standalone hand)
- [ ] Write test asserting scraper is reached by `collector`/`web_scout` paths (it's a tool, not a standalone autonomous capability — correct as-is). Document decision in plan. Commit.

### Task 2.5: coding_assistant — optional self-maintenance hand
- [ ] Decision gate (ask owner): add a `maintainer` hand that runs code review/refactor on VECTOR's own repo weekly? If yes: new hand + `code_review` route. If no: leave reactive. Default: **skip** unless owner says yes.

---

## PHASE 3 — Harden the autonomy (no-interference guarantees)

### Task 3.1: Every RED hand output gated; every notable result notifies owner
- [ ] Test: a `requires_approval=True` hand never executes its side effect without `PermissionGateway` approval; high-signal results (`hp_delta>=50` or `status=="alert"`) push via `pushover`.
- [ ] Implement in `run_hand`. Commit.

### Task 3.2: Fill or explicitly mark the 2 empty schedules
- [ ] `browser` + `clip` hands: either give a cron OR add `on_demand=True` field so "no schedule" is intentional, not a bug. Test that `register_all` skips on-demand hands by flag, not by empty string. Commit.

### Task 3.3: Loop resilience — a crashing hand never kills the scheduler
- [ ] Test: `run_hand` raising still returns/records an error HandResult and the scheduler keeps firing other hands. Commit.

---

## PHASE 4 — Prune dead weight *within* repos (optional, low priority)

Not deletion of repos (they're wired) — removal of unreachable submodules inside them.

### Task 4.1: Reachability report
- [ ] Create `scripts/absorbed_reachability.py`: static-import-graph from each district agent entrypoint into the absorbed lib; emit `docs/absorbed_reachability.md` listing reached vs unreached modules (e.g. which of `districts/investment/alpha_zoo/*` are ever imported).
- [ ] Run it; review with owner before deleting anything. No deletions in this plan without owner sign-off (memory: never delete what you didn't create without surfacing).

---

## PHASE 5 — Autonomy proof (the "shipped" gate)

### Task 5.1: Integration test — scheduler actually fires hands
- [ ] `tests/integration/test_absorbed_autonomy.py::test_scheduler_fires_hands_end_to_end`: start loop with a fake fast clock, assert ≥1 hand produces a persisted HandResult with closed-loop side effects (episodic row + HP delta), offline.
- [ ] Run full suite: `pytest tests/hands tests/integration -v` + `python scripts/smoke_test.py` (with `PYTHONUTF8=1`) + `python scripts/integration_check.py`. All green.
- [ ] Commit: `git commit -m "test: end-to-end absorbed-repo autonomy verified"`

### Task 5.2: Three-question shipped check (run manually, document in plan)
1. Did a hand do something useful with no prompt? (check episodic for `kind=hand_run` rows)
2. Does a repeated failure change behavior next run? (policy reward moved)
3. Restart VECTOR — do scheduled hands resume? (session persistence + scheduler re-registers)

---

## Pre-flight for the executor (Sonnet)
- Fix the known smoke-test Unicode bug first OR always run with `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` (Windows cp1252 crashes on `→`).
- Confirm scheduler module path/API by reading `core/scheduler/` + reusing `core/loop/cron_jobs.py::_try_register` (do NOT invent a new scheduler).
- DB access ALWAYS via `core.memory.episodic.get_db_connection()` / `close_db_connection()` (SQLCipher) — never raw sqlite3.
- TDD every task: failing test → implement → pass → commit. Do not bundle.
- Do not delete any absorbed code in Phases 0–3.
```
