# VECTOR Repository Inventory

**Purpose:** Complete directory structure and purpose mapping  
**Level:** System Level (Level 1)

---

## Repository Overview

**Total Scale:** ~1.6 million lines of code  
**Python Files:** ~7,000  
**Markdown Files:** ~19,642  
**Total Files:** ~50,000+

---

## Top-Level Directory Structure

### Core Runtime (VECTOR_CORE)

#### `core/` — Core Runtime Systems
**Purpose:** All core VECTOR systems  
**Status:** ✅ Production-reachable  
**Files:** ~1,332 Python files

**Major Subdirectories:**

| Directory | Purpose | Status | Key Files |
|-----------|---------|--------|-----------|
| `core/api/` | FastAPI server | ✅ | `app.py`, `routers/` |
| `core/loop/` | Autonomous loop | ✅ | `autonomous_loop.py`, `context_engine.py`, `decision_engine.py` |
| `core/brain/` | Intelligence stack | ✅ | `goal_system.py`, `epistemic_tracker.py`, `red_team_agent.py` |
| `core/memory/` | Memory systems | ✅ | `episodic.py`, `policy.py`, `reasoning_memory.py` |
| `core/city/` | Agent city | ✅ | `agent_base.py`, `agent_registry.py`, `governor.py` |
| `core/inference/` | Model routing | ✅ | `provider_client.py`, `ollama_safe.py`, `llm_providers.py` |
| `core/voice/` | Voice pipeline | ⚠️ | `stt.py`, `tts.py`, `wake_word.py` |
| `core/sensing/` | Sensors | ✅ | `camera.py`, `screen_observer.py`, `health_monitor.py` |
| `core/control/` | Device control | ✅ | `pc_controller.py`, `phone_controller.py` |
| `core/browser/` | Browser automation | ✅ | `dom_pruner.py`, `pii_scrub.py`, `auth_profiles.py` |
| `core/collections/` | Data layer | ✅ | Schema engine, CRUD, migrations |
| `core/engine/` | Engine systems | ✅ | `oauth/`, `webhook/`, `event_bus.py` |
| `core/security/` | Security | ✅ | `prompt_injection.py`, `ssrf_guard.py`, `taint_tracker.py` |
| `core/knowledge/` | Knowledge processing | ✅ | `domain_extractor.py`, `wiki_parser.py` |
| `core/runtime/` | Runtime utilities | ✅ | `doctor.py`, `production_check.py`, `tls.py` |

**Dependencies:** Internal only  
**Callers:** All districts, all agents  
**Production Status:** ✅ Production-reachable

---

#### `districts/` — District Implementations
**Purpose:** 33+ specialized districts  
**Status:** ✅ All built  
**Files:** ~133 agent files

**Districts:**

| District | Purpose | Agents | Status |
|----------|---------|--------|--------|
| `governance/` | LLM Council | `llm_council.py` | ✅ |
| `security/` | Threat detection | `threat_scout.py`, `node_guard.py`, `malware_hunter.py` | ✅ |
| `coding/` | Code generation | `git_bot.py`, `code_reviewer.py`, `architect_bot.py`, `bug_hunter.py`, `test_writer.py` | ✅ |
| `time_calendar/` | Scheduling | `kiit_scraper.py`, `deadline_manager.py`, `time_blocker.py` | ✅ |
| `communications/` | Messaging | `communications_adapter.py`, `person_model.py`, `style_model.py` | ✅ |
| `memory_curator/` | Memory management | `consolidation_bot.py`, `pattern_finder.py` | ✅ |
| `research/` | Research | `web_scout.py`, `paper_reader.py`, `news_aggregator.py`, `reddit_miner.py`, `opencli_adapter.py`, `research_hub.py` | ✅ |
| `intelligence/` | Intelligence | (via news_trends + pattern_detective) | ✅ |
| `skills/` | Skill tracking | `skill_mapper.py`, `gap_analyst.py`, `mastery_tracker.py` | ✅ |
| `languages/` | Language learning | `hindi_coach.py`, `bengali_coach.py`, `assamese_coach.py`, `english_coach.py`, `japanese_coach.py` | ✅ |
| `interview_prep/` | Interview prep | `mock_interviewer.py`, `report_generator.py`, `company_researcher.py`, `feedback_analyst.py` | ✅ |
| `learning/` | Video learning | `video_ingestor.py`, `concept_extractor.py`, `course_tracker.py`, `note_organizer.py` | ✅ |
| `finance/` | Finance | `upi_parser.py`, `expense_tracker.py`, `budget_analyst.py`, `tax_calendar.py` | ✅ |
| `health/` | Health tracking | `sleep_tracker.py`, `fatigue_monitor.py`, `exercise_logger.py`, `biometrics_aggregator.py` | ✅ |
| `reflection/` | Reflection | `daily_reviewer.py`, `journal_writer.py`, `growth_analyst.py` | ✅ |
| `projects/` | Project management | `project_planner.py`, `deadline_watcher.py`, `progress_tracker.py`, `doc_writer.py` | ✅ |
| `startups/` | Startup validation | `market_scanner.py`, `idea_validator.py`, `competitor_spy.py`, `revenue_modeler.py` | ✅ |
| `investment/` | Investment analysis | `stock_analyst.py`, `fundamentals_bot.py`, `technical_bot.py`, `sentiment_bot.py` | ✅ |
| `content/` | Content creation | `script_generator.py`, `video_generator.py`, `voice_generator.py`, `uploader.py`, `comfyui_adapter.py`, `video_merger.py`, `caption_generator.py` | ✅ |
| `agency/` | Agency management | `content_strategist.py`, `client_manager.py`, `performance_tracker.py` | ✅ |
| `karpathy_lab/` | Karpathy study | `progress_tracker.py`, `code_typer.py`, `data_prep.py`, `architecture_builder.py`, `autoresearch_runner.py` | ✅ |
| `relationships/` | Relationship management | `contact_manager.py`, `communication_analyst.py` | ✅ |
| `privacy/` | Privacy enforcement | `data_flow_auditor.py`, `privacy_enforcer.py` | ✅ |
| `pattern_detective/` | Pattern detection | `behavior_analyst.py`, `habit_finder.py` | ✅ |
| `news_trends/` | News aggregation | `ai_news_bot.py`, `market_trends_bot.py`, `opportunity_spotter.py` | ✅ |
| `calls/` | Call handling | `call_screener.py`, `transcription_bot.py`, `voice_responder.py` | ✅ |
| `ops/` | Operations | `sre_monitor.py`, `devops_automator.py`, `incident_commander.py` | ✅ |
| `data_analytics/` | Analytics | `analytics_reporter.py`, `performance_benchmarker.py`, `data_engineer.py` | ✅ |
| `personal_growth/` | Personal growth | `behavioral_nudge_engine.py`, `zk_steward.py`, `feedback_synthesizer.py` | ✅ |
| `documentation/` | Documentation | `technical_writer.py`, `doc_generator.py` | ✅ |
| `qa/` | Quality assurance | `reality_checker.py`, `evidence_collector.py`, `workflow_architect.py`, `api_tester.py`, `test_results_analyzer.py`, `accessibility_auditor.py`, `tool_evaluator.py`, `workflow_optimizer.py`, `model_qa_specialist.py` | ✅ |
| `chief_of_staff/` | Executive assistant | `chief_of_staff.py` | ✅ |
| `marketing/` | Marketing | `seo_specialist.py`, `growth_hacker.py`, `social_media_strategist.py`, `content_creator.py`, `ai_citation_strategist.py` | ✅ |
| `design/` | Design | `ui_designer.py`, `ux_researcher.py`, `image_prompt_engineer.py` | ✅ |

**Dependencies:** `core/`  
**Callers:** Governor, autonomous loop  
**Production Status:** ✅ All production-reachable

---

#### `vectorcode/` — VectorCode Intelligence Platform
**Purpose:** Absorbed from OpenJarvis + Hermes + Ruflo repos  
**Status:** ✅ Fully integrated  
**Files:** ~2,000+ files

**Major Components:**

| Component | Purpose | Status |
|-----------|---------|--------|
| `vectorcode/src/` | Core platform | ✅ |
| `vectorcode/src/neural_training.py` | RL algorithms (A2C, DQN, PPO, SARSA, Q-Learning, DecisionTransformer) | ✅ |
| `vectorcode/src/neural_flash_attention.py` | FlashAttention O(N) | ✅ |
| `vectorcode/src/neural_moe_router.py` | MoE router | ✅ |
| `vectorcode/src/reasoning_bank.py` | Reasoning bank (RULE 8) | ✅ |
| `vectorcode/src/router.py` | GNN router (MoE→GNN→keyword→regex) | ✅ |
| `vectorcode/src/claims.py` | Claim service | ✅ |
| `vectorcode/src/guidance.py` | Threat detector, authority gate | ✅ |
| `vectorcode/src/swarm.py` | Swarm coordinator (8 topologies) | ✅ |
| `vectorcode/src/agent/curator.py` | Skill maintenance | ✅ |
| `vectorcode/src/agent/lsp/` | LSP integration | ✅ |
| `vectorcode/src/channels/` | 30+ communication adapters | ✅ |
| `vectorcode/skills/` | 100+ skills | ✅ |

**Dependencies:** Independent platform  
**Callers:** VECTOR core, districts  
**Production Status:** ✅ Production-reachable

---

### Infrastructure

#### `api/` — Cloudflare Worker API
**Purpose:** Cloud API endpoint  
**Status:** ✅ LIVE  
**Files:** TypeScript

**Components:**
- `src/router.ts` — API router
- `wrangler.toml` — Cloudflare config
- D1 database (7 tables)
- KV storage
- R2 storage

**Endpoints:**
- `/status`
- `/health`
- `/heartbeat`
- `/command` + queue
- `/memory/recent`
- `/agents`
- `/goals`

**Dependencies:** Cloudflare  
**Callers:** Remote clients  
**Production Status:** ✅ Deployed

---

#### `frontend/` — Web UI
**Purpose:** HUD dashboard  
**Status:** ✅ Operational  
**Files:** HTML/JS/CSS (~6.3k LOC)

**Features:**
- Status dashboard
- Command box
- Memory visualization
- Agent monitoring
- Log viewer

**Dependencies:** FastAPI backend  
**Callers:** Browser  
**Production Status:** ✅ Served at `/hud/`

---

#### `cloud/` — Cloud Infrastructure
**Purpose:** Cloud deployment configs  
**Status:** ⚠️ Partial  
**Files:** Various

**Components:**
- `brain_server/` — Fly.io (NOT DEPLOYED, owner declined)
- `supabase/` — Supabase schema
- `cloudflare/` — Cloudflare configs

**Production Status:** ⚠️ Cloudflare ✅, Fly.io ❌

---

#### `deploy/` — Deployment Scripts
**Purpose:** Deployment automation  
**Status:** ✅  
**Files:** PowerShell, Bash

**Scripts:**
- `install_service.ps1` — NSSM Windows service
- `supabase_schema.sql` — Supabase schema
- Various deployment helpers

**Production Status:** ✅ Production-ready

---

### Data & Configuration

#### `data/` — Runtime Data
**Purpose:** Runtime data storage  
**Status:** ✅  
**Contents:**
- `golden_intent_dataset.jsonl` — 737 examples
- `intent_examples.json` — 590+ examples
- `adapters/` — LoRA adapters
- `logs/` — Runtime logs
- `karpathy/` — Karpathy study data

**Production Status:** ✅ Production data

---

#### `config/` — Configuration
**Purpose:** Configuration files  
**Status:** ✅  
**Files:**
- `agent_manifest.yaml` — Agent definitions
- `model_catalog.yaml` — Model routing
- `providers.yaml` — OAuth providers (83)

**Production Status:** ✅ Production config

---

#### `modelfiles/` — Ollama Model Definitions
**Purpose:** Custom Ollama models  
**Status:** ✅  
**Files:** 10 modelfiles

**Models:**
- `vector-ambient` (gemma4:e2b)
- `vector-focus` (gemma4:e4b)
- `vector-multilingual` (qwen3:14b)
- `vector-reasoning` (qwen3:14b)
- `vector-coder` (qwen3:14b)
- `vector-deep` (gemma4:26b)
- `vector-chairman` (gemma4:31b)
- `vector-r1` (deepseek-r1)
- `vector-dev` (devstral)
- `vector-fast` (mistral-small3.1)

**Production Status:** ✅ Built

---

### Tools & Scripts

#### `scripts/` — Utility Scripts
**Purpose:** Development and operational scripts  
**Status:** ✅  
**Files:** ~100 scripts

**Key Scripts:**
- `train_intent_real.py` — LoRA training
- `auto_retrain_intent.py` — Automated retraining
- `calibrate_intent_threshold.py` — Threshold calibration
- `diag_tier6.py` — Integration test
- `smoke_test.py` — Smoke test
- `integration_check.py` — Integration check

**Production Status:** ✅ Production-ready

---

#### `tools/` — MCP Tools
**Purpose:** Model Context Protocol tools  
**Status:** ✅  
**Files:** ~20 tools

**Tools:**
- Filesystem, shell, browser
- GitHub, databases
- Communication, email
- System control

**Production Status:** ✅ Production-ready

---

### Testing

#### `tests/` — Test Suite
**Purpose:** Unit and integration tests  
**Status:** ✅ 140+ passing  
**Files:** ~100 test files

**Coverage:**
- Permission gateway (63 tests)
- Memory stores (38 tests)
- Decision engine (112 tests)
- All districts (47 tests)
- Absorbed repos (224 tests)

**Production Status:** ✅ All passing

---

### Documentation

#### `docs/` — Documentation
**Purpose:** Architecture docs, ADRs, design docs  
**Status:** ✅  
**Files:** ~50 docs

**Key Docs:**
- `intent_classification_architecture.md` — Intent classification
- `adr/` — Architecture Decision Records (6)
- `phase_status.md` — Phase tracker

**Production Status:** ✅ Documentation

---

#### `brain/` — Obsidian Vault (Junction)
**Purpose:** Knowledge base  
**Status:** ✅  
**Location:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain\`

**Structure:**
- `VECTOR/` — VECTOR architecture
- `Blueprint/` — Governing strategy
- `CLAUDE.md` — User profile
- `GOALS.md` — Goals

**Production Status:** ✅ Active

---

### Experimental / Archived

#### `hands/` — Autonomous Hands
**Purpose:** Experimental agent hands  
**Status:** 🧪 EXPERIMENTAL  
**Files:** ~10 files

**Production Status:** 🧪 Experimental

---

#### `dickens/` — Dickens System
**Purpose:** Experimental  
**Status:** 🧪 EXPERIMENTAL  
**Files:** ~5 files

**Production Status:** 🧪 Experimental

---

#### `memory_tree/` — Memory Tree
**Purpose:** Experimental memory structure  
**Status:** 🧪 EXPERIMENTAL  
**Files:** ~10 files

**Production Status:** 🧪 Experimental

---

#### `seo_portfolio/` — SEO Portfolio
**Purpose:** SEO tools  
**Status:** 🧪 EXPERIMENTAL  
**Files:** ~20 files

**Production Status:** 🧪 Experimental

---

#### `phone_node/` — Phone Termux Node
**Purpose:** Android Termux ambient node  
**Status:** ⚠️ Needs setup  
**Files:** ~5 files

**Production Status:** ⚠️ Owner-only setup needed

---

### Vendored / Third-Party

#### `ponytail/` — Ponytail Decision Ladder
**Purpose:** Vendored from DietrichGebert/ponytail  
**Status:** 📦 VENDORED  
**Integration:** Wired into `core/inference/ponytail_guard.py`

**Purpose:** Enforce minimal-code decision ladder for SaaS builds

**Production Status:** ✅ Integrated

---

#### `.claude/` — Claude Code Configuration
**Purpose:** Claude Code skills, commands, hooks  
**Status:** 📦 THIRD-PARTY  
**Files:** ~200 files

**Components:**
- `skills/` — 100+ skills
- `commands/` — 31 commands
- `hooks/` — 8 hooks
- `agents/` — Agent definitions

**Production Status:** ✅ Active

---

#### `node_modules/` — Node Dependencies
**Purpose:** npm packages  
**Status:** 📦 THIRD-PARTY  
**Size:** ~500MB

**Production Status:** ✅ Dependencies

---

#### `.deepeval/` — DeepEval Configuration
**Purpose:** Evaluation framework  
**Status:** 📦 THIRD-PARTY  
**Files:** ~10 files

**Production Status:** ✅ Active

---

### Generated / Cache

#### `__pycache__/` — Python Cache
**Purpose:** Python bytecode cache  
**Status:** 🔄 GENERATED  
**Size:** ~100MB

**Production Status:** 🔄 Auto-generated

---

#### `.pytest_cache/` — Pytest Cache
**Purpose:** Pytest cache  
**Status:** 🔄 GENERATED  
**Size:** ~10MB

**Production Status:** 🔄 Auto-generated

---

#### `graphify-out/` — Knowledge Graph Output
**Purpose:** Graphify output  
**Status:** 🔄 GENERATED  
**Files:** `graph.json`, `GRAPH_REPORT.md`

**Production Status:** 🔄 Generated

---

#### `renders/` — Rendered Content
**Purpose:** Rendered videos/images  
**Status:** 🔄 GENERATED  
**Size:** ~1GB

**Production Status:** 🔄 Generated

---

#### `attachments/` — Attachments
**Purpose:** Uploaded files  
**Status:** 🔄 GENERATED  
**Size:** ~100MB

**Production Status:** 🔄 Generated

---

#### `test_tmp/` — Test Temp Files
**Purpose:** Test temporary files  
**Status:** 🔄 GENERATED  
**Size:** ~10MB

**Production Status:** 🔄 Auto-generated

---

#### `_cleanup_trash_2026-07-28/` — Cleanup Archive
**Purpose:** Archived trash  
**Status:** 💀 ARCHIVED  
**Size:** ~50MB

**Production Status:** 💀 Archived

---

## Classification Summary

### VECTOR_CORE (Core Runtime)
- `core/` — All core systems
- `districts/` — All districts
- `vectorcode/` — VectorCode platform

### VECTOR_RUNTIME (Runtime Execution)
- `run_vector.py` — Main launcher
- `core/api/` — FastAPI server
- `core/loop/` — Autonomous loop

### VECTOR_DISTRICT (District Implementations)
- `districts/*/` — 33+ districts

### VECTOR_AGENT (Agent Implementations)
- `districts/*/*.py` — 133+ agent files

### VECTOR_MEMORY (Memory Systems)
- `core/memory/` — All memory systems

### VECTOR_MODEL (Model Integrations)
- `core/inference/` — All model routing

### VECTOR_TOOL (Tool Implementations)
- `tools/` — MCP tools
- `core/mcp_tools/` — MCP tool implementations

### VECTOR_INTEGRATION (External Integrations)
- `vectorcode/src/channels/` — Communication adapters
- `core/engine/oauth/` — OAuth integrations

### VECTOR_API (API Endpoints)
- `core/api/` — FastAPI routes
- `api/` — Cloudflare Worker

### VECTOR_FRONTEND (Web UI)
- `frontend/` — HUD dashboard

### VECTOR_INFRASTRUCTURE (Infrastructure)
- `cloud/` — Cloud configs
- `deploy/` — Deployment scripts
- `config/` — Configuration

### VENDORED (Third-Party Code)
- `ponytail/` — Ponytail decision ladder
- `.claude/` — Claude Code config
- `node_modules/` — npm packages

### THIRD_PARTY (External Dependencies)
- `.deepeval/` — DeepEval
- All pip dependencies

### GENERATED (Auto-Generated)
- `__pycache__/`
- `.pytest_cache/`
- `graphify-out/`
- `renders/`
- `attachments/`
- `test_tmp/`

### EXPERIMENTAL (Not Production)
- `hands/`
- `dickens/`
- `memory_tree/`
- `seo_portfolio/`

### ARCHIVED (No Longer Active)
- `_cleanup_trash_2026-07-28/`

### TEST_ONLY (Test Infrastructure)
- `tests/`

### DEVELOPMENT_ONLY (Development Tools)
- `scripts/` (some)

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `03_VECTOR_VS_REPOSITORY.md` — VECTOR vs vendored
- `04_RUNTIME_AND_BOOT.md` — Startup sequence
- `32_ALL_DISTRICTS.md` — District details
- `33_ALL_AGENTS.md` — Agent index

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
