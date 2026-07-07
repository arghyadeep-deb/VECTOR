---
name: vector-inference-routing
description: Load when working on how VECTOR chooses LLM providers/models — the free-tier catalog, quota, domain chains, the paid-model guardrail, or debugging "wrong model / 429 / paid model got called". Triggers: "provider", "model routing", "which model", "quota", "429", "catalog", "domain chain", "cloud vs local", "free tier".
---

# VECTOR Inference Routing

How VECTOR picks LLM providers and models. This is a load-bearing, VECTOR-unique
subsystem. Ground truth 2026-07-07.

## When NOT to use this skill
For general config use `vector-config-and-flags`; for the architecture rationale
use `vector-architecture-contract`.

## The policy: cloud-PRIMARY, ollama-terminal
Owner has NO paid OpenAI/Anthropic keys — **free tiers only**. All LLM calls go
through `core/inference/provider_client.py`. Priority per call is set by
`core/inference/route_policy.py::decide_route()`:
- SENSITIVE (security/privacy district, RED tier, secret-looking prompt) →
  **local Ollama ONLY** (non-negotiable gate).
- simple/medium → load-balanced free cloud, then ollama.
- heavy → premium-quality free providers first (github_models gpt-5/o3,
  cerebras zai-glm-4.7 355B), then ollama.
- cloud budget exhausted → ollama-only.

## The catalog (owner-editable, no code change)
`core/inference/model_catalog.yaml` — per provider: free models, capability
tiers (rank 1 = best), free-tier limits; plus `domains:` = per-work-domain
fallback chains. Loader `core/inference/model_catalog.py`
(`select_model(slug,tier)`, `is_model_allowed`, `chain_for_domain`). 13
providers: groq, cerebras, cloudflare, opencode_zen, openrouter, mistral,
github_models, nvidia, zai, gemini, llm7, cohere, deepseek. Edit the YAML to
add models / fix limits.

## The three guardrails (do not weaken)
1. **Paid-model whitelist:** `opencode_zen` and `zai` keys can reach PAID models
   (owner card on file). Their `LLMProvider.locked_models=True` and
   `provider_client._enforce_whitelist` CLAMP every call to the free whitelist —
   a paid model is NEVER sent, even via explicit `model=` or a model_pool entry.
   VERIFIED: forcing `claude-opus-4-8` on opencode_zen → served deepseek-v4-flash-free.
   `openrouter` default routing is gated to `:free` models.
2. **Soft quota ledger** (`core/inference/quota_ledger.py`,
   `~/.vector_ca/metering/provider_quota.json`): per-provider/model UTC-day
   usage; at >=90% of a free limit the provider is DEPRIORITIZED (moved after
   fresh options, before ollama) — never hard-blocked. Groq=req/day,
   Cerebras=tok/day, Cloudflare=neurons, Mistral=per-minute.
3. **Sensitivity gate** — see policy above; secret-looking prompts never leave
   the machine.

## Domain routing (district agents)
`vectorcode_llm.chat(domain="coding.review")` (or role→domain default) routes
via `model="domain:<name>"` — a model_pool logical model expanding to the chain
(3-4 cloud + ollama terminal). 16 domains (content.script, coding.generation/
review/architecture, orchestration, agentic.loop, research, vision,
multilingual.indic, security[local_only], etc.). Kill-switch
`VECTOR_DOMAIN_ROUTING=0`. Every chain ends on ollama → never crashes.

## Common traps (see also vector-debugging-playbook)
- Local model name (vector-focus, qwen3:14b) sent to cloud → 404. Fixed by
  `_model_for_provider` clamping to the provider's own default.
- Thinking models return empty content on short prompts → counted as failure,
  next provider tried. Use `think=False` + `num_predict` cap for classification.
- Gemini 2.0-flash/2.5-pro have `free_tier limit=0` on owner key → catalog uses
  2.5-flash/flash-lite only.
- First `domain:` call in a fresh process: catalog must load to register domain
  pools — `provider_client` triggers `get_catalog()` when model startswith "domain:".

## Provenance and maintenance
Dated 2026-07-07. Re-verify catalog: `python core/inference/model_catalog.py`.
Re-verify a live route: `python -c "import asyncio; from core.inference.provider_client import get_client; print(asyncio.run(get_client().chat([{'role':'user','content':'hi'}], tier='fast')).provider)"`.
Working providers (2026-07-02): groq, mistral, openrouter, nvidia, github_models,
cerebras, opencode_zen, zai(flash). Blocked: gemini(quota), deepseek/zai-paid(balance), cohere(trial).
