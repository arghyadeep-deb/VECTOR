# VECTOR Memory & Persistence Audit — 2026-08-05

Scope: `core/memory/*`, `core/engine/memory_tree/tree_builder.py`, `core/loop/loop_state.py`.
Read-only audit. VECTOR was live throughout (pid 14328) — not touched. No writes made to
`vector_memory.db`. All probes ran against throwaway files in the scratch dir or read-only
inspection of the live filesystem/log evidence.

Severity scale: **CRITICAL** (silent data loss / broken subsystem in production) → **HIGH**
(real correctness bug, will bite under normal operation) → **MEDIUM** (real but narrow /
latent) → **LOW** (hygiene, no observed impact).

---

## Previously-fixed items — re-verified, still sound

- **`_get_db_key()` / `close_db_connection()` key-reset (8dfe36bce).** Confirmed sound.
  `close_db_connection()` (`core/memory/episodic.py:348-393`) clears `_DB_KEY = None` in the
  *same* `_db_lock` critical section that clears `_db_connection`, so a later
  `get_db_connection()` cannot reopen with a stale cached key. Verified by reading the code
  path end-to-end; the fix comment at lines 361-373 correctly describes the hazard it closes.
- **Ebbinghaus decay/tiering modules.** `core/memory/decay.py` and `core/memory/tiering.py`
  are present, imported by `episodic.py`, and their embedded self-tests
  (`should_evict`/`reinforce`/`retention` boundary cases) check out arithmetically by
  inspection (`R(t)=e^{-t/S}`, eviction at `R<0.05`, reinforcement `×1.3` capped at 365d).
  Both tables (`episodic_memory`, `reasoning_chains`) get `stability_days`/`last_touch`
  columns via `_ensure_decay_columns()`, called on every `_create_tables()`.
- **Six-test-file DB pollution fix.** Re-spot-checked: `tests/backend/test_memory_quality.py`,
  `test_memory_concurrency_safety.py`, `test_mcp_memory_safety.py`,
  `test_memory_tree_performance.py`, `test_multi_db_mesh.py` and others under `tests/hands/`,
  `tests/integration/` now monkeypatch `VECTOR_DB_PATH` per-test. Not re-litigating the
  already-accepted 28,083 legacy rows.

---

## CONFIRMED — CRITICAL

### 1. `core/memory/shared_facts.py` — SQLCipher rule violation, whole subsystem silently dead

`SharedFacts` (Gap 8, cross-agent fact consensus) defaults to the **main encrypted DB path**
(`_DB_PATH = configured_db_path()`, module level, `core/memory/shared_facts.py:22`) but opens
it with **plain `sqlite3.connect()`** (`_conn()`, line 39) — never through
`core.memory.episodic.get_db_connection()` / `_open_sqlcipher_connection()`.

Reproduced the exact failure mode in the scratch dir (not against the live DB): creating a
real SQLCipher-keyed file and then opening it with plain `sqlite3.connect()` raises

```
sqlite3.DatabaseError: file is not a database
```

`sqlcipher3` is installed and active in this environment (`_USE_SQLCIPHER=True`), so every
real `SharedFacts()` construction against the production DB hits this on `_init_db()`
(called from `__init__`), and every subsequent `.set()/.get()/.vote()/.all_facts()` would hit
it again even if construction somehow succeeded.

The only two call sites are `core/city/agent_base.py:321-340` (`AgentBase.know()` /
`AgentBase.recall_fact()`), used by every one of VECTOR's 200+ agent files:

```python
def know(self, key: str, value) -> None:
    self._facts[key] = value
    try:
        from core.memory.shared_facts import SharedFacts
        SharedFacts().set(key, value, source=self.name)      # <-- fails, see below
    except Exception:
        logger.warning("[VECTOR] silent swallow")
        pass
```

Both call sites wrap the call in a bare `except Exception: pass` (with only a generic
`"silent swallow"` warning, no exception detail). **Net effect: cross-agent fact sharing has
been a complete no-op in production** — every agent's `know()` only ever lands in that
agent's own in-process `self._facts` dict, which dies with the agent instance; nothing is
ever actually shared or persisted. This is the textbook "persistence that appears to work"
failure mode: `know()` returns normally, callers have no way to notice.

**Independent secondary bug, same call site:** `agent_base.py:326` calls
`SharedFacts().set(key, value, source=self.name)`, but `SharedFacts.set()`'s real signature
(`shared_facts.py:66`) is `set(self, key, value, confidence=0.5, source_agent="unknown")` —
there is no `source` parameter. Even if the SQLCipher bug were fixed, this call raises
`TypeError: set() got an unexpected keyword argument 'source'` on every single invocation,
also silently swallowed by the same `except Exception: pass`.

**Fix direction:** route `SharedFacts._conn()` through
`core.memory.episodic.get_db_connection()` (or at minimum `_open_sqlcipher_connection()`
when `_USE_SQLCIPHER`) the same way `districts/emergency/log.py:_open_conn()` and
`core/avatar/avatar_state.py:_get_conn()` already correctly do; fix the `source=` /
`source_agent=` mismatch in `agent_base.py`; stop swallowing the exception type so this class
of failure is visible in logs going forward.

---

## CONFIRMED — HIGH

### 2. `core/memory/policy.py` and `core/memory/reasoning_memory.py` bypass `_write_lock` — race + stale-connection risk on RULE 7 / RULE 8

Every write/read in `episodic.py` itself goes through `get_temp_cursor()`
(`episodic.py:628-646`), which holds the module-level `_write_lock` (`threading.RLock`) for
the whole operation — this is the *only* thing serializing concurrent threads against the one
shared `sqlite3.Connection` singleton (`check_same_thread=False`, so nothing else stops two
threads from calling into it at once).

`PolicyMemory` (`core/memory/policy.py:46-98`) and `ReasoningMemory`
(`core/memory/reasoning_memory.py:113-135, 182-221`) do **not** use `get_temp_cursor()`. They
grab `self._get_mem().conn` once and call `conn.execute(...)` / `conn.commit()` directly,
completely outside `_write_lock`. `core/memory/causal_graph.py` (`_conn()`/`_init_db()`,
lines 45-86) has the same pattern for its own `conn.execute()` calls (it re-fetches
`get_db_connection()` fresh each time so avoids finding #2b below, but still bypasses the
lock for #2a).

Two concrete consequences of bypassing the lock:

**2a. Lost-update race in `PolicyMemory.update_from_outcome()` (RULE 7).** The online average
update is a classic unprotected read-modify-write:

```python
row = conn.execute("SELECT avg_reward, sample_count FROM policy_memory WHERE ...").fetchone()
...
new_avg = (old_avg * n + reward) / (n + 1)
conn.execute("UPDATE policy_memory SET avg_reward=?, sample_count=?, ... WHERE ...", ...)
conn.commit()
```

Two threads calling `update_from_outcome()` for the same `(action_type, situation_hash)`
concurrently (very plausible — RULE 7 requires this be called after *every* action, from
potentially-parallel district-agent tasks and `asyncio.to_thread` workers) can both read the
same `(old_avg, n)`, compute independently, and the second commit silently clobbers the
first's update — one reward sample is lost from the average with no error, no log line, and
no way to detect it after the fact. This directly degrades the RULE 7 policy-learning signal
the decision engine relies on.

**2b. Stale cached connection — same defect class as already-documented KNOWN_ISSUES #21.**
`consolidation_bot.py:94-97` documents (for `pattern_finder.py`, already fixed there) that
"a cached `self._memory.conn` never sees `get_db_connection()`'s self-healing
reopen-if-closed logic." `PolicyMemory._get_mem()` and `ReasoningMemory._get_mem()`
(`policy.py:24-28`, `reasoning_memory.py:18-22`) have the **identical, still-unfixed**
pattern: they lazily construct `EpisodicMemory()` once and cache `self._mem`, then reuse
`self._mem.conn` forever. If the singleton connection is ever closed and reopened while a
`PolicyMemory`/`ReasoningMemory` instance is already alive (test teardown calling
`close_db_connection()`, a SQLCipher repair cycle, etc.), every subsequent policy/reasoning
call silently fails — caught by each method's own broad `except Exception`, logged at
`error`/`debug`, and papered over by returning `DEFAULT_SCORE` / `[]` / `""`. RULE 7 and
RULE 8 both go dark with no crash and no visible signal.

**Fix direction:** route all of `policy.py`/`reasoning_memory.py`/`causal_graph.py`'s raw SQL
through `get_temp_cursor()` (or at minimum acquire `episodic.get_db_write_lock()` around the
existing `conn.execute()` calls, and call `get_db_connection()` fresh per operation instead of
caching `.conn`).

### 3. SUSPECTED — plausible concrete mechanism for the ~5.5h autonomous-loop stall (KNOWN_ISSUES #0)

Marked **SUSPECTED**: root cause is not proven (no thread dump exists — `KNOWN_ISSUES.md`
itself says so), but static analysis turned up a mechanism that matches every piece of
recorded evidence exactly, and it lives entirely inside this audit's scope.

Evidence from `KNOWN_ISSUES.md` issue #0: process ran 5.5h (tick 1921), heartbeat froze,
**0.0s CPU consumed over a 20s sample** (thread blocked, not spinning), **no exception or
traceback logged**, and the **last stderr line was a `memory_tree ingest` from
`governor_dispatch`, then total silence**.

Traced the call chain:

- `core/loop/autonomous_loop.py:718` and `:1082` — `await self._get_governor().dispatch(...)`,
  called directly on the loop's own event-loop thread (also fire-and-forget via
  `asyncio.create_task(governor.dispatch(task))` at line 157). **Never wrapped in
  `asyncio.to_thread`**, unlike every other potentially-slow operation in this same file
  (screen capture, face detection, phone polling, git commits, weekly cycle, DB backup — all
  explicitly `to_thread`'d).
- `core/city/governor.py:2240-2243` — `dispatch()` calls
  `self._get_memory().store(event_type="governor_dispatch", ...)` **synchronously, inline**,
  on every single dispatch (i.e. on essentially every agent action VECTOR takes).
- `core/memory/episodic.py:751-763` — `EpisodicMemory.store()` then synchronously calls
  `get_shared_tree().ingest(...)` (`core/engine/memory_tree/tree_builder.py`).
- `tree_builder.py:262-269` — `ingest()` is **debounced** (save every 20 ingests or 15s,
  whichever first) but when the debounce condition trips, `_save()` runs **synchronously, on
  whatever thread called `ingest()`** — a full `json.dumps()` of the entire in-memory tree
  (currently **8.76 MB** live on this machine, growing) followed by `tmp.write_text(...)` and
  `os.replace(tmp, path)` (`tree_builder.py:471-474`), with **no timeout, no `to_thread`, no
  interruptibility**.

So: the one blocking-I/O class in the whole hot dispatch path that was never given the
`to_thread` treatment applied everywhere else in `autonomous_loop.py` is exactly the one whose
name appears as the last thing logged before the freeze. A stall in that single synchronous
`write_text`/`os.replace()` call (Windows Defender real-time scan intercepting the write,
transient disk/antivirus contention, any OS-level I/O hang that never raises) would freeze
the *entire* autonomous-loop event-loop thread indefinitely — zero CPU, no exception, no
traceback — which is precisely what was observed. It would also be intermittent by nature
(explaining why the process survived 1921 prior ticks fine), consistent with an
environment-triggered stall rather than a deterministic code bug.

The weekly (Monday-only) consolidation path has the same class of gap:
`ConsolidationBot.consolidate_old_episodes()` (awaited from the same reflect tick,
`autonomous_loop.py:1405-1417`) synchronously calls `EpisodicMemory.prune_old_episodes()`
(which can trigger a full `VACUUM` of the now **267 MB** `vector_memory.db`) and
`MemoryTree.prune_old_chunks()` → `flush()` → `_save()` — both fully synchronous, both
un-`to_thread`'d, both on the loop's single thread. Lower likelihood of being *this specific*
5.5h incident (weekly cadence doesn't obviously line up), but the same architectural gap.

**Recommended next step (from `KNOWN_ISSUES.md`'s own plan, reinforced by this finding):**
wrap `governor.dispatch()`'s memory writes (or at minimum `MemoryTree.ingest()`/`_save()`) in
`asyncio.to_thread`, and get a `faulthandler` thread dump on the next stall to confirm.

---

## RESOLVED — the MemoryTree "321 KB, untouched since Jul 28" discrepancy

**Saves are not silently failing.** The debounced save (every 20 ingests or 15s,
`tree_builder.py:262-269`) is working correctly. The 321 KB / Jul-28 file is
`~/.vector_ca/memory_tree/memory_tree.json` — the **pre-fix hardcoded legacy path**
(`_LEGACY_TREE_DIR`, `tree_builder.py:44`). The 2026-07-08/29 fix
(`_default_tree_dir()`, lines 47-77) relocated the live tree to
`configured_db_path().resolve().parent / "memory_tree"`; for this deployment
(`.env: VECTOR_DB_PATH=vector_memory.db`, a relative path, resolved against the repo root)
that is `<repo>/memory_tree/memory_tree.json`.

Verified directly on disk:

| File | Size | Last modified |
|---|---|---|
| `<repo>/memory_tree/memory_tree.json` (live) | 8.76 MB | **2026-08-05 22:14** (today, growing in lockstep with `vector_memory.db`'s own mtime) |
| `~/.vector_ca/memory_tree/memory_tree.json` (legacy) | 321 KB | 2026-07-28 17:42 (frozen) |

The one-time legacy→new migration (`_migrate_legacy_tree_if_needed`, lines 80-102) only fires
once, when the *new* path has no file yet — after that the legacy file is permanently
orphaned, never updated, never deleted, never marked deprecated. Anyone (including this
audit's brief) inspecting the historically-familiar `~/.vector_ca` path draws exactly the
wrong conclusion. This is a **LOW-severity hygiene gap** worth closing (delete or rename the
legacy file post-migration, or log a one-time loud warning pointing at the new location) so
it stops generating false "saves aren't happening" alarms.

Separately: growth is bounded but on a *slow* cadence — per-topic chunk cap
(`_max_chunks_per_topic=2000`) is enforced on every `ingest()`, and `prune_old_chunks(90d)` is
wired into the weekly (Monday) consolidation pass (`consolidation_bot.py:187-193`,
confirmed reachable from the reflect tick) — not unbounded, just growing over the intervening
week, which is expected/fine.

---

## MEDIUM

### 4. `core/memory/db_registry.py: get_district_db()` — latent SQLCipher landmine (not yet triggered)

Three registry entries — `"core.episodic"`, `"core.collections"`, `"core.causal_graph"`
(`db_registry.py:44-61`) — point `path_template` at `vector_memory.db`, the SQLCipher DB, but
`get_district_db()`'s factory (`line 175`) always opens with plain `sqlite3.connect()`.
Calling `get_district_db("core.episodic")` would hit the identical
`"file is not a database"` failure as finding #1.

Confirmed via repo-wide grep that `get_district_db()` is **never actually called anywhere in
production code today** — only defined and referenced in its own docstring example. This is a
landmine for a future developer following the module's own stated usage pattern, not an
active bug. Recommend either removing these three entries from the registry (they're already
served correctly by `episodic.get_db_connection()`) or teaching the factory to special-case
`path_template == "vector_memory.db"`.

### 5. Circuit-breaker buffer is a real, if deliberate, data-loss window

`episodic.py`'s `_memory_buffer` (`deque(maxlen=10000)`, lines 242-244) holds writes made
while the `episodic_memory` circuit breaker is OPEN. It is **in-memory only** — never
journaled to disk. This is explicitly a *bounded-memory* design tradeoff in the comments, but
it is also, un-stated, a *durability* tradeoff: an ungraceful kill (crash, forced restart,
power loss) while the breaker is open loses every buffered write (up to 10,000) permanently
and silently — nothing on disk records they ever happened. Not a bug (the fallback chain
design in this codebase explicitly favors availability), but flagging so it's a conscious,
documented choice rather than an accidental gap — the current comments justify the *bound*,
not the *loss*.

---

## Confirmed sound / no action needed

- `core/memory/episodic.py` core CRUD, FTS5 fallback-to-LIKE search, `prune_old_episodes()`
  Ebbinghaus eviction + chunked/rebuild-threshold FTS delete, `vacuum()`'s autocommit
  handling — all read cleanly and match their own documentation.
- `core/memory/db_utils.py` — `apply_pragmas()` correctly sets `busy_timeout=5000` +
  `journal_mode=WAL` (with a DELETE-mode fallback) on every connection it's called on; no
  connection in the audited scope opens without a `busy_timeout`, so cross-process contention
  fails fast (5s) rather than hanging forever. No cross-process locking is claimed anywhere
  beyond that — the `threading.Lock`/`RLock` instances in this codebase (`_write_lock`,
  `_SAVE_LOCK`, `_tree_lock`) are correctly understood by their own comments as process-local
  only (see `tree_builder.py:450-457`'s explicit note on this), not miscast as cross-process
  protection anywhere in the audited scope.
- `core/memory/decay.py`, `core/memory/tiering.py` — formulas and constants check out.
- `core/memory/router.py`, `core/memory/session_buffer.py` — both fail closed to episodic
  (the broadest-net store) on any classification/store failure; `session_buffer.py`'s
  no-op-without-session_id contract is enforced both at documented call sites and internally.
- `core/loop/loop_state.py` — heartbeat file write is correctly `os.replace`-atomic and
  best-effort (never breaks the loop on failure); `restore_agent_hp()`'s
  `(district, name)`-identity fallback (replacing broken UUID-only matching) is correct and
  well-reasoned.
- `core/memory/multi_db_manager.py` — local-first write ordering, LWW merge, and quarantine
  kill-switch all read correctly; `backup()`/`restore()` correctly open their own **separate**
  plain-sqlite connections against a caller-specified path (not the live singleton), which is
  the right call for a point-in-time dump, not a violation of the SQLCipher-singleton rule.

---

## Summary

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | CRITICAL | `shared_facts.py` opens SQLCipher DB with plain sqlite3; entire Gap-8 shared-fact store is a silent no-op in production (plus an independent `source=`/`source_agent=` TypeError, also swallowed) | CONFIRMED |
| 2 | HIGH | `policy.py`/`reasoning_memory.py`/`causal_graph.py` bypass `_write_lock`; lost-update race in RULE 7's online average + stale-cached-connection defect (same class as fixed KNOWN_ISSUES #21) | CONFIRMED (code-inspection level; live race not caught in the act) |
| 3 | HIGH | Synchronous, un-`to_thread`'d `MemoryTree._save()` on the autonomous loop's single event-loop thread, reached via every `governor.dispatch()` call — matches all recorded evidence for the 5.5h loop stall | SUSPECTED |
| — | — | MemoryTree "321 KB / stale since Jul 28" discrepancy | RESOLVED — wrong (legacy) path was being checked; live file is 8.76 MB, updated today, saves work correctly |
| 4 | MEDIUM | `db_registry.get_district_db()` would break on the 3 `vector_memory.db`-pointing entries if ever called | CONFIRMED defect, unreachable today (latent) |
| 5 | MEDIUM | Circuit-breaker write buffer is in-memory-only; up to 10,000 writes lost on ungraceful kill while breaker is open | CONFIRMED, deliberate tradeoff, durability implication not previously documented |
