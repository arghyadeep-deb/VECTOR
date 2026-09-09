# R12-H — Persistence / State Integrity Audit

Read-only. HEAD audited: `81b53b1175aede4ed05d1b9d086af91dda64c8a6`. No production code or DB was modified in the course of this audit; `python core/brain/goal_system.py` / `python core/memory/policy.py` were deliberately NOT executed (see Finding 4).

## Objective

Determine the actual corruption/data-loss risk surface of VECTOR's SQLite persistence layer today, and whether anything is currently unsafe enough to block further learning-loop (R13+) work.

## Method

Direct source read of `core/memory/episodic.py`, `core/memory/db_utils.py`, `core/memory/policy.py`, `core/brain/goal_system.py`, `core/brain/epistemic_tracker.py`, `core/memory/counterfactual.py`, `tests/conftest.py`, plus a repo-wide grep for every test file that imports these modules and for `core/migration/`.

## Findings

### 1. Three separate SQLite databases exist, with two different isolation patterns

- **`vector_memory.db`** (episodic_memory, semantic_memory, policy_memory, reasoning_chains, skill_memory, agent_history, episodic_embeddings, session_turns) — one process-wide **singleton** connection (`core/memory/episodic.py:317` `_db_connection`, guarded by `_db_lock`/`_write_lock`). Path resolved by `core/memory/db_utils.py:12` `configured_db_path()`: `VECTOR_DB_PATH` env var wins if set, else `CONFIG["db_path"]`. `GoalSystem._persist()` (`core/brain/goal_system.py:216`) and `PolicyMemory` (all methods) both go through this singleton via `EpisodicMemory`/`get_temp_cursor()`, so they correctly inherit whatever isolation `VECTOR_DB_PATH` provides.
- **`epistemic.db`** (`core/brain/epistemic_tracker.py:19,29-43`) — **not** the singleton. Each `EpistemicTracker()` instance opens its **own** `sqlite3.connect()`, with an explicit `db_path` constructor param (`_DEFAULT_DB = CONFIG["data_dir"]/epistemic.db` if omitted). No `VECTOR_DB_PATH` support.
- **`counterfactual.db`** (`core/memory/counterfactual.py:58-72`) — identical shape: own connection, own `db_path` constructor param, no `VECTOR_DB_PATH` support.

**Consequence:** the isolation convention this whole session has relied on for tests (set `VECTOR_DB_PATH` before import) only isolates the first database. Any test that constructs a bare `EpistemicTracker()` or `CounterfactualMemory()` without passing `db_path=` explicitly still touches the real `data/epistemic.db` / `data/counterfactual.db` on disk, regardless of `VECTOR_DB_PATH`. This matches the summary's own note that E1/R10-style tests pass `db_path=` explicitly for CF/epistemic — that discipline is necessary, not optional, and is easy to forget since it's a *different* mechanism than the env var pattern used everywhere else.

**Risk:** MEDIUM. Not corruption, but a second, easy-to-miss real-data-mutation surface with a different isolation API than the one everybody now reflexively reaches for (`VECTOR_DB_PATH`).

### 2. No global test-suite isolation fixture — per-file discipline only

`tests/conftest.py` (repo-wide, autouse) sets up `VECTOR_TEST_DATA_DIR`, Windows event-loop policy, and a `PermissionGateway` singleton reset. **It does not set `VECTOR_DB_PATH`.** There is no autouse fixture anywhere that redirects the memory DB for the whole suite. Isolation is achieved entirely per-file, by whichever pattern that file's author chose:
- some files set `os.environ["VECTOR_DB_PATH"]` before any `core.*` import (the `test_e1_persistent_learning.py` / `test_r10_decision_provenance.py` / `test_task89c_goal_progress.py` / `test_r11_learning_integration.py` convention),
- some files fully `MagicMock()` every `DecisionEngine._get_*` accessor so the real DB is never opened at all (`test_task91_r6_candidate_diversity.py` and most `test_r11_*`/`test_e*` fixtures),
- and at least three files construct a bare, unmocked `GoalSystem()` and only *afterward* monkeypatch its instance attributes (Finding 3, below).

**Risk:** LOW-MEDIUM by itself (the second pattern above is safe, and the first is correct when used), but it means correctness depends on every future test author independently remembering the right pattern — there is no structural guardrail.

### 3. Three test files call bare `GoalSystem()` with no `VECTOR_DB_PATH` and no memory mock — safe today only by coincidence

`tests/test_e6_native_candidate_competition.py:134`, `tests/test_r11_end_to_end_trace.py:45`, and `tests/test_r11_native_goal_strategy_candidates.py:83` all do:
```python
gs = GoalSystem()          # __init__ -> _load_or_seed() -> real EpisodicMemory() -> REAL vector_memory.db
gs._persist = lambda: None # override AFTER construction
gs._goals = [...]          # override AFTER construction
```
Tracing `GoalSystem.__init__` → `_load_or_seed()` (`core/brain/goal_system.py:187-204`): it calls `self._get_memory()` (a real, unmocked `EpisodicMemory()` against whatever `configured_db_path()` currently resolves to — the real production DB in these three files) and `mem.recall_fact("goals_v1")`. Today this is a **read-only** call and returns early, because the real store already has a `goals_v1` row (confirmed present, 10 goals, from the R11 incident fix). The early-return branch also calls `self._merge_new_seeds()` (`goal_system.py:206-214`), which **does write** (`self._persist()`) — but only if it finds a `PRESEEDED_GOALS` id not already present in the real stored set. Today it finds none, so no write occurs.

This means these three tests are safe **only because the current real DB state happens to already contain every `PRESEEDED_GOALS` id**. The moment a future change adds one new entry to `PRESEEDED_GOALS` (a plausible, likely R13 action — R11's own report recommends exactly this: "extend tag vocabulary... revenue/equation/startups/..." adjacent goal seeding is a natural companion change), the very next `pytest` run of these three files will silently call `_merge_new_seeds()` → `_persist()` against the **real production goal store**, before the test's own override takes effect — reproducing the exact incident already disclosed once in the R11 report (`python core/brain/goal_system.py` mutating real data), except this time triggered by routine `pytest`, not a manual sanity-check command.

**Risk:** HIGH for the *next* wave specifically, because R13 (per the master mission prompt) is explicitly about expanding tag/strategy coverage and may plausibly touch `PRESEEDED_GOALS` or the tag vocabulary. This is a latent trap that will not fail loudly — it fails by silently writing into the owner's real goal list.

**Recommended remediation (not performed — read-only audit):** either (a) add `VECTOR_DB_PATH` isolation to these three call sites' setup, matching the `test_r11_learning_integration.py` convention, or (b) mock `GoalSystem._get_memory` before construction in these three files, matching the `_get_policy`/`_get_goals` MagicMock convention already used everywhere else in this session's own new tests. (b) is more consistent with how the *other* 29 files already avoid this exact hazard.

### 4. `goal_system.py` and `policy.py` both still have `__main__` self-tests that mutate the real DB when run directly

`core/brain/goal_system.py`'s `if __name__ == "__main__":` block (confirmed present from the R11 incident) and `core/memory/policy.py:265-313`'s block both instantiate real, unmocked objects against whatever `configured_db_path()` resolves to with no env var set — i.e., the real production DB — and call real mutating methods (`update_goal_progress`, `add_goal`-shaped writes via `_persist()`, `update_from_outcome()`). `policy.py`'s block is comparatively low-risk (it writes throwaway rows under unique `smoke_*_{uuid}` keys, never touches real owner data, and there is no real-world meaning attached to a stray `policy_memory` row) — but `goal_system.py`'s block is the exact mechanism that caused the incident already disclosed in the R11 report. **This was not fixed as part of R11** (R11's fix was to the running production code path, not to the file's own self-test convention required by `.claude/rules/code_style.md`'s "Every File Must Have... `if __name__ == "__main__":`" rule).

**Risk:** HIGH but easily avoidable — this is a "don't run this command" hazard, not a design defect, but it is the second time in this project's own session history that exactly this command has been the proximate cause of real data mutation. Given the codebase-wide convention that *every* file must carry a real, no-mock `__main__` block, this hazard is structural, not confined to `goal_system.py` — any file whose real self-test path reaches `EpisodicMemory()`/`GoalSystem()`/`PolicyMemory()` shares it. Not something a future orchestrator agent should ever invoke directly on `goal_system.py` (or any `core/brain/*.py` / `core/memory/*.py` file) without first setting `VECTOR_DB_PATH` in that shell.

### 5. Connection lifecycle / restart behavior — sound

`close_db_connection()` (`episodic.py:348-393`) correctly closes the singleton, clears the cached `_DB_KEY` in the same lock (preventing the stale-key hazard its own comment documents), resets the episodic circuit breaker, and resets the shared `MemoryTree` singleton in lockstep — this is exactly the mechanism `test_r11_learning_integration.py`'s genuine-restart test correctly relies on, and it is doing the right thing. `get_db_connection()` re-detects a closed connection (`_is_connection_closed`, handling sqlcipher3's non-standard `ProgrammingError` by name) and transparently reopens — no user-visible restart hazard found.

WAL mode + `busy_timeout=5000` (`db_utils.py:38-42`, and again explicitly in `_open_sqlcipher_connection`) is applied consistently across all three databases (`apply_pragmas()` is shared), which is the correct mitigation for the multi-connection-per-file pattern epistemic/counterfactual use (Finding 1) — concurrent readers/writers to the same file should not deadlock or corrupt, only serialize with a bounded wait.

### 6. Concurrency — `_write_lock` correctly serializes `vector_memory.db`; epistemic/counterfactual have no equivalent

`get_temp_cursor()` (`episodic.py:651-669`) holds `_write_lock` (a process-wide `threading.RLock`) for its entire `with` block, and `PolicyMemory.update_from_outcome()`'s own docstring (`policy.py:113-122`) explicitly documents that this is what makes its read-modify-write online-average atomic across threads. Confirmed correct: the read, the arithmetic, and the write all happen inside one `get_temp_cursor()` block, so no lost-update race is possible for `vector_memory.db` tables.

`EpistemicTracker` and `CounterfactualMemory` have **no equivalent write lock** — each holds its own `sqlite3.Connection` with no explicit application-level locking beyond SQLite's own `busy_timeout`. For a single-process VECTOR (the current deployment model — one `run_vector.py` process, no multi-process deployment), this is not currently a demonstrated bug, since Python's GIL plus SQLite's own internal locking prevents true concurrent writes from corrupting a row; a genuine read-modify-write race (two coroutines updating the same claim's confidence in the same tick) is theoretically possible if either module ever grows a read-then-write sequence spanning an `await` point, but no such sequence was found in the code read for this audit.

**Risk:** LOW today (single-process, and no read-modify-write-across-await pattern found), but worth flagging before any future multi-process or heavier-concurrency runtime change (R20 territory).

### 7. Migrations — no versioned migration runner for the 5 sacred tables; idempotent inline `ALTER TABLE` checks only

There is no `_migrations` table or version-tracked runner for `episodic_memory` / `semantic_memory` / `policy_memory` / `reasoning_chains` / `agent_history` (the five tables `.claude/rules/memory.md` calls "Never Rename"). Schema evolution is instead handled by small idempotent helper functions called on every connection open: `_ensure_policy_columns()` (adds `veto_count` if missing, `episodic.py:610-621`) and `_ensure_decay_columns()` (adds `stability_days`/`last_touch` to `episodic_memory`/`reasoning_chains` if missing, `episodic.py:631-648`), each guarded by a `PRAGMA table_info` check before `ALTER TABLE ADD COLUMN`. This is safe for the case it's used for (additive, nullable-default columns) and has been used correctly twice already (Task 89's `veto_count`, the 2026-07-29 decay columns) with historical rows genuinely left untouched per their own comments. It is not a general migration system: it has no rollback, no schema-version record, and would not by itself handle a column *rename*, *type change*, or *drop* safely — but `.claude/rules/memory.md` already forbids renaming/dropping these tables' columns, so the mechanism matches the one kind of change it's allowed to make.

(A separate, unrelated `core/migration/importer.py` exists — this is a cross-instance data importer, not a schema migration runner, and is out of scope for this finding.)

**Risk:** LOW today given the additive-only convention holds; would become a real gap only if a future milestone needed a genuinely destructive schema change (not expected in R13-R20 scope as written).

### 8. `EpisodicMemory.__main__` self-test — also touches the real DB

`episodic.py:1440-1456`'s own `if __name__ == "__main__":` block instantiates a real `EpisodicMemory()` and calls real `store()`/`remember()`/`store_chain()` against whatever DB `configured_db_path()` resolves to. Lower practical risk than `goal_system.py`'s block (it writes generic test rows like `'VECTOR started for first time'`/`'owner_name'` — the latter, `remember('owner_name', 'Arghyadeep', ...)`, **does** overwrite the real `semantic_memory` row keyed `owner_name` with the literal string `'Arghyadeep'` on every run, which happens to already be correct but is a real, unconditional overwrite of real semantic memory nonetheless).

## Risk Table

| # | Finding | Class | Blocks R13? |
|---|---|---|---|
| 1 | epistemic.db / counterfactual.db use a different isolation mechanism (constructor `db_path=`) than `VECTOR_DB_PATH` | Consistency / latent test hazard | No, but must be remembered by any new test touching those two modules |
| 2 | No global `VECTOR_DB_PATH` test-suite fixture | Structural gap | No — current per-file discipline works today |
| 3 | 3 test files (`test_e6_native_candidate_competition.py`, `test_r11_end_to_end_trace.py`, `test_r11_native_goal_strategy_candidates.py`) construct bare `GoalSystem()` unsafely | **Live landmine for R13** | **Yes — should be fixed before/alongside any `PRESEEDED_GOALS` change** |
| 4 | `goal_system.py __main__` (and, lower severity, `policy.py __main__`) mutate real DB if run directly without `VECTOR_DB_PATH` | Operational hazard (already caused one real incident) | No — just: never run these directly without isolation |
| 5 | Connection lifecycle / restart | Sound | No |
| 6 | No write-lock in epistemic/counterfactual | Low, theoretical | No |
| 7 | No versioned migration runner (additive-only inline checks) | Low, matches current constraints | No |
| 8 | `episodic.py __main__` overwrites real `owner_name` semantic row | Low (currently harmless — writes the correct value) | No |

## Current Capability Level

Persistence itself is at **PRODUCTION_VERIFIED** for the restart/atomicity properties R11's own learning-integration test already exercises (genuine `close_db_connection()` + reopen, exact score survival, `_write_lock`-atomic online averaging). Test-suite *isolation* discipline, by contrast, is **TEST_VERIFIED at best, and only per-file** — there is no suite-wide guarantee, and Finding 3 is a concrete, not hypothetical, gap in that guarantee given R13's likely shape.

## What's Broken vs. Working

**Working:** singleton lifecycle, WAL+busy_timeout concurrency mitigation, `_write_lock`-atomic policy updates, additive-only schema evolution, `close_db_connection()`'s stale-key-clearing correctness.

**Not broken, but a real gap:** no structural (fixture-level) guarantee against a test touching real production data; three specific existing test files rely on current DB contents matching `PRESEEDED_GOALS` rather than genuine isolation.

## Recommended Next Milestone

Before or alongside R13 (which is likely to touch tag/goal vocabulary): retrofit the three unsafe `GoalSystem()` test call sites (Finding 3) with either explicit `VECTOR_DB_PATH` isolation or a `_get_memory` mock, matching the convention the other 29 test files already use correctly. This is a small, targeted, test-only fix — no production code change required — and directly removes the one HIGH-risk item this audit found that R13 could plausibly trigger.

## Open Questions

- Should `EpistemicTracker`/`CounterfactualMemory` gain `VECTOR_DB_PATH` support for consistency with the rest of the memory layer, or is the explicit-`db_path=` convention intentional/preferred for those two (e.g. because they are sometimes intentionally instantiated with a non-default path in production, unlike `EpisodicMemory`)? Not determined by this read-only audit — worth a targeted question to whoever designed R9's epistemic isolation tests.
- Is a `tests/conftest.py` autouse `VECTOR_DB_PATH` fixture desirable at all, given some tests (integration tests exercising real cross-restart behavior) *need* a real, non-autouse-overridden path per test? Not answered here — flagging for orchestrator synthesis rather than deciding unilaterally, since it's a test-architecture decision with tradeoffs, not a pure bug.
