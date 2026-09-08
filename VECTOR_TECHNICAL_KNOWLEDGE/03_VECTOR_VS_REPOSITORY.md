# VECTOR vs Repository Boundary

**Purpose:** Classify what is VECTOR core vs vendored/third-party  
**Level:** System Level (Level 1)

---

## Classification Framework

Every significant piece of code in the repository is classified as:

| Category | Definition | Example |
|----------|-----------|---------|
| VECTOR_CORE | Core runtime systems | `core/loop/autonomous_loop.py` |
| VECTOR_RUNTIME | Runtime execution | `run_vector.py`, `core/api/app.py` |
| VECTOR_DISTRICT | District implementations | `districts/coding/git_bot.py` |
| VECTOR_AGENT | Agent implementations | `districts/security/threat_scout.py` |
| VECTOR_MEMORY | Memory systems | `core/memory/episodic.py` |
| VECTOR_MODEL | Model integrations | `core/inference/provider_client.py` |
| VECTOR_TOOL | Tool implementations | `tools/mcp_tools.py` |
| VECTOR_INTEGRATION | External integrations | `vectorcode/src/channels/telegram.py` |
| VECTOR_API | API endpoints | `core/api/routers/status.py` |
| VECTOR_FRONTEND | Web UI | `frontend/index.html` |
| VECTOR_INFRASTRUCTURE | Infrastructure | `deploy/install_service.ps1` |
| VENDORED | Third-party code (integrated) | `ponytail/` |
| THIRD_PARTY | External dependencies | `node_modules/`, pip packages |
| GENERATED | Auto-generated | `__pycache__/`, `renders/` |
| EXPERIMENTAL | Not production | `hands/`, `dickens/` |
| ARCHIVED | No longer active | `_cleanup_trash_2026-07-28/` |
| TEST_ONLY | Test infrastructure | `tests/` |
| DEVELOPMENT_ONLY | Development tools | `scripts/` (some) |
| UNKNOWN | Cannot classify | Uncategorized files |

---

## VECTOR_CORE — Core Runtime Systems

### `core/` Directory

**Classification:** VECTOR_CORE  
**Purpose:** All core VECTOR systems  
**Status:** ✅ Production-reachable  
**Size:** ~1,332 Python files

**Subdirectories:**

| Path | Purpose | Classification | Status |
|------|---------|----------------|--------|
| `core/api/` | FastAPI server | VECTOR_CORE | ✅ |
| `core/loop/` | Autonomous loop | VECTOR_CORE | ✅ |
| `core/brain/` | Intelligence stack | VECTOR_CORE | ✅ |
| `core/memory/` | Memory systems | VECTOR_MEMORY | ✅ |
| `core/city/` | Agent city | VECTOR_CORE | ✅ |
| `core/inference/` | Model routing | VECTOR_MODEL | ✅ |
| `core/voice/` | Voice pipeline | VECTOR_CORE | ⚠️ |
| `core/sensing/` | Sensors | VECTOR_CORE | ✅ |
| `core/control/` | Device control | VECTOR_CORE | ✅ |
| `core/browser/` | Browser automation | VECTOR_CORE | ✅ |
| `core/collections/` | Data layer | VECTOR_CORE | ✅ |
| `core/engine/` | Engine systems | VECTOR_CORE | ✅ |
| `core/security/` | Security | VECTOR_CORE | ✅ |
| `core/knowledge/` | Knowledge processing | VECTOR_CORE | ✅ |
| `core/runtime/` | Runtime utilities | VECTOR_CORE | ✅ |
| `core/scraper/` | Web scraping | VECTOR_CORE | ✅ |
| `core/research_engine/` | Research engine | VECTOR_CORE | ✅ |
| `core/coding_assistant/` | Coding assistant | VECTOR_CORE | ✅ |
| `core/sandbox/` | Sandboxing | VECTOR_CORE | ✅ |
| `core/scheduler/` | Scheduling | VECTOR_CORE | ✅ |
| `core/mining/` | Data mining | VECTOR_CORE | 🧪 |
| `core/telemetry/` | Telemetry | VECTOR_CORE | ✅ |
| `core/ui/` | UI utilities | VECTOR_FRONTEND | ✅ |

**Key Files:**

```python
# Autonomous Loop
core/loop/autonomous_loop.py          # Main loop
core/loop/context_engine.py           # World state
core/loop/decision_engine.py          # Decision making

# Intelligence
core/brain/goal_system.py             # Goals
core/brain/epistemic_tracker.py       # Uncertainty
core/brain/red_team_agent.py          # Adversarial review
core/brain/hypothesis_engine.py       # Proactive insights
core/brain/synthesis_bridge.py        # Cross-domain patterns
core/brain/person_model.py            # Theory of mind
core/brain/blueprint_doctrine.py      # Doctrine injection

# Memory
core/memory/episodic.py               # Episodic memory
core/memory/policy.py                 # Policy memory
core/memory/reasoning_memory.py       # Reasoning chains
core/memory/obsidian_sync.py          # Obsidian integration
core/memory/light_rag.py              # Semantic memory

# Agent City
core/city/agent_base.py               # Agent base class
core/city/agent_registry.py           # Agent registry
core/city/governor.py                 # Governor/routing
core/city/evolution_engine.py         # Agent evolution
core/city/intent_matcher.py           # Intent classification
core/city/intent_qwen3_8b.py          # Qwen3 classifier
core/city/intent_monitor.py           # Performance monitor

# Model Inference
core/inference/provider_client.py     # Model routing
core/inference/ollama_safe.py         # Ollama integration
core/inference/llm_providers.py       # 27 providers
core/inference/model_catalog.py       # Model catalog
core/inference/quota_ledger.py        # Budget tracking
core/inference/key_pool.py            # Key management

# Permission & Security
core/loop/permission_gateway.py       # Permission gates
core/security/prompt_injection.py     # Injection detection
core/security/ssrf_guard.py           # SSRF protection
core/security/taint_tracker.py        # Taint tracking

# Voice
core/voice/stt.py                     # Speech-to-text
core/voice/tts.py                     # Text-to-speech
core/voice/wake_word.py               # Wake word detection
core/voice/language_detector.py       # Language detection
core/voice/ambient_listener.py        # Ambient listening

# Sensing & Control
core/sensing/camera.py                # Camera/face detection
core/sensing/screen_observer.py       # Screen observation
core/sensing/health_monitor.py        # Health monitoring
core/sensing/sound_classifier.py      # Sound classification
core/control/pc_controller.py         # PC control
core/control/phone_controller.py      # Phone control
core/control/security/malware_detector.py  # Malware detection
```

**Dependencies:** Internal only  
**Callers:** All districts, all agents, autonomous loop  
**Production Status:** ✅ All production-reachable

---

## VECTOR_RUNTIME — Runtime Execution

### Entry Points

**Classification:** VECTOR_RUNTIME  
**Purpose:** Application startup and execution  
**Status:** ✅ Production-reachable

**Files:**

```python
run_vector.py                          # Main launcher (loop/api/smoke/doctor)
core/api/app.py                        # FastAPI application
core/mcp_server.py                     # MCP server
```

**run_vector.py Modes:**
- `loop` — Start autonomous loop (default)
- `api` — Start FastAPI server
- `smoke` — One-shot startup verification
- `doctor` — Dependency check
- `production-check` — Production readiness check
- `memory-repair` — Memory database repair

**Startup Sequence:**

```
1. Load .env
2. Configure file logging
3. Setup exception hooks
4. Start sidecars (ComfyUI, open-webui, etc.)
5. Start background services (AmbientListener)
6. Bootstrap agents (from manifest)
7. Start autonomous loop OR API server
```

**Key Functions:**

```python
# run_vector.py
def main()                           # CLI entry point
async def run_loop()                 # Start autonomous loop
def run_api(host, port)              # Start FastAPI server
async def smoke_test()               # Smoke test
def bootstrap_agents()               # Register agents from manifest
def _start_sidecars()                # Start optional sidecars
def _start_background_services()     # Start background services
async def _graceful_shutdown()       # Graceful shutdown
```

**Dependencies:** `core/`  
**Callers:** User, launch scripts  
**Production Status:** ✅ Production-reachable

---

## VECTOR_DISTRICT — District Implementations

### `districts/` Directory

**Classification:** VECTOR_DISTRICT  
**Purpose:** 33+ specialized districts  
**Status:** ✅ All built  
**Size:** ~133 agent files

**All Districts:**

| District | Purpose | Agents | Classification | Status |
|----------|---------|--------|----------------|--------|
| `governance/` | LLM Council | `llm_council.py` | VECTOR_DISTRICT | ✅ |
| `security/` | Threat detection | `threat_scout.py`, `node_guard.py`, `malware_hunter.py` | VECTOR_DISTRICT | ✅ |
| `coding/` | Code generation | `git_bot.py`, `code_reviewer.py`, `architect_bot.py`, `bug_hunter.py`, `test_writer.py` | VECTOR_DISTRICT | ✅ |
| `time_calendar/` | Scheduling | `kiit_scraper.py`, `deadline_manager.py`, `time_blocker.py` | VECTOR_DISTRICT | ✅ |
| `communications/` | Messaging | `communications_adapter.py`, `person_model.py`, `style_model.py` | VECTOR_DISTRICT | ✅ |
| `memory_curator/` | Memory management | `consolidation_bot.py`, `pattern_finder.py` | VECTOR_DISTRICT | ✅ |
| `research/` | Research | `web_scout.py`, `paper_reader.py`, `news_aggregator.py`, `reddit_miner.py`, `opencli_adapter.py`, `research_hub.py` | VECTOR_DISTRICT | ✅ |
| `intelligence/` | Intelligence | (via news_trends + pattern_detective) | VECTOR_DISTRICT | ✅ |
| `skills/` | Skill tracking | `skill_mapper.py`, `gap_analyst.py`, `mastery_tracker.py` | VECTOR_DISTRICT | ✅ |
| `languages/` | Language learning | `hindi_coach.py`, `bengali_coach.py`, `assamese_coach.py`, `english_coach.py`, `japanese_coach.py` | VECTOR_DISTRICT | ✅ |
| `interview_prep/` | Interview prep | `mock_interviewer.py`, `report_generator.py`, `company_researcher.py`, `feedback_analyst.py` | VECTOR_DISTRICT | ✅ |
| `learning/` | Video learning | `video_ingestor.py`, `concept_extractor.py`, `course_tracker.py`, `note_organizer.py` | VECTOR_DISTRICT | ✅ |
| `finance/` | Finance | `upi_parser.py`, `expense_tracker.py`, `budget_analyst.py`, `tax_calendar.py` | VECTOR_DISTRICT | ✅ |
| `health/` | Health tracking | `sleep_tracker.py`, `fatigue_monitor.py`, `exercise_logger.py`, `biometrics_aggregator.py` | VECTOR_DISTRICT | ✅ |
| `reflection/` | Reflection | `daily_reviewer.py`, `journal_writer.py`, `growth_analyst.py` | VECTOR_DISTRICT | ✅ |
| `projects/` | Project management | `project_planner.py`, `deadline_watcher.py`, `progress_tracker.py`, `doc_writer.py` | VECTOR_DISTRICT | ✅ |
| `startups/` | Startup validation | `market_scanner.py`, `idea_validator.py`, `competitor_spy.py`, `revenue_modeler.py` | VECTOR_DISTRICT | ✅ |
| `investment/` | Investment analysis | `stock_analyst.py`, `fundamentals_bot.py`, `technical_bot.py`, `sentiment_bot.py` | VECTOR_DISTRICT | ✅ |
| `content/` | Content creation | `script_generator.py`, `video_generator.py`, `voice_generator.py`, `uploader.py`, `comfyui_adapter.py`, `video_merger.py`, `caption_generator.py` | VECTOR_DISTRICT | ✅ |
| `agency/` | Agency management | `content_strategist.py`, `client_manager.py`, `performance_tracker.py` | VECTOR_DISTRICT | ✅ |
| `karpathy_lab/` | Karpathy study | `progress_tracker.py`, `code_typer.py`, `data_prep.py`, `architecture_builder.py`, `autoresearch_runner.py` | VECTOR_DISTRICT | ✅ |
| `relationships/` | Relationship management | `contact_manager.py`, `communication_analyst.py` | VECTOR_DISTRICT | ✅ |
| `privacy/` | Privacy enforcement | `data_flow_auditor.py`, `privacy_enforcer.py` | VECTOR_DISTRICT | ✅ |
| `pattern_detective/` | Pattern detection | `behavior_analyst.py`, `habit_finder.py` | VECTOR_DISTRICT | ✅ |
| `news_trends/` | News aggregation | `ai_news_bot.py`, `market_trends_bot.py`, `opportunity_spotter.py` | VECTOR_DISTRICT | ✅ |
| `calls/` | Call handling | `call_screener.py`, `transcription_bot.py`, `voice_responder.py` | VECTOR_DISTRICT | ✅ |
| `ops/` | Operations | `sre_monitor.py`, `devops_automator.py`, `incident_commander.py` | VECTOR_DISTRICT | ✅ |
| `data_analytics/` | Analytics | `analytics_reporter.py`, `performance_benchmarker.py`, `data_engineer.py` | VECTOR_DISTRICT | ✅ |
| `personal_growth/` | Personal growth | `behavioral_nudge_engine.py`, `zk_steward.py`, `feedback_synthesizer.py` | VECTOR_DISTRICT | ✅ |
| `documentation/` | Documentation | `technical_writer.py`, `doc_generator.py` | VECTOR_DISTRICT | ✅ |
| `qa/` | Quality assurance | `reality_checker.py`, `evidence_collector.py`, `workflow_architect.py`, `api_tester.py`, `test_results_analyzer.py`, `accessibility_auditor.py`, `tool_evaluator.py`, `workflow_optimizer.py`, `model_qa_specialist.py` | VECTOR_DISTRICT | ✅ |
| `chief_of_staff/` | Executive assistant | `chief_of_staff.py` | VECTOR_DISTRICT | ✅ |
| `marketing/` | Marketing | `seo_specialist.py`, `growth_hacker.py`, `social_media_strategist.py`, `content_creator.py`, `ai_citation_strategist.py` | VECTOR_DISTRICT | ✅ |
| `design/` | Design | `ui_designer.py`, `ux_researcher.py`, `image_prompt_engineer.py` | VECTOR_DISTRICT | ✅ |

**Dependencies:** `core/`  
**Callers:** Governor, autonomous loop  
**Production Status:** ✅ All production-reachable

---

## VECTOR_MEMORY — Memory Systems

### `core/memory/` Directory

**Classification:** VECTOR_MEMORY  
**Purpose:** All memory subsystems  
**Status:** ✅ Production-reachable  
**Size:** ~20 Python files

**Memory Types:**

| File | Type | Storage | Purpose | Status |
|------|------|---------|---------|--------|
| `episodic.py` | Episodic | SQLite FTS5 | Events, conversations | ✅ |
| `policy.py` | Policy | EMA | Learned behavior | ✅ |
| `reasoning_memory.py` | Reasoning | SQLite | Decision chains | ✅ |
| `obsidian_sync.py` | Obsidian | Markdown files | Human-readable notes | ✅ |
| `light_rag.py` | Semantic | nano-vectordb | Knowledge, facts | ✅ |
| `ghost_memory.py` | Ghost | SQLite | Deceased agent memory | ✅ |
| `session.py` | Session | In-memory | Current session state | ✅ |
| `consolidation.py` | Consolidation | SQLite | Memory consolidation | ✅ |

**Key Functions:**

```python
# Episodic Memory
EpisodicMemory.store(event_type, content, tags, source)
EpisodicMemory.retrieve(query, limit)
EpisodicMemory.consolidate()

# Policy Memory
PolicyMemory.get_score(action_type)
PolicyMemory.update_from_outcome(action_type, outcome)

# Reasoning Memory
ReasoningMemory.store_chain(chain, reward)
ReasoningMemory.get_similar_chains(query)

# Obsidian Sync
ObsidianSync.sync_to_vault(memory)
ObsidianSync.watch_vault()
```

**Dependencies:** SQLite, LightRAG  
**Callers:** Autonomous loop, agents, reflection  
**Production Status:** ✅ Production-reachable

---

## VECTOR_MODEL — Model Integrations

### `core/inference/` Directory

**Classification:** VECTOR_MODEL  
**Purpose:** All model integrations and routing  
**Status:** ✅ Production-reachable  
**Size:** ~30 Python files

**Providers:** 27 total

| Provider | Type | Models | Status |
|----------|------|--------|--------|
| Anthropic | Cloud | Claude Sonnet, Opus | ✅ |
| OpenAI | Cloud | GPT-4, GPT-5 | ✅ |
| Gemini | Cloud | Gemini 2.5 Pro | ✅ |
| Groq | Cloud | Llama, Mixtral | ✅ |
| DeepSeek | Cloud | DeepSeek V3, R1 | ✅ |
| Mistral | Cloud | Mistral Large | ✅ |
| OpenRouter | Cloud | Multi-provider | ✅ |
| Together | Cloud | Open-source models | ✅ |
| Fireworks | Cloud | Fast inference | ✅ |
| Perplexity | Cloud | Search-augmented | ✅ |
| Cohere | Cloud | Command R+ | ✅ |
| Azure | Cloud | Azure OpenAI | ✅ |
| Cloudflare | Cloud | Workers AI | ✅ |
| vLLM | Local | High-throughput | ✅ |
| HuggingFace | Cloud | Model hub | ✅ |
| Replicate | Cloud | Model hosting | ✅ |
| Anyscale | Cloud | Ray clusters | ✅ |
| Cerebras | Cloud | Fast inference | ✅ |
| SambaNova | Cloud | Fast inference | ✅ |
| NVIDIA | Cloud | NIM models | ✅ |
| Moonshot | Cloud | Kimi models | ✅ |
| Zhipu | Cloud | GLM models | ✅ |
| Baidu | Cloud | ERNIE models | ✅ |
| Yi | Cloud | Yi models | ✅ |
| LMStudio | Local | Local models | ✅ |
| Ollama | Local | Local models | ✅ |
| GitHub Models | Cloud | Free-tier models | ✅ |

**Key Files:**

```python
core/inference/provider_client.py      # Main routing
core/inference/ollama_safe.py          # Ollama integration
core/inference/llm_providers.py        # Provider implementations
core/inference/model_catalog.py        # Model catalog (YAML)
core/inference/quota_ledger.py         # Budget tracking
core/inference/key_pool.py             # Key management
core/inference/route_policy.py         # Routing policy
core/inference/model_pool.py           # Model aliases
core/inference/domain_router.py        # Domain-based routing
```

**Routing Logic:**

```python
# provider_client.py
async def chat(messages, model=None, domain=None):
    # 1. Check domain routing
    if domain:
        provider = domain_router.route(domain)
    
    # 2. Check model pool
    if model and model.startswith("domain:"):
        provider = model_pool.resolve(model)
    
    # 3. Route by complexity
    complexity = estimate_complexity(messages)
    if complexity == "simple":
        provider = select_free_tier()
    elif complexity == "medium":
        provider = select_balanced()
    else:  # heavy
        provider = select_premium()
    
    # 4. Check budget
    if quota_ledger.is_near_limit(provider):
        provider = "ollama"  # fallback
    
    # 5. Execute
    return await provider.chat(messages)
```

**Dependencies:** HTTP clients, API keys  
**Callers:** All agents, all districts  
**Production Status:** ✅ Production-reachable

---

## VECTOR_INTEGRATION — External Integrations

### `vectorcode/src/channels/` Directory

**Classification:** VECTOR_INTEGRATION  
**Purpose:** 30+ communication platform adapters  
**Status:** ✅ Production-reachable  
**Size:** ~50 files

**Platforms:**

| Platform | File | Inbound | Outbound | Status |
|----------|------|---------|----------|--------|
| Telegram | `telegram.py` | ✅ | ✅ | ✅ |
| WhatsApp | `whatsapp.py` | ✅ | ✅ | ✅ |
| WhatsApp Business | `whatsapp_business.py` | ✅ | ✅ | ✅ |
| Discord | `discord.py` | ✅ | ✅ | ✅ |
| Slack | `slack.py` | ✅ | ✅ | ✅ |
| Gmail | `gmail.py` | ✅ | ✅ | ✅ |
| Signal | `signal.py` | ✅ | ✅ | ✅ |
| Instagram | `instagram.py` | ❌ | ✅ | ✅ |
| YouTube | `youtube.py` | ❌ | ✅ | ✅ |
| Twitter/X | `twitter.py` | ❌ | ✅ | ✅ |
| LinkedIn | `linkedin.py` | ❌ | ✅ | ✅ |
| Reddit | `reddit.py` | ❌ | ✅ | ✅ |
| GitHub | `github.py` | ✅ | ✅ | ✅ |
| Matrix | `matrix.py` | ✅ | ✅ | ✅ |
| IRC | `irc.py` | ✅ | ✅ | ✅ |
| SMS | `sms.py` | ✅ | ✅ | ✅ |
| Pushover | `pushover.py` | ❌ | ✅ | ✅ |
| Email (SMTP) | `email.py` | ❌ | ✅ | ✅ |
| Webhook | `webhook.py` | ✅ | ✅ | ✅ |
| RSS | `rss.py` | ✅ | ❌ | ✅ |
| Atom | `atom.py` | ✅ | ❌ | ✅ |
| Mastodon | `mastodon.py` | ✅ | ✅ | ✅ |
| Bluesky | `bluesky.py` | ✅ | ✅ | ✅ |
| Nostr | `nostr.py` | ✅ | ✅ | ✅ |
| XMPP | `xmpp.py` | ✅ | ✅ | ✅ |
| Mattermost | `mattermost.py` | ✅ | ✅ | ✅ |
| Rocket.Chat | `rocketchat.py` | ✅ | ✅ | ✅ |
| Zulip | `zulip.py` | ✅ | ✅ | ✅ |
| Microsoft Teams | `teams.py` | ✅ | ✅ | ✅ |
| Google Chat | `google_chat.py` | ✅ | ✅ | ✅ |

**Gateway:** VectorCode (replaced Hermes, 2026-06-19)

**Key Files:**

```python
vectorcode/src/channels/base.py           # Base channel class
vectorcode/src/channels/registry.py       # Channel registry
vectorcode/src/channels/gateway.py        # Unified gateway
vectorcode/src/channels/telegram.py       # Telegram adapter
vectorcode/src/channels/whatsapp.py       # WhatsApp adapter
vectorcode/src/channels/discord.py        # Discord adapter
# ... (30+ adapters)
```

**Dependencies:** Platform APIs, HTTP clients  
**Callers:** Communications district, autonomous loop  
**Production Status:** ✅ Production-reachable

---

## VENDORED — Third-Party Code (Integrated)

### `ponytail/` Directory

**Classification:** VENDORED  
**Purpose:** Decision ladder for minimal-code enforcement  
**Source:** DietrichGebert/ponytail  
**Status:** ✅ Integrated  
**Size:** ~10 files

**Integration:**

```python
# core/inference/ponytail_guard.py
from ponytail.skills.ponytail import decision_ladder

def inject_into_llm_call(prompt):
    """Inject ponytail decision ladder into coding LLM calls."""
    ladder = decision_ladder(intensity="full")
    return f"{ladder}\n\n{prompt}"
```

**Purpose:** Enforce minimal-code decisions for SaaS builds (Wave-1 products)

**Dependencies:** None (self-contained)  
**Callers:** `core/inference/ponytail_guard.py`  
**Production Status:** ✅ Integrated

---

### `.claude/` Directory

**Classification:** THIRD_PARTY  
**Purpose:** Claude Code configuration  
**Status:** ✅ Active  
**Size:** ~200 files

**Components:**

| Component | Purpose | Status |
|-----------|---------|--------|
| `skills/` | 100+ skills | ✅ |
| `commands/` | 31 commands | ✅ |
| `hooks/` | 8 hooks | ✅ |
| `agents/` | Agent definitions | ✅ |
| `rules/` | VECTOR rules | ✅ |
| `settings.json` | Settings | ✅ |

**Key Files:**

```
.claude/rules/architecture.md       # Architecture rules
.claude/rules/code_style.md         # Code style rules
.claude/rules/models.md             # Model routing rules
.claude/rules/districts.md          # District rules
.claude/commands/loop-start.md      # Start loop command
.claude/commands/verify.md          # Verify command
.claude/skills/brainstorming/       # Brainstorming skill
.claude/skills/writing-plans/       # Plan writing skill
```

**Dependencies:** Claude Code  
**Callers:** Claude Code runtime  
**Production Status:** ✅ Active

---

## THIRD_PARTY — External Dependencies

### `node_modules/` Directory

**Classification:** THIRD_PARTY  
**Purpose:** npm packages  
**Status:** ✅ Dependencies  
**Size:** ~500MB

**Key Packages:**
- `wrangler` — Cloudflare Workers
- `playwright` — Browser automation
- `sharp` — Image processing
- `ffmpeg` — Video processing

**Dependencies:** npm  
**Callers:** Frontend, API  
**Production Status:** ✅ Dependencies

---

### Pip Dependencies

**Classification:** THIRD_PARTY  
**Purpose:** Python packages  
**Status:** ✅ Dependencies  
**Size:** ~2GB

**Key Packages:**

```
# Core
fastapi
uvicorn
httpx
pydantic
loguru

# AI/ML
torch
transformers
peft
ollama

# Memory
lightrag
sqlcipher3

# Voice
openai-whisper
kokoro-onnx
sounddevice

# Vision
opencv-python
face-recognition
mediapipe

# Browser
playwright

# Communication
python-telegram-bot
discord.py
slack-sdk

# Inference
anthropic
openai
google-generativeai

# ... (100+ packages)
```

**File:** `requirements.txt`  
**Dependencies:** pip  
**Callers:** All Python code  
**Production Status:** ✅ Dependencies

---

## GENERATED — Auto-Generated

### `__pycache__/` Directory

**Classification:** GENERATED  
**Purpose:** Python bytecode cache  
**Status:** 🔄 Auto-generated  
**Size:** ~100MB

**Contents:** `.pyc` files

**Dependencies:** Python runtime  
**Callers:** Python interpreter  
**Production Status:** 🔄 Auto-generated

---

### `.pytest_cache/` Directory

**Classification:** GENERATED  
**Purpose:** Pytest cache  
**Status:** 🔄 Auto-generated  
**Size:** ~10MB

**Contents:** Test results, cache

**Dependencies:** pytest  
**Callers:** pytest  
**Production Status:** 🔄 Auto-generated

---

### `graphify-out/` Directory

**Classification:** GENERATED  
**Purpose:** Knowledge graph output  
**Status:** 🔄 Generated  
**Size:** ~50MB

**Contents:**
- `graph.json` — Knowledge graph
- `GRAPH_REPORT.md` — Report

**Dependencies:** graphify skill  
**Callers:** graphify command  
**Production Status:** 🔄 Generated

---

### `renders/` Directory

**Classification:** GENERATED  
**Purpose:** Rendered videos/images  
**Status:** 🔄 Generated  
**Size:** ~1GB

**Contents:** Video files, image files

**Dependencies:** ComfyUI, FFmpeg  
**Callers:** Content district  
**Production Status:** 🔄 Generated

---

### `attachments/` Directory

**Classification:** GENERATED  
**Purpose:** Uploaded files  
**Status:** 🔄 Generated  
**Size:** ~100MB

**Contents:** User uploads

**Dependencies:** FastAPI  
**Callers:** API endpoints  
**Production Status:** 🔄 Generated

---

### `test_tmp/` Directory

**Classification:** GENERATED  
**Purpose:** Test temporary files  
**Status:** 🔄 Auto-generated  
**Size:** ~10MB

**Contents:** Test artifacts

**Dependencies:** pytest  
**Callers:** Tests  
**Production Status:** 🔄 Auto-generated

---

## EXPERIMENTAL — Not Production

### `hands/` Directory

**Classification:** EXPERIMENTAL  
**Purpose:** Autonomous hands (experimental)  
**Status:** 🧪 Experimental  
**Size:** ~10 files

**Contents:** Experimental agent implementations

**Dependencies:** `core/`  
**Callers:** None (not wired)  
**Production Status:** 🧪 Experimental

---

### `dickens/` Directory

**Classification:** EXPERIMENTAL  
**Purpose:** Dickens system (experimental)  
**Status:** 🧪 Experimental  
**Size:** ~5 files

**Contents:** Experimental narrative system

**Dependencies:** None  
**Callers:** None (not wired)  
**Production Status:** 🧪 Experimental

---

### `memory_tree/` Directory

**Classification:** EXPERIMENTAL  
**Purpose:** Memory tree (experimental)  
**Status:** 🧪 Experimental  
**Size:** ~10 files

**Contents:** Experimental memory structure

**Dependencies:** None  
**Callers:** None (not wired)  
**Production Status:** 🧪 Experimental

---

### `seo_portfolio/` Directory

**Classification:** EXPERIMENTAL  
**Purpose:** SEO tools (experimental)  
**Status:** 🧪 Experimental  
**Size:** ~20 files

**Contents:** SEO analysis tools

**Dependencies:** None  
**Callers:** None (not wired)  
**Production Status:** 🧪 Experimental

---

## ARCHIVED — No Longer Active

### `_cleanup_trash_2026-07-28/` Directory

**Classification:** ARCHIVED  
**Purpose:** Archived trash  
**Status:** 💀 Archived  
**Size:** ~50MB

**Contents:** Old files, cleanup archive

**Dependencies:** None  
**Callers:** None  
**Production Status:** 💀 Archived

---

## TEST_ONLY — Test Infrastructure

### `tests/` Directory

**Classification:** TEST_ONLY  
**Purpose:** Test suite  
**Status:** ✅ 140+ passing  
**Size:** ~100 files

**Test Categories:**

| Category | Tests | Status |
|----------|-------|--------|
| Permission gateway | 63 | ✅ |
| Memory stores | 38 | ✅ |
| Decision engine | 112 | ✅ |
| Districts | 47 | ✅ |
| Absorbed repos | 224 | ✅ |
| Integration | 51 | ✅ |
| Smoke | 38 | ✅ |

**Key Files:**

```python
tests/test_permission_gateway.py      # Permission tests
tests/test_memory.py                  # Memory tests
tests/test_decision_engine.py         # Decision tests
tests/test_phase2_districts.py        # District tests
tests/test_postiz_absorption.py       # Postiz absorption
tests/test_openwa_absorption.py       # OpenWA absorption
tests/test_understand_anything_absorption.py  # UA absorption
```

**Dependencies:** pytest  
**Callers:** CI/CD, developers  
**Production Status:** ✅ All passing

---

## DEVELOPMENT_ONLY — Development Tools

### `scripts/` Directory

**Classification:** DEVELOPMENT_ONLY  
**Purpose:** Development and operational scripts  
**Status:** ✅ Production-ready  
**Size:** ~100 scripts

**Key Scripts:**

```python
scripts/train_intent_real.py          # LoRA training
scripts/auto_retrain_intent.py        # Automated retraining
scripts/calibrate_intent_threshold.py # Threshold calibration
scripts/diag_tier6.py                 # Integration test
scripts/smoke_test.py                 # Smoke test
scripts/integration_check.py          # Integration check
scripts/build_golden_dataset.py       # Dataset builder
scripts/convert_to_district_only.py   # Dataset converter
scripts/augment_intent_dataset.py     # Dataset augmentation
scripts/integrate_intent_qwen3.py     # Governor integration
scripts/execute_intent_pipeline.py    # Master pipeline
```

**Dependencies:** `core/`  
**Callers:** Developers, CI/CD  
**Production Status:** ✅ Production-ready

---

## UNKNOWN — Cannot Classify

Files that cannot be clearly classified should be marked as UNKNOWN and investigated further.

---

## Integration Boundaries

### VECTOR → Vendored

```
VECTOR_CORE
    ↓
ponytail/ (vendored decision ladder)
    ↓
core/inference/ponytail_guard.py (integration point)
```

### VECTOR → Third-Party

```
VECTOR_CORE
    ↓
node_modules/ (npm packages)
pip dependencies (Python packages)
    ↓
External APIs (Anthropic, OpenAI, etc.)
```

### VECTOR → Generated

```
VECTOR_CORE
    ↓
__pycache__/ (auto-generated)
renders/ (content generation)
graphify-out/ (knowledge graph)
```

---

## Security Implications

### Vendored Code
- `ponytail/` — Trusted, minimal attack surface
- `.claude/` — Trusted, Claude Code official

### Third-Party Code
- `node_modules/` — Large attack surface, needs audit
- pip dependencies — Large attack surface, needs audit
- External APIs — Network attack surface, needs authentication

### Generated Code
- `__pycache__/` — Low risk, auto-generated
- `renders/` — Medium risk, user content
- `graphify-out/` — Low risk, generated data

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `02_REPOSITORY_INVENTORY.md` — Directory structure
- `04_RUNTIME_AND_BOOT.md` — Startup sequence
- `34_CAPABILITY_MATRIX.md` — What VECTOR can do
- `35_REACHABILITY_MATRIX.md` — What is actually wired

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
