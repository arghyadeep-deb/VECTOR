# Phase 0 Triage Summary — Absorbed Capability Reachability + Live Smoke

Per `plans/wire-absorbed-repos-autonomy.md` Phase 0. Evidence, not guesses —
every verdict below is backed by a real, captured run (see the per-repo
`.md` files in this directory).

## Reachability (Task 0.1)

**26/26 target modules import-resolve cleanly across all 7 repo groups.**
Zero `IMPORT_ERROR`. The absorbed code is not broken at the import level —
whatever issues exist are deeper (runtime/config/environment), not "this
module can't even load." Full table: `_reachability.md`.

## Live smoke verdicts (Task 0.2)

| Repo | Verdict | Why |
|---|---|---|
| **coding_assistant** | ✅ **LIVE** | Real grep over `core/city`, 21 genuine matches with correct file/line data. Works as-is. |
| **scraper** | ❌ **BROKEN** | Real bug, fully isolated. `vector_scraper.py:152` reads `resp.text` (always empty) instead of `resp.html_content` (has the real content). Network fetch genuinely succeeds (200, real bytes) — the public API just discards it. Affects `fetch()`/`quick_fetch()`/`fetch_to_markdown()` everywhere. **Needs a real code fix** before this capability can be scheduled autonomously — right now every call "succeeds" with empty output. |
| **research_engine** | ⚠️ **LIVE, but hollow** | The hypothesis→experiment→report pipeline genuinely runs end-to-end and writes a real markdown file to the Obsidian vault — orchestration plumbing works. But two real bugs degrade the *content*: (1) `EpisodicMemory.search()` doesn't exist (wrong method name) — memory-pattern context is silently always empty; (2) the sandbox experiment itself fails ("Insufficient data points (0)") after an Ollama 404 fallback — so the report's Results/Analysis sections are real markdown but scientifically empty. Wireable now, but scheduling it before fixing bug (2) just accumulates empty reports. |
| **investment** (Fincept) | 🟡 **NEEDS-CONFIG** (environmental, not code) | Hit a deterministic SQLCipher DB lock caused by a leftover test process from earlier in this session (PID 48532, `run_vector.py api`), confirmed still running. Not a defect in `FinAgentAgent`. **Owner action: close that process**, then re-run for a clean verdict on the actual analysis logic. |
| **trading** | 🟡 **NEEDS-CONFIG** (same cause as investment) | Identical deterministic DB lock, different class/module — confirms it's process-level, not a `trading_conductor_agent.py` bug. Same owner action needed. |
| **intelligence** | 🟡 **NEEDS-CONFIG** (one-line env fix) | `VectorIntelAgent`'s default port (8002) matches shadowbroker's own documented default exactly — not a code bug. The shadowbroker instance *currently running* on this machine just happens to be bound to port 8765 (leftover from an earlier, unrelated session). Fix: restart shadowbroker normally, or set `VECTORINTEL_HOST=http://127.0.0.1:8765`. Graceful degradation (empty lists, no crash) worked exactly as designed. |

## What this means for Phase 1+ workload

**1 real code fix required before autonomy:**
- `scraper` — fix `resp.text` → `resp.html_content` in `vector_scraper.py` (3 call sites). Small, scoped, do this before Task 2.x for scraper.

**1 real code fix recommended (not blocking, but wasteful if skipped):**
- `research_engine` — fix `EpisodicMemory.search()` → correct method name; investigate why the sandbox experiment always reports 0 data points. Otherwise the autonomous hand will run forever and produce empty reports.

**3 owner actions, zero code changes:**
- Close the leftover `run_vector.py api` process (PID 48532) so `investment`/`trading` can get a real verdict.
- Restart shadowbroker on its documented port (or repoint `VECTORINTEL_HOST`) so `intelligence` can get a real verdict.
- Re-run `python scripts/capability_smoke.py --live investment,trading,intelligence` after both, to confirm.

**1 architectural question for Phase 1's `HandRunner` design** (surfaced by the
investment/trading investigation, not yet answered): if SQLCipher's encrypted
DB genuinely cannot tolerate two VECTOR processes holding a connection at
once, the Hand Execution Engine cannot have each hand open its own
`EpisodicMemory()` — it needs to share the main loop's connection, or the DB
needs a busy-timeout/WAL fix. This should be designed into Task 1.1/1.2, not
discovered after Phase 1 is built.

**0 capabilities are definitively broken in a way that blocks Phase 1.**
`scraper`'s bug is real but small and scoped; everything else is either
already working (`coding_assistant`) or blocked by environment, not code.

## What Phase 0 did NOT cover

`research_district` (11 modules — `agent.py`, `deep_researcher.py`,
`web_scout.py`, etc.) was reachability-checked (11/11 resolve) but has no
live probe yet — the plan's Task 0.2 list didn't name a specific entrypoint
for it distinct from `research_engine`. Worth a follow-up live probe before
Task 2.x's "research" sub-list is finalized, since `web_scout`/`collector`
hands route through this district, not directly through `research_engine`.
