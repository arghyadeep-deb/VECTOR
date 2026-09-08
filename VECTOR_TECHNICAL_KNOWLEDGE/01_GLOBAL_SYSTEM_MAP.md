# VECTOR Global System Map

**Purpose:** What VECTOR is and how all major systems connect  
**Level:** System Level (Level 1)

---

## What VECTOR Is

**VECTOR** = Virtual Entity for Cognitive Tasks & Operational Reasoning

A **Darwinian multi-agent autonomous AI system** running 24/7 on local hardware (Legion Pro 5, RTX 5070 Ti). VECTOR governs a "city" of 133+ agents across 33+ districts that evolve, die, and are reborn.

**Architectural Philosophy:**
- **Local-first:** All critical operations run locally, cloud is fallback
- **Darwinian:** Agents have HP (0-1000), die at 0, ghost memory preserved
- **Autonomous:** Runs continuously without human intervention
- **Multi-agent:** 133+ specialized agents across 33+ districts
- **Governed:** High-stakes decisions require council approval (HP > 700)
- **Memory-rich:** Multiple memory systems (episodic, semantic, policy, reasoning)
- **Model-flexible:** 27 LLM providers, local Ollama models, cloud fallback

**Owner:** Arghyadeep Deb  
**Runtime:** 24/7 autonomous operation on Legion Pro 5 (RTX 5070 Ti, 32GB RAM)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ USER / EXTERNAL INPUT                                       │
│ (Telegram, WhatsApp, Discord, Email, Voice, API, Web)       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ INTERFACE LAYER                                             │
│ - FastAPI server (port 8000)                                │
│ - MCP server (port 9001)                                    │
│ - Communication adapters (30+ platforms)                    │
│ - Voice pipeline (STT/TTS)                                  │
│ - Web UI (HUD, dashboard)                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ AUTONOMOUS LOOP (never stops)                               │
│ observe(0.5s) → think(event-driven) → act(permission-gated) │
│ → reflect(2AM)                                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ INTELLIGENCE STACK                                          │
│ 1. context_engine → unified world state                     │
│ 2. goal_system → 3 horizons (LONG/MID/SHORT)                │
│ 3. decision_engine → 5-factor scoring                       │
│ 4. policy.py → get_score() BEFORE, update AFTER             │
│ 5. permission_gateway → GREEN/YELLOW/RED                    │
│ 6. reasoning_memory → all chains stored                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ GOVERNOR / ROUTING                                          │
│ - Intent classification (regex → embedding → LLM)           │
│ - District routing (33+ districts)                          │
│ - Agent selection (HP-based, council for high-stakes)       │
│ - Permission check (GREEN/YELLOW/RED)                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ VECTOR CITY — 33+ DISTRICTS                                 │
│ governance/ security/ coding/ time_calendar/ communications/│
│ memory_curator/ research/ intelligence/ skills/ languages/  │
│ interview_prep/ learning/ finance/ health/ reflection/      │
│ startups/ investment/ content/ agency/ karpathy_lab/        │
│ projects/ relationships/ privacy/ pattern_detective/        │
│ news_trends/ calls/ ops/ data_analytics/ personal_growth/   │
│ documentation/ qa/ chief_of_staff/ marketing/ design/ ...   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ AGENTS (133+ files)                                         │
│ - AgentBase class with HP system                            │
│ - Darwinian lifecycle (birth, life, death, ghost, rebirth)  │
│ - HP > 800 → Claude Sonnet access                           │
│ - HP > 700 → Council voting rights                          │
│ - HP = 0 → death + ghost memory preserved                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ MODEL INFERENCE (27 providers)                              │
│ Cloud (primary): Anthropic, OpenAI, Gemini, Groq, ...       │
│ Local (fallback): Ollama (qwen3:8b, qwen3:14b, gemma4, ...) │
│ Routing: provider_client.py → decide_route()                │
│ Budget: quota_ledger.py tracks free-tier usage              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ TOOLS (100+)                                                │
│ Filesystem, shell, browser, web, coding, GitHub, databases, │
│ APIs, communication, email, calendar, social media,         │
│ phone/ADB, finance, media, system control, automation       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ PERMISSION GATEWAY                                          │
│ GREEN → execute immediately                                 │
│ YELLOW → log + execute (owner notified)                     │
│ RED → require owner approval (Pushover)                     │
│ FORBIDDEN → never execute                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ EXECUTION                                                   │
│ - Tool calls                                                │
│ - API calls                                                 │
│ - File operations                                           │
│ - Shell commands                                            │
│ - External effects                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ MEMORY SYSTEMS                                              │
│ Episodic (SQLite FTS5) → events, conversations              │
│ Semantic (LightRAG) → knowledge, facts                      │
│ Policy (EMA) → learned behavior                             │
│ Reasoning → all decision chains                             │
│ Ghost → deceased agent memory                               │
│ Obsidian → human-readable notes                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ REFLECTION (2AM daily)                                      │
│ - Review day's events                                       │
│ - Consolidate memories                                      │
│ - Extract patterns                                          │
│ - Update policy                                             │
│ - Write to Obsidian                                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ NEXT CYCLE                                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Subsystems

### 1. Autonomous Loop
**File:** `core/loop/autonomous_loop.py`

**Purpose:** The heartbeat of VECTOR. Never stops.

**Components:**
- `observe_loop()` — 0.5s cadence, senses environment
- `think_loop()` — event-driven, makes decisions
- `act_loop()` — permission-gated execution
- `reflect_loop()` — 2AM daily review

**Key Properties:**
- Never crashes (all exceptions caught)
- Graceful shutdown (SIGINT/SIGTERM handling)
- Task tracking (active_task_count)
- Restart recovery

**Status:** ✅ IMPLEMENTED, production-reachable

---

### 2. Context Engine
**File:** `core/loop/context_engine.py`

**Purpose:** Unified world state.Injected into every LLM call.

**What it knows:**
- Device state (battery, CPU, GPU, memory)
- Environment state (time, location, weather)
- Session state (conversation history, active goals)
- Persistent state (memories, policies)
- External state (API status, network)
- Domain state (district-specific context)

**Key Function:** `session_hydration_prompt()` — called BEFORE every LLM call

**Status:** ✅ IMPLEMENTED, mandatory (RULE 1)

---

### 3. Goal System
**File:** `core/brain/goal_system.py`

**Purpose:** 3-horizon goal hierarchy

**Horizons:**
- LONG (90 days) — strategic objectives
- MID (30 days) — tactical objectives
- SHORT (7 days) — immediate actions

**Features:**
- Pre-seeded goals (5 initial)
- Goal expiry (auto-prune stale goals)
- Progress tracking
- Action generation

**Status:** ✅ IMPLEMENTED

---

### 4. Decision Engine
**File:** `core/loop/decision_engine.py`

**Purpose:** 5-factor candidate scoring

**Formula:**
```
total_score = 
  goal_alignment(30%) + 
  confidence(25%) + 
  policy(20%) + 
  urgency(15%) + 
  timing(10%) - 
  cost(5%)
```

**Process:**
1. Generate candidates (from goals)
2. Score each candidate
3. Select winner
4. Execute or defer

**Status:** ✅ IMPLEMENTED

---

### 5. Policy Memory
**File:** `core/memory/policy.py`

**Purpose:** Learned behavior via EMA (Exponential Moving Average)

**Key Functions:**
- `get_score()` — called BEFORE every decision
- `update_from_outcome()` — called AFTER every action

**Status:** ✅ IMPLEMENTED (RULE 7)

---

### 6. Permission Gateway
**File:** `core/loop/permission_gateway.py`

**Purpose:** GREEN/YELLOW/RED permission system

**Tiers:**
- GREEN → execute immediately
- YELLOW → log + execute (owner notified)
- RED → require owner approval (Pushover)
- FORBIDDEN → never execute

**Owner Approval:** Pushover (owner-phone), replaced HumanLayer (2026-06-19)

**Status:** ✅ IMPLEMENTED (RULE 3)

---

### 7. Governor / Routing
**File:** `core/city/governor.py`

**Purpose:** Intent classification + district routing

**Pipeline:**
1. Regex pre-classifier (35 patterns, 95% confidence)
2. Embedding similarity (nomic-embed-text, 768-dim, 100-300ms)
3. Qwen3 8B classifier (LoRA fine-tuned, <100ms, 95-97% expected)
4. LLM fallback (flexible, 3-12s)

**Districts:** 33+ districts, 180 routing rules

**Status:** ✅ IMPLEMENTED (Phase 1 working, Phase 2 training)

---

### 8. Agent System
**Files:** 
- `core/city/agent_base.py` — base class
- `core/city/agent_registry.py` — registry
- `districts/*/` — 133+ agent files

**HP System:**
- 0-1000 HP
- +100 HP: user approved output
- +50 HP: task completed well
- +30 HP: output used by VECTOR
- +40 HP: council voted for them
- -30 HP: task failed
- -50 HP: output ignored 3x
- -100 HP: critical error
- 0 HP: death + ghost memory

**Thresholds:**
- >800 HP → Claude Sonnet access
- >700 HP → Council seat
- 600-800 → kimi-k2.6 access
- 0 HP → death

**Status:** ✅ IMPLEMENTED

---

### 9. Memory Systems
**Files:**
- `core/memory/episodic.py` — SQLite FTS5
- `core/memory/policy.py` — EMA
- `core/memory/reasoning_memory.py` — reasoning chains
- `core/memory/obsidian_sync.py` — Obsidian integration
- `core/memory/light_rag.py` — semantic memory (upgraded)

**Types:**
- Episodic: events, conversations
- Semantic: knowledge, facts (LightRAG)
- Policy: learned behavior (EMA)
- Reasoning: all decision chains
- Ghost: deceased agent memory
- Obsidian: human-readable notes

**Status:** ✅ IMPLEMENTED

---

### 10. Model Inference
**Files:**
- `core/inference/provider_client.py` — routing
- `core/inference/ollama_safe.py` — Ollama
- `core/inference/llm_providers.py` — 27 providers

**Providers:** 27 (Anthropic, OpenAI, Gemini, Groq, DeepSeek, Mistral, OpenRouter, Together, Fireworks, Perplexity, Cohere, Azure, Cloudflare, vLLM, HF, Replicate, Anyscale, Cerebras, SambaNova, NVIDIA, Moonshot, Zhipu, Baidu, Yi, LMStudio, Ollama, +1)

**Routing:**
- Cloud (primary): free-tier pooled keys
- Local (fallback): Ollama
- Sensitive: local ONLY

**Budget Tracking:** `core/inference/quota_ledger.py`

**Status:** ✅ IMPLEMENTED

---

### 11. Tool System
**Files:** `tools/`, `core/mcp_tools/`

**Categories:**
- Filesystem, shell, browser, web
- Coding, GitHub
- Databases, APIs
- Communication, email, calendar
- Social media, phone/ADB
- Finance, media
- System control, automation

**Count:** 100+ tools

**Safety:** All dangerous tools go through PermissionGateway

**Status:** ✅ IMPLEMENTED

---

### 12. Communications
**Files:** `vectorcode/src/channels/`, `districts/communications/`

**Platforms:** 30+ (Telegram, WhatsApp, Discord, Slack, Gmail, Signal, etc.)

**Gateway:** VectorCode (replaced Hermes, 2026-06-19)

**Status:** ✅ IMPLEMENTED

---

### 13. Voice Pipeline
**Files:** `core/voice/`

**Components:**
- STT: Whisper (local)
- TTS: Kokoro (primary), pyttsx3 (fallback)
- Wake word: "Hey VECTOR" (custom training needed)
- Language detection: HI/BN/AS/JA/EN auto-switch

**Status:** ⚠️ PARTIAL (Kokoro model needs download, wake word training pending)

---

### 14. Reflection
**Files:** `districts/reflection/`, `core/loop/autonomous_loop.py`

**Schedule:** 2AM daily

**Process:**
- Review day's events
- Consolidate memories
- Extract patterns
- Update policy
- Write to Obsidian

**Status:** ✅ IMPLEMENTED

---

### 15. Cloud Deployment
**Files:** `api/`, `cloud/`, `deploy/`

**Components:**
- Cloudflare Worker API (LIVE)
- Cloudflare D1/R2/KV (PROVISIONED)
- Supabase cloud DB (CONFIGURED)
- Fly.io (NOT DEPLOYED — owner declined, requires card)

**Status:** ✅ DEPLOYED (Cloudflare), ❌ Fly.io (not deployed)

---

## Three-Layer System

```
Layer A — Devices:
  Legion Pro 5 (primary) | Old Android Termux (ambient) | Daily phone (alerts)

Layer B — Cloud:
  Fly.io (3 VMs, NOT DEPLOYED) | Cloudflare Workers+D1+R2+KV | Supabase | Turso

Layer C — APIs:
  Claude Sonnet (Pro chat, build sessions) | Gemini 2.5 Pro (free) | Ollama local
```

---

## Intelligence Stack (Build Order)

```
1. context_engine.py     — unified world state, session_hydration_prompt() BEFORE EVERY LLM CALL
2. goal_system.py        — 3 horizons: LONG/MID/SHORT, pre-seeded goals
3. decision_engine.py    — 4 candidates scored: goal_alignment(30%) + confidence(25%) + policy(20%) + urgency(15%) + timing(10%) - cost(5%)
4. policy.py             — get_score() BEFORE deciding, update_from_outcome() AFTER every action
5. permission_gateway.py — GREEN/YELLOW/RED, LLM has ZERO direct access, ever
6. reasoning_memory.py   — all thought chains stored, becomes LLM training data
```

**Status:** ✅ ALL IMPLEMENTED

---

## VECTOR Gaps (Built After Phase 1)

```
Gap 1: synthesis_bridge.py    — cross-domain pattern detection every 30min ✅ BUILT
Gap 2: red_team_agent.py      — adversarial review before RED actions ✅ BUILT
Gap 3: epistemic_tracker.py   — knows what it doesn't know ✅ BUILT
Gap 4: counterfactual.py      — learns from rejected decisions ✅ BUILT (2026-06-11)
Gap 5: hypothesis_engine.py   — proactive insights ✅ BUILT
Gap 6: causal_graph.py        — causal reasoning ✅ BUILT (SQLite-backed, 2026-05-30)
Gap 7: person_model.py        — theory of mind per person ✅ BUILT
Gap 8: meta_cognition.py      — monthly bias detection ✅ BUILT
```

**Status:** ✅ ALL GAPS NOW BUILT (corrected from earlier documentation)

---

## Key Rules (Non-Negotiable)

1. **`context_engine.session_hydration_prompt()` before EVERY LLM call** — no exceptions
2. **Autonomous loop must never die** — every coroutine catches all exceptions, restarts
3. **Permission Gateway is the ONLY path to real-world actions** — LLM proposes, Gateway executes
4. **`policy.py` wired both ways** — `get_score()` BEFORE every decision, `update_from_outcome()` AFTER
5. **Local-first inference** — cloud keys are primary for quality, Ollama is the terminal fallback
6. **No `print()` in production** — `loguru` everywhere
7. **SQLCipher for main DB** — always go through `core.memory.episodic.get_db_connection()`
8. **Never use `requests`, `flask`, `threading`, `pickle`** — use `httpx`, `fastapi`, `asyncio`, `json/msgpack`
9. **`core/config.py` CONFIG dict for all configurable values** — never hardcode
10. **Free-tier only at runtime** — no paid Anthropic/OpenAI keys at runtime (owner decision 2026-07-08)

---

## What VECTOR Can Do TODAY

### ✅ FULLY OPERATIONAL
- Autonomous loop (24/7 operation)
- 33+ districts with 133+ agents
- 27 LLM providers (cloud + local)
- Intent classification (regex + embedding, 90% accuracy)
- Memory systems (episodic, semantic, policy, reasoning)
- Permission gateway (GREEN/YELLOW/RED)
- Governor routing (district selection)
- Reflection (2AM daily)
- Cloud deployment (Cloudflare Worker API)
- Communication adapters (30+ platforms)
- Tool system (100+ tools)
- HP system (agent lifecycle)
- Goal system (3 horizons)
- Decision engine (5-factor scoring)
- Context engine (world state)

### ⚠️ PARTIALLY OPERATIONAL
- Voice pipeline (needs Kokoro model download, wake word training)
- Face recognition (needs `pip install face-recognition mediapipe`)
- Phase 2 intent classification (training in progress, 95-97% expected)

### ❌ NOT OPERATIONAL
- Fly.io deployment (owner declined, requires card)
- Next.js dashboard (HUD frontend serves the role)
- Full voice activation (needs model download + training)

---

## What VECTOR Cannot Do (Yet)

- **Move real money** (investment district is ANALYSIS ONLY, never trades)
- **Deploy to production** without owner approval (PermissionGateway RED tier)
- **Access paid models** at runtime (hard-clamped to free-tier whitelist)
- **Run without local hardware** (Legion Pro 5 is primary)
- **Full voice conversation** (needs Kokoro + wake word training)

---

## Architectural Philosophy

1. **Local-first:** All critical operations run locally, cloud is fallback
2. **Darwinian:** Agents evolve, die, and are reborn based on performance
3. **Autonomous:** Runs 24/7 without human intervention
4. **Governed:** High-stakes decisions require council approval
5. **Memory-rich:** Multiple memory systems for different purposes
6. **Model-flexible:** 27 providers, automatic routing
7. **Safety-first:** Permission gateway prevents unauthorized actions
8. **Observable:** Extensive logging, metrics, monitoring
9. **Resilient:** Never crashes, graceful degradation
10. **Free-tier:** No paid API keys at runtime (owner decision)

---

## Scale

- **Code:** ~1.6 million lines
- **Python files:** ~7,000
- **Districts:** 33+
- **Agents:** 133+
- **Tools:** 100+
- **LLM providers:** 27
- **Communication platforms:** 30+
- **Tests:** 140+ passing
- **Skills:** 100+
- **Commands:** 31

---

## Cross-References

See:
- `04_RUNTIME_AND_BOOT.md` — startup sequence
- `05_AUTONOMOUS_LOOP.md` — loop architecture
- `10_AGENT_ARCHITECTURE.md` — agent system
- `11_VECTOR_CITY.md` — districts
- `13_MEMORY_ARCHITECTURE.md` — memory systems
- `15_MODELS_AND_INFERENCE.md` — model routing
- `34_CAPABILITY_MATRIX.md` — what VECTOR can do
- `39_AUTONOMY_ASSESSMENT.md` — autonomy level

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
