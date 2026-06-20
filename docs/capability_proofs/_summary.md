# Capability Triage Summary — FINAL (2026-06-21)

Per `plans/wire-absorbed-repos-autonomy.md`. Evidence, not guesses — every
verdict below is backed by a real, captured run (see the per-repo `.md`
files in this directory). This supersedes all prior summaries — every
absorbed capability Phase 0 set out to verify is now LIVE.

## Reachability (Task 0.1)

**26/26 target modules import-resolve cleanly across all 7 repo groups.**
Zero `IMPORT_ERROR`. Full table: `_reachability.md`.

## Final live smoke verdicts — ALL SIX LIVE

| Repo | Verdict | Status |
|---|---|---|
| **coding_assistant** | ✅ **LIVE** | Works as-is. No change needed. |
| **scraper** | ✅ **LIVE** (fixed) | Was BROKEN (`resp.text` always empty). Fixed → `resp.html_content`. Real fetch returns real content. Full integration path (`web_scout` → `vector_scraper`) also live-proven. |
| **research_engine** | ✅ **LIVE** (fixed) | Was hollow (0 data points). Fixed `EpisodicMemory.search()`→`.recall()` and sandbox `logger.info()`→`print()`. Report has real computed statistics. Provenance leak scrubbed (Task 2.0 — 9 files, not the estimated 4). |
| **investment** (Fincept) | ✅ **LIVE** (fixed 2026-06-21) | Was masked-degraded (asyncio event-loop crash in `VectorProviderModel._sync_call`, worker threads never got an event loop on Python 3.10+). Fixed with the same `_ensure_legacy_event_loop()` pattern already established in `agent_base.py`. Live-verified: real multi-section LLM-generated AAPL investment report (Buffett persona), ending in "BUY (Strong Conviction)". |
| **trading** | ✅ **LIVE** (fixed 2026-06-21) | The original `[WinError 3]` never reproduced this session — full tracebacks revealed two different real bugs the prior swallowed-exception message had hidden: (1) `CONFIG["trading"]["llm_provider"]` hardcoded to `"openai"` despite Ollama models being configured (RULE 11 violation) — fixed to default `"ollama"`; (2) `core/trading/graph/setup.py` missing two imports (`create_msg_delete`, `create_trader`) — added. Live-verified: full 11-node multi-agent pipeline (4 analysts → debate → trader → risk → portfolio manager) ran end-to-end via local Ollama, real decision returned (`Overweight`). |
| **intelligence** | ✅ **LIVE** (fixed 2026-06-21) | Was NEEDS-CONFIG (port mismatch, not code). Fixed: `VECTORINTEL_HOST=http://127.0.0.1:8765` in `.env` (matching the already-running shadowbroker instance). Live-verified: real aircraft-tracking data (callsigns, GPS trails, emissions). Decided standalone-service (not a hand) — health-poll loop deferred, owner to confirm. |

## What got fixed overall (code, all with regression tests)

1. **`scraper`** — `core/scraper/vector_scraper.py`: `resp.text` → `resp.html_content` (3 sites).
2. **`research_engine`** — `.search()` → `.recall()`; sandbox `logger.info` → `print`; LLM model default fixed to an actually-installed model; 9-file User-Agent provenance scrub (Task 2.0).
3. **Test isolation (Task 0.5c)** — `scripts/capability_smoke.py --live` uses an isolated temp DB; also now calls `load_dotenv()` to match real `run_vector.py` behavior.
4. **`investment`** — `VectorProviderModel._ensure_legacy_event_loop()` added, mirroring the existing house pattern.
5. **`trading`** — `core/config.py` LLM provider default fixed to Ollama; `core/trading/graph/setup.py` missing imports added; `langgraph-checkpoint-sqlite` dependency installed and pinned.
6. **`intelligence`** — port mismatch resolved via `.env`.

## Phase 1/5/2/3 status (as of 2026-06-21)

- **Phase 1 (Hand Execution Engine)**: ✅ all 6 tasks (1.0–1.6) done. The 9 Hands and ~12 pre-existing cron jobs are no longer dead — real `AsyncIOScheduler`, verified live (20 real scheduled jobs with correct `next_run_time`).
- **Phase 5.1/5.2 (autonomy proof)**: ✅ done. Real `kind="hand_run"` episodic row, real HP delta, real policy update — scheduler-triggered, not test-triggered.
- **Phase 3 (harden)**: ✅ all 3 tasks done (RED gating, `on_demand` flag, crash isolation + pushover alerts on high-signal results).
- **Phase 2 (per-capability routing)**: research/investment/content routes added to `governor.py` (`osint_collect`, `content_generate` were missing); scraper integration live-proven. `content` hand has correct routing + RED gating but no live generation proof yet (deliberately not attempted unattended — risk of an actual generation/publish side effect without supervision).
- **Phase 5.3 (every capability has a LIVE verdict)**: ✅ **all 6 do**, as of this update.
- **Phase 5.4 (24-48h soak)**: deliberately deferred — owner's explicit call, to run after all phases are fixed.
- **Phase 4 (dead-code classification)**: still gated — not attempted; the plan's hard gate requires this only after Phase 5 is fully green, and the soak (5.4) hasn't run yet.

## Owner-review items (decisions made solo while owner was asleep, flagged for confirmation)

1. **Ollama model-warmth**: `researcher`/`predictor` hands moved off-peak (03:00). `vector-reasoning.modelfile`'s `num_ctx`, and `OLLAMA_MAX_LOADED_MODELS=1→2`, deliberately NOT changed (real Council-quality / system-config tradeoffs) — deferred to post-soak.
2. **`intelligence`**: decided standalone-service framing over mapping 34 task types to a hand. Health-poll loop not built.
3. **`content`**: routing wired, but no live generation attempted (RED/publish-adjacent, didn't want to risk an unsupervised side effect).
