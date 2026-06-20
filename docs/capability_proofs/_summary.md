# Phase 0 + 0.5 Triage Summary — Absorbed Capability Reachability + Live Smoke

Per `plans/wire-absorbed-repos-autonomy.md` Phases 0 and 0.5. Evidence, not
guesses — every verdict below is backed by a real, captured run (see the
per-repo `.md` files in this directory). This supersedes the original Phase
0-only summary: Phase 0.5 fixed the two real bugs Phase 0 found, and added
DB-isolation to the live-smoke harness itself, which then revealed two more
real (but separately-scoped) bugs that the DB contention had been masking.

## Reachability (Task 0.1)

**26/26 target modules import-resolve cleanly across all 7 repo groups.**
Zero `IMPORT_ERROR`. Full table: `_reachability.md`.

## Final live smoke verdicts (after Phase 0.5)

| Repo | Verdict | Status |
|---|---|---|
| **coding_assistant** | ✅ **LIVE** | Works as-is. No change needed. |
| **scraper** | ✅ **LIVE** (fixed) | Was BROKEN (`resp.text` always empty). Fixed → `resp.html_content`. Real fetch now returns real content (`content_len: 543` for example.com). Regression test passes. |
| **research_engine** | ✅ **LIVE** (fixed) | Was hollow (0 data points). Fixed `EpisodicMemory.search()`→`.recall()` and the sandbox's `logger.info()`→`print()` bug (sandbox's restricted builtins never define `logger`; `_extract_stats()` only reads stdout). Report now has real computed statistics (t=0.314, p=0.766, r=-0.430). Regression test passes. |
| **investment** (Fincept) | ✅ **LIVE** (test isolation fixed) | Phase 0's DB-contention finding is fully resolved by Task 0.5c's temp-DB isolation — proven with the original conflicting process (PID 48532) still running, zero process killing needed. **New finding surfaced**: the underlying LLM call fails ("no current event loop in thread") and degrades to a fallback response — real bug, but separately scoped, flagged for Phase 2 (see `investment.md`). |
| **trading** | 🟡 **BROKEN** (different bug than Phase 0 found) | DB-contention finding resolved by Task 0.5c (same as investment). **New finding**: missing `langgraph-checkpoint-sqlite` dependency (fixed — installed, added to `requirements.txt`), then a deeper `WinError 3: empty path` bug inside the absorbed `VectorTradingGraph` itself (config dict is correctly populated; directories exist; root cause is inside the absorbed library, not yet found). Needs its own fix sub-task — flagged for Phase 2 (see `trading.md`). |
| **intelligence** | 🟡 **NEEDS-CONFIG** (unchanged — one-line env fix, not code) | `vectorintel_agent.py`'s default port (8002) matches shadowbroker's own documented default exactly. The shadowbroker instance currently running on this machine is bound to 8765 (leftover from an unrelated earlier session) — not something Task 0.5 touched or could fix from code. |

## What Phase 0.5 actually fixed (code, with regression tests)

1. **`scraper`** — `core/scraper/vector_scraper.py`, all 3 `ScrapeResult` sites: `resp.text` → `resp.html_content`. Test: `tests/integration/test_capability_live.py::test_scraper_fetch_returns_real_content`.
2. **`research_engine`** — `auto_research_agent.py`: `EpisodicMemory.search()` → `.recall()`; sandbox template's `logger.info("STAT:...")` → `print(...)`. Also rewired `ExperimentDesigner`'s default model from the upstream project's unmodified `llama3.2` (never installed) to `CONFIG["models"]["reasoning"]` (`vector-reasoning`, actually installed). Test: `tests/integration/test_capability_live.py::test_research_engine_full_cycle_produces_real_statistics`.
3. **Test isolation (Task 0.5c)** — `scripts/capability_smoke.py --live` now points `VECTOR_DB_PATH` at a fresh temp file before any VECTOR module imports, via the existing `configured_db_path()` override seam in `core/memory/db_utils.py`. Confirmed working with the original conflicting process still alive. Test: `tests/test_capability_smoke.py` (4 tests).
4. **Trading dependency gap** — installed `langgraph-checkpoint-sqlite==2.0.4`, pinned in `requirements.txt` (downgraded `aiosqlite` 0.22.1→0.20.0; confirmed nothing else depends on a specific `aiosqlite` version).

## What's left — 3 items, all scoped for Phase 2, none blocking Phase 1

- **`investment`**: LLM call inside `investor_analysis` fails with an asyncio
  event-loop error in worker threads, degrades to a fallback placeholder
  response instead of real analysis. Needs the same kind of fix
  `agent_base.py::_ensure_legacy_event_loop()` already does for the main
  thread, applied to whatever executor/thread `VectorProviderModel._sync_call`
  runs in.
- **`trading`**: `WinError 3` empty-path bug inside the absorbed
  `VectorTradingGraph` — root cause not yet found, needs tracing inside
  `core/trading/graph/trading_graph.py`.
- **`intelligence`**: one-line owner action (restart shadowbroker on 8002,
  or set `VECTORINTEL_HOST=http://127.0.0.1:8765`) — not code.

**0 capabilities block Phase 1.** The DB-contention architectural question
Phase 0 raised is resolved for *testing* (Task 0.5c); the *production*
answer is now recorded in Phase 1's architecture decision (in-process
singleton connection, hardened by Task 1.0) rather than left open.

## What Phase 0/0.5 did NOT cover

`research_district` (11 modules) was reachability-checked (11/11 resolve)
but has no live probe yet distinct from `research_engine` — worth a
follow-up before Phase 2's "research" sub-list is finalized.
