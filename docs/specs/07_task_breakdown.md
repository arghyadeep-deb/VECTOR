# 07 — Task Breakdown

> Every task maps to a functional requirement. No code written without a spec reference.

| Task | File | Day | Spec |
|------|------|-----|------|
| T1.1 | `core/config.py` | 1 | FR-01, FR-08 — CONFIG dict, env detection, vault path, model routing |
| T1.2 | `core/memory/episodic.py` | 1 | FR-03 — SQLite FTS5 + SQLCipher, 5 tables, store() recall() remember() |
| T1.3 | `core/memory/multi_db_manager.py` | 1 | FR-03 — 4-DB sync, last-write-wins, health checks, auto-restore |
| T1.4 | `core/main.py` + `run_vector.py` | 1 | FR-01 — FastAPI /command /status /voice /agent/award |
| T2.1 | `core/loop/context_engine.py` | 2 | FR-02, FR-09 — 9 domains, session_hydration_prompt() |
| T2.2 | `core/brain/goal_system.py` | 2 | FR-01 — 3 horizons, pre-seeded goals, generate_immediate_actions() |
| T2.3 | `core/loop/decision_engine.py` | 2 | FR-07 — 4 candidates, scoring formula, log ALL including rejected |
| T2.4 | `core/memory/policy.py` | 2 | FR-07 — get_score() BEFORE + update_from_outcome() AFTER, both wired |
| T2.5 | `core/memory/reasoning_memory.py` | 2 | FR-10 — chains, inject_past_reasoning(), is_training_data flag |
| T2.6 | `core/loop/permission_gateway.py` | 2 | FR-06 — GREEN/YELLOW/RED matrix, audit_log(), zero direct LLM access |
| T2.7 | `core/city/agent_base.py` | 2 | FR-18–23 — HP, evolution, ghost_memory, get_upgraded_model() |
| T2.8 | `core/city/governor.py` + `task_router.py` | 2 | FR-01 — VECTOR routes tasks to districts by type |
| T3.1 | `core/voice/stt.py` + `tts.py` | 3 | FR-02, FR-08 — Whisper local, Kokoro, Google TTS, language_detector |
| T3.2 | `core/voice/wake_word.py` + `ambient_listener.py` | 3 | FR-02 — openWakeWord, 5s buffer, JSON output from vector-ambient |
| T3.3 | `core/loop/autonomous_loop.py` | 3 | FR-01 — asyncio.gather 5 coroutines, all with try/except restart |
| T4.1 | `core/sensing/` (all 4 files) | 4 | FR-09 — camera fatigue, screen activity, sound, health monitor |
| T4.2 | `core/control/` (all files) | 4 | FR-06 — PC controller, ADB, malware 3-layer, node router |
| T5.1 | `agents/districts/coding/` | 5 | FR-05 — git_bot auto-commit, code_reviewer, OpenCLI GitHub CLI |
| T5.2 | `agents/districts/time_calendar/` | 5 | FR-04 — KIIT scraper Playwright, deadline_manager, attendance alert |
| T5.3 | `agents/districts/security/` | 5 | FR-06 — threat_scout, malware_hunter, node_guard |
| T5.4 | `agents/districts/communications/` | 5 | FR-11 — Hermes adapter, calls_handler (NOT rebuilt from scratch) |
| T6.1 | `agents/districts/memory_curator/` | 6 | FR-03 — LightRAG integration, consolidation_bot |
| T6.2 | `agents/districts/research/` | 6 | FR-14 — OpenCLI autoresearch, paper_reader, news_aggregator |
| T6.3 | `cloud/` + `api/` + `dashboard/` | 6 | FR-01 — Fly.io brain, Cloudflare Workers, Vercel dashboard |
| T7.1 | `core/memory/obsidian_sync.py` | 7 | FR-03 — bidirectional vault, watchdog ingestion, Daily/ write |
| T7.2 | `agents/districts/governance/llm_council.py` | 7 | FR-10 — council flow, HP gate 700+, sessions as training data |
| T7.3 | `phone_node/` setup | 7 | FR-08 — old phone Termux, ambient_server.py, ADB bridge |