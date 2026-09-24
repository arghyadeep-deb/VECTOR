# Models & Routing

## Hardware
```
GPU:  RTX 5070 Ti 12GB VRAM
RAM:  32GB DDR5
CPU:  Intel Core Ultra 9 275HX (24 cores)
```

## Ollama Environment (already set)
```
OLLAMA_MAX_LOADED_MODELS=1     ← NEVER load 2 simultaneously (KV cache overflow)
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
OLLAMA_KEEP_ALIVE=30m
OLLAMA_HOST=127.0.0.1:11434
```

## Installed Models
```
vector-ambient      (gemma4:e2b)   — ambient JSON classifier, old phone
vector-focus        (gemma4:e4b)   — main voice + multimodal, permanent VRAM
vector-multilingual (qwen3:14b)    — HI/BN/AS/JA/EN auto-switch
vector-reasoning    (qwen3:14b)    — step-by-step, council member
vector-coder        (qwen3:14b)    — 2-mode: personal stack / SaaS stack
vector-deep        (gemma4:26b)    — overnight analysis, 65K context, document reading
vector-chairman    (gemma4:31b)    — council chairman, private reasoning, training data gen
nomic-embed-text                   — vector embeddings
qwen3:8b, qwen3:14b                — base models
qwen3:30b-a3b (MoE, 3B active)     — fast large-context reasoning, low VRAM for 30B class
gemma4:e2b, gemma4:e4b             — base models
gemma4:26b (MoE, 4B active)        — deep tasks, hybrid mode
gemma4:31b (Dense)                 — slow deep tasks, hybrid mode
deepseek-r1:14b                    — chain-of-thought reasoning, R1 style
devstral:24b                       — code-specialist (Mistral devstral), refactor + review
mistral-small3.1:latest            — fast general-purpose, low-latency fallback
```

## Model Routing (use this decision tree)
```
Real-time conversation   → vector-focus (permanent VRAM, 40+ tok/s)
Hindi/Bengali/Assamese  → vector-multilingual (load on demand)
Code generation         → vector-coder OR devstral:24b (load on demand)
Code review / refactor  → devstral:24b (code-specialist, 24B quality)
Chain-of-thought tasks  → deepseek-r1:14b (R1-style reasoning traces)
Fast general fallback   → mistral-small3.1 (low latency, broad knowledge)
Large-context reasoning → qwen3:30b-a3b (30B class, only 3B active VRAM)
Council/reasoning       → vector-reasoning + vector-r1 + vector-dev (chairman: vector-chairman)
Deep overnight tasks    → gemma4:26b or gemma4:31b (hybrid, 3-6 tok/s)
70B tasks               → AirLLM (streams layers, slow but works)
YOUR build sessions     → Claude Sonnet 4.6 via Pro plan chat (unlimited)
YOUR complex planning   → Claude Opus 4.6 via Pro plan chat
```

## VECTOR Runtime Rule (updated 2026-07-02 — owner decision)
> CORRECTION 2026-07-08: "premium cloud (anthropic/openai)" below is ASPIRATIONAL,
> not current. The owner has NO paid `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` set
> (verified 2026-07-08) — runtime is FREE-TIER ONLY across 13 providers (GitHub
> Models gives gpt-5/o3 free; Cerebras gives zai-glm-4.7 free). opencode_zen/zai
> keys can technically reach paid models but are hard-clamped to the free
> whitelist. Do NOT stand up paid Anthropic/OpenAI routing. See the
> `vector-inference-routing` skill for the authoritative current state.
```
CLOUD API KEYS are PRIMARY — Ollama is the FALLBACK.
route_policy.decide_route() orders providers per call:
  - simple/medium  → load-balanced pooled cloud keys, then ollama
  - heavy          → premium cloud (anthropic/openai/deepseek), then ollama
  - SENSITIVE      → local ONLY, always (security/privacy districts, RED tier,
                     secret-looking prompts) — this gate is non-negotiable
  - cloud budget exhausted (budget_gate) → automatic ollama-only

Local stays primary ONLY where it must:
  - voice conversation streaming (sentence-TTS needs token streaming)
  - anything matching the sensitivity gate above

Set API keys in .env to activate cloud providers:
  ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, GROQ_API_KEY,
  DEEPSEEK_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, etc.
  (.env is auto-loaded by core/inference/key_pool.py — keys do NOT need
  to be system-wide env vars.)

Use core/inference/provider_client.py for all LLM calls — never raw httpx,
and prefer it over direct ollama_safe unless latency/streaming demands local.
Budget tracked per-agent via core/metering/budget_meter.py.
```

## Multi-Model Catalog + Soft Quota (added 2026-07-02)
```
core/inference/model_catalog.yaml — OWNER-EDITABLE catalog of every provider's
FREE models + free-tier limits + capability tiers. Edit it to add/remove
models or fix limits; NO code change needed (core/inference/model_catalog.py
reloads it; hardcoded fallback keeps the guardrails if PyYAML is missing).

Per-provider-per-tier model selection: when a tier hits a provider, the
catalog picks that provider's BEST model for the tier (rank 1) — e.g. coding
tier + cloudflare → Kimi K2.7 Code, not the generic default. Requested-model
passthrough and model_pool logical aliases still work.

Soft daily quota (core/inference/quota_ledger.py →
~/.vector_ca/metering/provider_quota.json): tracks approx per-provider/model
usage per UTC day. At >= 90% of any free-tier limit the provider/model is
DEPRIORITIZED (moved after fresh cloud options, before the ollama terminal) —
never hard-blocked. Resets at UTC midnight. Groq=req/day, Cerebras=tok/day,
Cloudflare=neurons/day, Mistral=per-minute; unknown limits = never deprioritized.

HARD WHITELIST (paid-model guardrail): opencode_zen and zai keys can reach
PAID models (owner card on file). Their LLMProvider.locked_models=True and
provider_client._enforce_whitelist CLAMP every call to the free-model
whitelist — a paid model is NEVER sent, even via explicit model= or a
model_pool entry. openrouter default routing is gated to ':free' models.

DOMAIN ALIGNMENT (vectorcode_llm.chat domain= / model="domain:<name>"):
each work domain (content.script, coding.review, coding.architecture,
orchestration, agentic.loop, research, vision, multilingual.indic, security,
...) is a 3-4 model cloud chain + ollama terminal in model_catalog.yaml
domains:, registered as model_pool "domain:<name>". District agents pass
domain= (or a local role that maps to one via _ROLE_TO_DOMAIN). security
domain is local_only. Kill-switch: VECTOR_DOMAIN_ROUTING=0. Never crashes —
every chain terminates on ollama.
```

## Custom LLM Plan (OpenMythos RDT)
```
Week 7-8:  nanoGPT on your data (learning exercise)
Month 2:   LoRA fine-tune Qwen3 4B on RTX 5070 Ti (1-2 hours local)
Month 2-3: vector-chairman → Council Chairman (replaces qwen3:30b-a3b as chairman)
Month 4-6: Pre-train OpenMythos 200M from scratch (weekend on Legion)
Year 2:    Full custom LLM trained on VECTOR's reasoning chains

WARNING: Verify OpenMythos has working train.py before Month 2.
Fallback:  karpathy/nanoGPT + LoRA on Colab (proven, no risk)
```

## Coder Model — Two Modes
```
MODE 1 (Personal/Skill Projects):
  Fixed stack: Python, FastAPI, LangGraph, LangChain, PyTorch, SQLite,
               RAG, MCP, Streamlit, Docker, TensorFlow, Keras, PowerBI
  Goal: resume-worthy, clean, demonstrable

MODE 2 (SaaS Products):
  Stack chosen per requirement. Analyse first.
  Defaults: FastAPI/Next.js + Supabase + Railway + Stripe + Cloudflare
  Ask: "Personal project or SaaS?" if unclear
```

## LLM Council
```
Trigger:  high-stakes decisions only (stakes = "high" or "critical")
Members:  districts/governance/llm_council.py → vector-reasoning + vector-r1 + vector-dev
          core/brain/council.py (RED-tier path) → ONE model in 3 roles (cautious / pragmatic / long-term), majority vote
Chairman: vector-chairman (gemma4:31b) → your fine-tuned model (Month 2); on CouncilBrain only breaks a genuine split
HP gate:  requester needs >= 700 HP (CONFIG["council"]["hp_gate"]); max 10 sessions/week
Cost:     ₹0 — fully local, no cloud APIs
Sessions: stored in reasoning_chains → LLM training data
```