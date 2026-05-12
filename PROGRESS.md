# VECTOR — Build Progress Tracker

**Owner:** Arghyadeep Deb | KIIT CSE 2023-27  
**Hardware:** Legion Pro 5 | RTX 5070 Ti 12GB | 32GB RAM  
**Repo:** https://github.com/arghyadeep-deb/VECTOR  
**Last updated:** 2026-05-12

---

## Overall Status

| Phase | Description | Status | Gate |
|-------|-------------|--------|------|
| T1 | Foundation — config, memory, API server | ✅ DONE | ✅ PASS |
| T2 | Intelligence Stack — loop, goals, decisions | ✅ DONE | ✅ PASS |
| T3 | Voice Pipeline — STT, TTS, wake word | ✅ DONE | ✅ PASS (pyttsx3 fallback) |
| T4 | Sensing & Control — camera, ADB, screen | ✅ DONE | ✅ PASS (face_recognition optional) |
| T5 | Phase 1 Districts — coding, calendar, security | ✅ DONE | ✅ PASS |
| T6 | Memory + Research + Cloud | ✅ DONE | ⚠️ Code complete — deploy pending |
| T7 | Final Integration | ✅ DONE | ⚠️ Integration testing pending |
| P2 | Phase 2 — Reflection, Health, Finance, Projects | ✅ DONE | ✅ 47/47 tests |
| P3 | Phase 3 — Modular API, Intelligence Stack Fixes | ✅ DONE | ✅ 19 routes, full stack wired |
| GH | GitHub Repos Integration — all repos wired/deleted | ✅ DONE | ✅ 154/154 tests |
| UI | Native UI — terminal TUI + browser dashboard + MCP server | ✅ DONE | ✅ 154/154 tests |
| BG | Background TaskQueue — parallel execution, /bg /tasks /cancel, web panel | ✅ DONE | ✅ singleton wired |
| UP | District Upgrades — ResearchHub×14 APIs, StockAnalyst CoinGecko, CodeReviewer severity+AgentShield, HermesAdapter cron+skills, ComfyUI adapter | ✅ DONE | ✅ |

---

## T1 — Day 1: Foundation ✅ COMPLETE

| Module | File | Smoke Test |
|--------|------|------------|
| Config | `core/config.py` | ✅ Pydantic BaseSettings validated |
| Episodic Memory | `core/memory/episodic.py` | ✅ FTS5 + 6 tables |
| FastAPI Server | `core/main.py` | ✅ 6 routes |
| Agent Base | `core/city/agent_base.py` | ✅ HP + ghost memory |
| Permission Gateway | `core/loop/permission_gateway.py` | ✅ GREEN/YELLOW/RED |
| Multi-DB Manager | `core/memory/multi_db_manager.py` | ⚠️ stub |
| run_vector.py | `run_vector.py` | ⚠️ stub |

**Day 1 Gate:** `python run_vector.py` → JSON response + SQLite row ✅

---

## T2 — Day 2: Intelligence Stack ✅ COMPLETE

| Module | File | Key Capability |
|--------|------|----------------|
| Context Engine | `core/loop/context_engine.py` | RULE 1 — session_hydration_prompt() |
| Goal System | `core/brain/goal_system.py` | RULE 6 — 3-horizon management, 7 goals |
| Decision Engine | `core/loop/decision_engine.py` | 5-factor scoring (30/25/20/15/10) |
| Policy Memory | `core/memory/policy.py` | RULE 7 — get_score() + update_from_outcome() |
| Reasoning Memory | `core/memory/reasoning_memory.py` | RULE 8 — chains → training data |
| Agent Registry | `core/city/agent_registry.py` | RULE 9 — Darwinism + ghost memory |
| Governor | `core/city/governor.py` | Task routing + HP wiring |
| Autonomous Loop | `core/loop/autonomous_loop.py` | RULE 2 — never stops, 7 coroutines |

**Day 2 Gate:** debug mode → 4 candidates + scores + policy table rows ✅

---

## T3 — Day 3: Voice Pipeline ✅ COMPLETE

| Module | File | Status |
|--------|------|--------|
| STT | `core/voice/stt.py` | ✅ Whisper local (RULE 5 — audio never leaves device) |
| TTS | `core/voice/tts.py` | ✅ Kokoro primary → pyttsx3 fallback |
| Wake Word | `core/voice/wake_word.py` | ✅ openwakeword (hey_jarvis placeholder; Hey VECTOR needs training) |
| Language Detector | `core/voice/language_detector.py` | ✅ langdetect EN/HI/BN/AS/JA |
| Ambient Listener | `core/voice/ambient_listener.py` | ✅ Orchestrates full pipeline |

**Day 3 Gate:** "Hey VECTOR" → WAKE → TRANSCRIBE → THINK → SPEAK ✅ (pyttsx3 TTS; Kokoro model ~300MB pending download)

---

## T4 — Day 4: Sensing & Control ✅ COMPLETE

| Module | File | Status |
|--------|------|--------|
| Camera / Face ID | `core/sensing/camera.py` | ✅ face_recognition graceful degradation |
| Screen Capture | `core/sensing/screen_observer.py` | ✅ mss live; pytesseract optional |
| Health Monitor | `core/sensing/health_monitor.py` | ✅ psutil + EAR fatigue scoring |
| Sound Classifier | `core/sensing/sound_classifier.py` | ✅ RMS+ZCR heuristic |
| PC Control | `core/control/pc_controller.py` | ✅ pyautogui + mss screenshots |
| Phone Control | `core/control/phone_controller.py` | ✅ ADB bridge; graceful if disconnected |
| Malware Detector | `core/control/security/malware_detector.py` | ✅ 3-layer: VT + MIME + LightGBM |
| Threat Detector | `core/control/security/threat_detector.py` | ✅ |
| Node Router | `core/control/security/node_router.py` | ✅ |

**Day 4 Gate:** Face ID + cursor control + ADB screenshot ✅ (face_recognition optional; cursor/ADB ready)

---

## T5 — Day 5: Phase 1 Districts ✅ COMPLETE

| District | Agents | Status |
|----------|--------|--------|
| `coding/` | GitBot, CodeReviewer, ArchitectBot | ✅ YELLOW/RED gateway wired; AST analysis |
| `time_calendar/` | KIITScraper, DeadlineManager, TimeBlocker | ✅ Playwright scraper |
| `security/` | ThreatScout, NodeGuard | ✅ process + startup + 166 connections |
| `communications/` | Hermes adapter | ⚠️ Stub — RULE 10: use Hermes, do not rebuild |

**Day 5 Gate:** KIIT schedule + auto-commit ✅ (Gmail pending T6)

---

## T6 — Day 6: Memory + Research + Cloud ✅ COMPLETE (deploy pending)

| Module | Status |
|--------|--------|
| `agents/districts/memory_curator/consolidation_bot.py` | ✅ LightRAG consolidation |
| `agents/districts/memory_curator/pattern_finder.py` | ✅ cross-domain pattern detection |
| `agents/districts/research/web_scout.py` | ✅ DuckDuckGo + httpx |
| `agents/districts/research/paper_reader.py` | ✅ ArXiv + PDF extraction |
| `agents/districts/research/news_aggregator.py` | ✅ RSS feeds |
| `agents/districts/research/reddit_miner.py` | ✅ PRAW subreddit mining |
| `core/memory/obsidian_sync.py` | ✅ LightRAG vault bridge, watchdog, ingest |
| `cloud/brain_server/main.py` | ✅ FastAPI — /status → 200 (verified) |
| `cloud/agent_workers/workers.py` + `scheduler.py` | ✅ APScheduler 5 jobs |
| `cloud/comms_service/service.py` | ✅ Hermes bridge (RULE 10) |
| `api/src/` | ✅ Cloudflare Worker — Bearer auth + KV rate limiter |
| `dashboard/src/app/` | ✅ 7 Next.js pages |

**Deploy commands (pending):**
```bash
cd cloud/brain_server && fly launch
cd api && wrangler deploy
cd dashboard && vercel --prod
```

**Day 6 Gate:** fly.dev/status 200 ⚠️ Code complete — `fly launch` not yet run

---

## T7 — Day 7: Final Integration ✅ COMPLETE

| Module | Status |
|--------|--------|
| `core/memory/obsidian_sync.py` | ✅ LightRAG + watchdog + ingest_existing |
| `agents/districts/governance/llm_council.py` | ✅ 3-stage (collect→rank→synthesize), HP gate ≥700, max 10/week |
| `phone_node/ambient_server.py` | ✅ Pure stdlib HTTP server, battery + heartbeat |
| `phone_node/adb_bridge.py` | ✅ Legion↔phone bridge, graceful if disconnected |
| `phone_node/setup.sh` | ✅ Termux bootstrap |
| `core/loop/autonomous_loop.py` | ✅ phone_loop + /heartbeat to brain server |

**Day 7 Gate:** all 4 end-to-end scenarios ⚠️ Integration testing pending (phone node: old phone not available)

---

| Phase 2 — Districts: Reflection, Health, Finance, Projects ✅ COMPLETE

### P2.1 — Reflection District ✅
| Agent | Schedule | Key Behavior |
|-------|----------|--------------|
| `daily_reviewer.py` | 2:00 AM daily | vector-chairman analysis → POLICY_UPDATES → semantic_memory → Obsidian Reflections/ |
| `journal_writer.py` | 22:30 daily, Sunday 23:00 weekly | First-person narrative journal → Journals/ + Reviews/ |
| `growth_analyst.py` | Sunday 2:30 AM | 21-day growth score trend, velocity, bottlenecks → Reflections/ |

### P2.2 — Health District ✅
| Agent | Schedule | Key Behavior |
|-------|----------|--------------|
| `sleep_tracker.py` | 8:00 AM daily | Infers sleep from ≥4h activity gaps; quality labels; chronic under-sleep penalty |
| `fatigue_monitor.py` | Every 5 min | EAR from ContextEngine world state + 90-min session threshold alerts |
| `exercise_logger.py` | Sunday 9:00 AM + `log_session()` | Sedentary alert after 2+ inactive days; weekly report → Health/ |

### P2.3 — Finance District ✅
| Agent | Schedule | Key Behavior |
|-------|----------|--------------|
| `upi_parser.py` | Event-driven | Regex SMS parser, 8 categories (food/transport/education/utilities/shopping/health/entertainment/other) |
| `expense_tracker.py` | 1st of month 9:00 | Aggregates UPI → monthly breakdown → Finance/ |
| `budget_analyst.py` | 1st of month 9:30 | Over-budget detection vs configurable targets + LLM recommendations |
| `tax_calendar.py` | Daily 9:00 + April 1 | Indian FY deadlines (ITR, advance tax, etc.) — T-7/T-1/T-0 alerts |

### P2.4 — Projects District ✅
| Agent | Schedule | Key Behavior |
|-------|----------|--------------|
| `project_planner.py` | Event-driven | vector-reasoning milestone plan → semantic_memory + Obsidian Projects/ |
| `deadline_watcher.py` | 9:00 + 18:00 daily | T-7/3/1/0 alerts with per-day deduplication guard |
| `progress_tracker.py` | Sunday 10:00 | Git commits + manual updates → weekly progress report |
| `doc_writer.py` | Event-driven | 5 doc types: readme / architecture / api / retrospective / onboarding |

**Tests:** 47/47 passing (`tests/test_phase2_districts.py`)

---

## Phase 3 — Modular API + Intelligence Stack Fixes ✅ COMPLETE

| Module | File | Status |
|--------|------|--------|
| API App Factory | `core/api/app.py` | ✅ `create_app()` wires all routers, middleware, CORS, startup/shutdown |
| Schemas | `core/api/schemas.py` | ✅ All Pydantic request/response models |
| Dependencies | `core/api/dependencies.py` | ✅ DI for all core components (8 FastAPI Depends functions) |
| Auth | `core/api/auth.py` | ✅ HTTPBearer API key verification via security dependency |
| Middleware | `core/api/middleware.py` | ✅ Auth, logging, timing, error-handling middleware |
| CRUD | `core/api/crud.py` | ✅ 12 CRUD functions for memory, agents, goals, policies |
| Commands Router | `core/api/routers/commands.py` | ✅ Full intelligence stack: context → goals → decision → gateway → policy |
| Council Router | `core/api/routers/council.py` | ✅ 3-stage deliberation with throttling, confidence scoring |
| Agents Router | `core/api/routers/agents.py` | ✅ /agents and /agent/award |
| Status Router | `core/api/routers/status.py` | ✅ Dynamic Ollama model checking + /health |
| Voice Router | `core/api/routers/voice.py` | ✅ /voice with soundfile parsing |
| Memory Router | `core/api/routers/memory.py` | ✅ /memory endpoints (recent, type-filtered, training-data, goals, council/history, security/recent) |
| Deprecate main.py | `core/main.py` | ✅ Redirects to `create_app()` with deprecation warning |
| Permission Gateway | `core/loop/permission_gateway.py` | ✅ `_execute_action()` now handles 14 action types |
| Decision Engine | `core/loop/decision_engine.py` | ✅ Complete reasoning chain (6 steps) + situation dict in `Decision` dataclass |
| Autonomous Loop | `core/loop/autonomous_loop.py` | ✅ `_act_on()` now stores reasoning chain in episodic memory |
| Multi-DB Manager | `core/memory/multi_db_manager.py` | ✅ Full 4-DB sync: write_local/write_cloud/write_all/sync_all/health_check/get_stats |

**Phase 3 Gate:** All modules import successfully — `create_app()` produces app with 19 routes ✅

---

## Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/test_agent_base.py` | — | ✅ |
| `tests/test_decision_engine.py` | — | ✅ |
| `tests/test_episodic.py` | — | ✅ |
| `tests/test_governor.py` | — | ✅ |
| `tests/test_llm_council.py` | 16 | ✅ |
| `tests/test_memory_curator.py` | — | ✅ |
| `tests/test_obsidian_sync.py` | — | ✅ |
| `tests/test_permission_gateway.py` | — | ✅ |
| `tests/test_point_system.py` | — | ✅ |
| `tests/test_research_district.py` | — | ✅ |
| `tests/test_phase2_districts.py` | 47 | ✅ |

---

## Infrastructure ✅ COMPLETE

| Item | Status |
|------|--------|
| `.claude/settings.json` | ✅ PreToolUse security hooks |
| `modelfiles/` (7) | ✅ vector-ambient/focus/coder/multilingual/reasoning/deep/chairman |
| `.github/workflows/ci.yml` | ✅ Python 3.11, pytest |
| `.github/workflows/lint.yml` | ✅ ruff on core/ and agents/ |
| `core/config.py` | ✅ Pydantic BaseSettings, obsidian write folders updated |

---

## Models Routing

| Model | Base | Used For |
|-------|------|----------|
| vector-ambient | gemma4:e2b | Ambient classification, phone node |
| vector-focus | gemma4:e4b | Real-time conversation, main loop |
| vector-multilingual | qwen3:14b | Hindi/Bengali/Assamese/Japanese/English |
| vector-coder | qwen3:14b | Code generation (2 modes) |
| vector-reasoning | qwen3:14b | Step-by-step analysis, council member |
| vector-deep | gemma4:26b | Overnight analysis, 65K context |
| vector-chairman | gemma4:31b | Council chairman, daily reflection |

**Rebuild all:**
```bash
ollama create vector-ambient -f modelfiles/vector-ambient.modelfile && \
ollama create vector-focus -f modelfiles/vector-focus.modelfile && \
ollama create vector-coder -f modelfiles/vector-coder.modelfile && \
ollama create vector-multilingual -f modelfiles/vector-multilingual.modelfile && \
ollama create vector-reasoning -f modelfiles/vector-reasoning.modelfile && \
ollama create vector-deep -f modelfiles/vector-deep.modelfile && \
ollama create vector-chairman -f modelfiles/vector-chairman.modelfile
```

---

## GitHub Repos Integrated ✅ COMPLETE

| Repo | Integration | Status |
|------|------------|--------|
| `NousResearch/hermes-agent` | RULE 10 — used directly, not rebuilt | ✅ |
| `lyogavin/airllm` | 70B inference on RTX 5070 Ti via `AirLLM` | ✅ wired in models config |
| `kyegomez/OpenMythos` | Custom LLM training pipeline (Month 2) | ✅ referenced in roadmap |
| `PrefectHQ/fastmcp` | `core/mcp_server.py` — 14 tools + 1 resource exposed to Claude Code | ✅ |
| `jackwener/OpenCLI` | `agents/districts/research/opencli_adapter.py` — npm wrapper + native fallbacks | ✅ |
| `mem0ai/mem0` (self-hosted) | District 7, `from mem0 import Memory` — never MemoryClient | ✅ |
| `HumanLayer` | Approval layer for YELLOW/RED gateway actions | ✅ wired |
| Reference repos (AI-Trader, etc.) | Deleted — no implementation dependency | ✅ deleted |

---

## Native UI ✅ COMPLETE

| Interface | File | Launch |
|-----------|------|--------|
| Terminal TUI (Rich) | `core/ui/chat.py` | `python -m core.ui.chat` |
| Browser Dashboard | `core/ui/web_ui.py` | `http://127.0.0.1:8000/ui` (zero npm) |
| MCP Server | `core/mcp_server.py` | auto via `.mcp.json` |

**Terminal features:** banner + status line, /help /status /goals /search /note /districts /council /karpathy, rolling 10-exchange history, episodic memory on every turn (RULE 8)  
**Browser features:** Chat, Research (HN/GitHub/DEV.to/ArXiv), Goals, Memory recall, Districts grid, Karpathy, Agents HP — all DOM-safe (no innerHTML with user data), polls /status every 30s  
**MCP tools (14):** recall_memory, store_memory, get_world_state, get_goals, search_web, mine_reddit, read_paper, convene_council, review_code, git_status, karpathy_session, karpathy_streak, write_note, search_vault

---

## Native Research Hub ✅ COMPLETE

`agents/districts/research/research_hub.py` — zero npm, 100% Python:

| Source | Method | API |
|--------|--------|-----|
| DuckDuckGo | `search_web()` | JSON instant answers + HTML fallback |
| HackerNews | `get_hn_top()`, `get_hn_ask()` | Firebase JSON API |
| GitHub | `get_github_trending()` | GitHub Search REST API |
| DEV.to | `get_devto_posts()` | DEV.to public REST |
| ArXiv | `search_arxiv()` | ArXiv XML Atom feed |
| ProductHunt | `get_producthunt_top()` | PH GraphQL public |
| YouTube | `search_youtube()` | yt-dlp ytsearch |
| CoinGecko | `get_crypto_prices()` | Crypto prices + 24h change — no auth |
| Econdb | `get_macro_indicator()` | Macroeconomic series (GDP/CPI/unemployment) — no auth |
| Crossref | `search_papers()` | Academic papers by DOI/title — no auth |
| OpenAQ | `get_air_quality()` | PM2.5/PM10 by city — no auth |
| Yahoo Finance | `get_stock_quote()` | NSE/BSE prices — no auth |
| Tech feed | `get_tech_news()` | HN + DEV.to merged stream |

`daily_digest()` runs all sources in parallel, stores summary in episodic memory.
Full catalog: `docs/public_apis.md`

---

## Pending Actions

| Item | Command | Priority |
|------|---------|----------|
| Deploy brain server | `cd cloud/brain_server && fly launch` | HIGH |
| Deploy Cloudflare Worker | `cd api && wrangler deploy` | HIGH |
| Deploy dashboard | `cd dashboard && vercel --prod` | MEDIUM |
| Pull vector-deep base | `ollama pull gemma4:26b` | HIGH (for overnight tasks) |
| Pull vector-chairman base | `ollama pull gemma4:31b` | HIGH (for council + reflection) |
| Pull qwen3:30b-a3b | `ollama pull qwen3:30b-a3b` | MEDIUM (MoE reasoning upgrade) |
| Create vector-deep | `ollama create vector-deep -f modelfiles/vector-deep.modelfile` | HIGH (after pull) |
| Create vector-chairman | `ollama create vector-chairman -f modelfiles/vector-chairman.modelfile` | HIGH (after pull) |
| Phone ambient node | Run `phone_node/setup.sh` on Termux | LOW (phone not ready) |
| Download Kokoro TTS model | ~300MB from kokoro-onnx releases | MEDIUM |
| Train "Hey VECTOR" wake word | openwakeword custom training | LOW |
| Install face_recognition | `pip install face-recognition` | LOW |
| Install mediapipe | `pip install mediapipe` | LOW |
| Install pytesseract | Tesseract binary + `pip install pytesseract` | LOW |

---

## Commit Log

| Commit | Message |
|--------|---------|
| `07f3dc0` | feat: Phase 2 districts — Reflection, Health, Finance, Projects |
| `a25f166` | feat(T7-3): Phone node — Termux ambient server, ADB bridge, loop wired |
| `9c8a554` | feat(T6-3): Cloud layer — brain server, agent workers, Cloudflare Worker, dashboard |
| `e3f7090` | feat(T6-D): LLM Council — 3-stage deliberation with HP gate and weekly throttle |
| `df351c4` | feat(T6-C): Research district — WebScout, PaperReader, NewsAggregator, RedditMiner |
| `010c8c5` | feat(T6-B): Memory Curator district — ConsolidationBot + PatternFinder |
| `ae91e33` | feat(T6): ObsidianSync — LightRAG vault bridge, Day 6 Obsidian gate PASS |
| `8403ae2` | feat: migrate config to Pydantic BaseSettings with type validation |
| `057c580` | [T2] complete intelligence stack + Claude Code infrastructure |
