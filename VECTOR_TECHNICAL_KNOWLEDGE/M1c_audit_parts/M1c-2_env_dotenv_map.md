# M1c-2 — Environment / Dotenv Isolation Map

Read-only, static analysis only. No file was executed, imported, or run as part of this audit.

## Executive finding

**The dotenv-precedence mechanism that caused the M1b incident is REPO-WIDE in its trigger surface
(`import core` alone is enough to arm it), but the specific ANTI-PATTERN that turned it into a real
incident — a *conditional* `if "VECTOR_DB_PATH" not in os.environ` isolation guard placed after a
`core.*` import — is CONFIRMED ISOLATED to the one file already fixed
(`core/brain/goal_system.py`).** No other tracked `.py` file in the repository currently uses that
guarded pattern for `VECTOR_DB_PATH`. This is a directly-verified grep result (see §2), not an
inference.

A second, previously undocumented (by this audit) structural risk was found and is more subtle than
the path-guard issue: `VECTOR_DB_KEY` resolution is cached **process-wide, once, forever** (see §4).
This does not currently cause silent data leakage anywhere found, but it is a real fragility the
owner should know about before trusting "isolation" claims that span more than one DB-connection
lifecycle within a single process.

## 1. `load_dotenv` call sites (confirmed by reading exact source, not inferred)

| File | Trigger | Override | Confirmed how |
|---|---|---|---|
| `core/__init__.py:33-38` | Runs on **any** `import core` or `import core.<anything>` — i.e. virtually every module in the codebase, transitively | `_load_dotenv(path)` — **no `override=` kwarg**, so python-dotenv's documented default (`override=False`) applies. The file's own comment (line 32) states this explicitly and matches library behavior. | Direct read of the call, line 36 |
| `run_vector.py:26-27` | Explicit, top of the real entrypoint | `override=False` (explicit) | Direct read |
| Various `districts/investment/*`, `districts/intelligence/vector_social_sim/*`, `vectorcode/src/vector_cli/*` | Each subsystem's own CLI/entrypoint, not part of the `core.*` import chain `GoalSystem` uses | Mixed — most explicit `override=False`; `vector_cli/env_loader.py:175` uses `override=True` for the **user** env file specifically (by design, for CLI credential precedence) | Direct read, listed for completeness; none of these are on the path any `core.brain.goal_system` import traverses |

**Root cause of M1b, precisely:** `core/__init__.py`'s dotenv load is the *first* thing that runs
the instant any file does `from core.config import CONFIG` (as `goal_system.py` does at its own
line 11) — because that import requires importing the `core` package first. `override=False` means
dotenv will NOT clobber a var the *calling process* already set before this point, but it WILL set
any var **not yet present**, including `VECTOR_DB_PATH`, from `.env`. Confirmed `.env` (line 11)
contains `VECTOR_DB_PATH=vector_memory.db` — the real production path. So by the time any later code
in the *same file* reaches an `if "VECTOR_DB_PATH" not in os.environ:` guard, that condition is
already false — not because a test/caller "deliberately configured" it, but because `.env`'s own
default was silently injected moments earlier by an import the guard's author likely didn't realize
had already run.

## 2. `VECTOR_DB_PATH` reader / writer map

**Reader** (single source of truth, confirmed non-cached — re-evaluated fresh on every call):
- `core/memory/db_utils.py:12-29` `configured_db_path()` — `os.environ.get("VECTOR_DB_PATH")` read
  live at call time, falls back to `CONFIG["db_path"]` only if unset. No `functools.lru_cache` or
  similar; verified by reading the full function body.

**Writers** (exhaustive grep for `os.environ["VECTOR_DB_PATH"] =`, `.setdefault("VECTOR_DB_PATH"`,
and `"VECTOR_DB_PATH" not in os.environ` across all `*.py`):

| File:line | Unconditional or guarded | Sets before or after first `core.*` import in that file | Verdict |
|---|---|---|---|
| `core/brain/goal_system.py:444` (current, uncommitted fix) | **Unconditional** | AFTER (`core.config` imported at file top, line 11) — but this is safe because the *reader* (`configured_db_path()`) is called fresh, not cached, and the write happens before `GoalSystem()` is ever constructed in that block | SAFE (the file also now asserts `configured_db_path() == _tmp_db.name` before proceeding — verified present in current source) |
| `tests/test_e1_persistent_learning.py:48` | Unconditional | BEFORE any `core.*` import (env var set at very top of file) | SAFE — established correct pattern |
| `tests/test_r10_decision_provenance.py:41` | Unconditional | BEFORE | SAFE |
| `tests/test_r11_learning_integration.py:54` | Unconditional | BEFORE | SAFE |
| `tests/test_task89c_goal_progress.py:60` | Unconditional | BEFORE | SAFE |
| `tests/integration/test_spec09_research.py:39` | Unconditional | Inside a fixture/setup function, not file-top — not independently re-verified whether any `core.*` import already ran earlier in the same test module before this fixture executes | NOT FULLY VERIFIED — flagged, not confirmed unsafe |
| `tests/integration/test_phase_c2_semantic_recall.py:214` | Unconditional | Same caveat as above (inside a method) | NOT FULLY VERIFIED |
| `tests/integration/test_phase_a6_synthesis_briefing.py:71` | Unconditional | Same caveat (inside a classmethod, `setUpClass`-style) | NOT FULLY VERIFIED |
| `tests/test_predictive_analytics_run.py:53,62` | Unconditional (sets, then restores `original_path` after) | Inside a function; second line restores rather than isolates | NOT FULLY VERIFIED, different purpose (temporary swap, not a persistent isolation boundary) |
| `core/benchmark/isolation.py:64,109` | Unconditional (line 64 sets a chosen path, line 109 explicitly restores `self._original_db_path`) | This is a purpose-built isolation *context manager* class, not a bare self-test — by design it captures the prior value and restores it | Appears to be the correct, deliberate pattern; not a hazard of the M1b class |
| `scripts/capability_smoke.py:61` | Unconditional | Not verified relative to import order | NOT FULLY VERIFIED |

**Critical: zero files found using the dangerous `if "VECTOR_DB_PATH" not in os.environ:` /
`.setdefault("VECTOR_DB_PATH", ...)` GUARDED pattern**, except the one file that was already fixed
to remove it in the current (uncommitted) working tree. This was the exact mechanism of the M1b
incident. **No other file currently carries that specific defect for `VECTOR_DB_PATH`.**

The four files marked "NOT FULLY VERIFIED" above are not confirmed unsafe — they use the safe
*unconditional* write pattern, which this audit's own analysis of `configured_db_path()` (non-cached
reader) means is very likely fine regardless of exact position within the file, since the danger
mode specifically requires a *conditional* guard being defeated by a prior dotenv write, which none
of these use. They are flagged only because this audit did not trace each one's full call chain
line-by-line to be exhaustive; recommend a follow-up pass if the owner wants 100% certainty on these
four specifically.

## 3. Other isolation-relevant env vars

- `VECTOR_DB_KEY`: every writer found (`test_e1_persistent_learning.py`, `test_r10_...py`,
  `test_r11_learning_integration.py`, `test_task89c_...py`, and the current `goal_system.py` fix)
  uses `.setdefault(...)` or unconditional assignment, all placed immediately after their own
  `VECTOR_DB_PATH` override, all in files that set both before any `core.*` import (except
  `goal_system.py`, addressed in §4 below — its case is different because it also unconditionally
  overwrites, not `setdefault`s). No guarded/absence-based anti-pattern found for this var either.
- `VECTOR_MEMORY_TREE_PATH`: referenced in `core/memory/episodic.py`,
  `core/engine/memory_tree/tree_builder.py`, and one test
  (`tests/backend/test_memory_tree_performance.py`). Not exhaustively traced in this pass (out of
  the primary `VECTOR_DB_PATH`/`VECTOR_DB_KEY` scope of this audit) — flagged as a plausible sibling
  surface using a similar pattern, not confirmed either safe or unsafe.
- `VECTOR_MCP`: not found written anywhere in application code during this pass; appears to be a
  pure external/ambient toggle the owner sets themselves, not something the app's own dotenv/import
  chain populates. Confirmed unset in the current session (Phase 0 of the parent orchestrator's
  earlier verification).
- `VECTOR_TEST_DATA_DIR` (`tests/conftest.py:26`): a `setdefault`, but for a *directory* used by
  tests generally, not a persistent-state DB path — different risk class, not investigated further.

## 4. `VECTOR_DB_KEY` process-wide caching — a distinct, real structural risk (new finding)

`core/memory/episodic.py`'s `_get_db_key()` (lines 93-133) resolves the encryption key ONCE per
process and caches it in a module-level global (`_DB_KEY`), returning the cached value on every
subsequent call **without re-reading `os.environ["VECTOR_DB_KEY"]`**. This is structurally different
from `configured_db_path()` (§2), which re-reads fresh every call.

**Consequence:** within a single Python process, only the *first* DB-connection-opening event's
`VECTOR_DB_KEY` value takes effect. If any code path opens a DB connection before a later
test/self-test's own key override runs, that later override is silently ineffective for the KEY
(though the PATH override still correctly redirects which *file* gets opened, since path resolution
is independent and non-cached). The codebase's own comment at `episodic.py:362-373` shows the
developers were already aware of a related failure mode and mitigated it: `close_db_connection()`
clears `_DB_KEY` together with `_db_connection` in the same lock, specifically to prevent "a test
that monkeypatches VECTOR_DB_KEY for isolation, closes the connection at teardown, and lets
monkeypatch restore the real env var" from then opening the *real* production DB with the *test's*
stale key (which would fail loudly with an HMAC/key-mismatch error — a safe failure mode, not silent
corruption).

**Bounded risk assessment (not exhaustively proven, reasoned from the code read):**
- Every file in this repo that relies on this isolation pattern is documented (in its own header
  comment, confirmed present in each of the 4-5 files listed in §2) as **"must be run standalone,
  never mixed into a combined pytest session with other files that import core.memory.episodic
  first."** As long as that documented constraint is honored, each such file gets a genuinely fresh
  process and this caching risk never manifests.
- The realistic failure mode if that constraint were VIOLATED (two such "standalone-only" files run
  in the same pytest process) is most likely a loud `HMAC check failed` / key-mismatch exception —
  not a silent write to the real DB — because the second file's *path* override still correctly
  redirects to its own distinct temp file, and a mismatched key against THAT file's SQLCipher header
  fails safely, UNLESS that file is brand new/empty, in which case a fresh file adopts whatever key
  first touches it, and the test proceeds with an unexpected-but-still-isolated key — cosmetically
  wrong, not a production-data hazard.
- No path was found by this audit where this caching mechanism could cause a WRITE to the REAL
  production DB file (`vector_memory.db`) as a *result* of the caching itself — the caching risk is
  about which key is used against an already-correctly-isolated path, not about which path is used.
  This is a materially different (lower-severity) risk class than the M1b/R11 incidents, which were
  about the PATH itself resolving to the real file.

## Open questions (handed to the parent/owner, not resolved here)

1. Should the 4 "NOT FULLY VERIFIED" files in §2 get an explicit line-by-line trace to reach full
   certainty, or is the non-cached-reader argument sufficient?
2. Should `_get_db_key()`'s single-process caching be hardened (e.g., a dedicated
   `reset_db_key_cache()` isolation helper, or documenting the "standalone-only" constraint more
   prominently/enforcing it via a pytest collection-time check) given it's a real, if
   lower-severity, fragility?
3. `VECTOR_MEMORY_TREE_PATH` was not traced with the same rigor as `VECTOR_DB_PATH` — worth a
   follow-up pass if the owner wants full parity of confidence across both stores.
