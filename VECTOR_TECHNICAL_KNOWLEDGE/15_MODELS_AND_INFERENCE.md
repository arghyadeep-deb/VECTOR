# Models and Inference

**Purpose:** All 27 model providers, routing logic, budget tracking  
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR integrates 27 LLM providers with intelligent routing based on complexity, cost, and domain. Cloud providers are primary for quality, Ollama is terminal fallback.

**Key Properties:**
- **27 providers** — Anthropic, OpenAI, Gemini, Groq, DeepSeek, etc.
- **Intelligent routing** — complexity-based provider selection
- **Budget tracking** — free-tier quota management
- **Domain routing** — work-specific model chains
- **Hard whitelist** — paid models never called at runtime

**Files:**
- `core/inference/provider_client.py` (~600 lines)
- `core/inference/llm_providers.py` (~800 lines)
- `core/inference/model_catalog.yaml`
- `core/inference/quota_ledger.py` (~200 lines)

**Status:** ✅ IMPLEMENTED, production-reachable

---

## Provider List

### 27 Providers

**File:** `core/inference/llm_providers.py`  
**Status:** ✅ IMPLEMENTED

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

---

## Routing Logic

### Provider Client

**File:** `core/inference/provider_client.py`  
**Status:** ✅ IMPLEMENTED

```python
async def chat(messages: list, model: str = None, domain: str = None):
    """Call LLM with routing."""
    
    # 1. Inject context (RULE 1)
    from core.loop.context_engine import context_engine
    hydration = await context_engine.session_hydration_prompt(domain=domain)
    
    messages_with_context = [
        {"role": "system", "content": hydration},
        *messages
    ]
    
    # 2. Determine provider
    provider = await _select_provider(model, domain)
    
    # 3. Check budget
    if quota_ledger.is_near_limit(provider):
        provider = "ollama"  # fallback
    
    # 4. Execute
    response = await _call_provider(provider, messages_with_context, model)
    
    return response

async def _select_provider(model: str, domain: str) -> str:
    """Select provider based on model and domain."""
    
    # Domain routing
    if domain:
        provider = domain_router.route(domain)
        if provider:
            return provider
    
    # Model pool routing
    if model and model.startswith("domain:"):
        provider = model_pool.resolve(model)
        if provider:
            return provider
    
    # Complexity-based routing
    complexity = estimate_complexity(messages)
    
    if complexity == "simple":
        return select_free_tier()
    elif complexity == "medium":
        return select_balanced()
    else:  # heavy
        return select_premium()

def estimate_complexity(messages: list) -> str:
    """Estimate message complexity."""
    total_length = sum(len(m.get("content", "")) for m in messages)
    
    if total_length < 500:
        return "simple"
    elif total_length < 2000:
        return "medium"
    else:
        return "heavy"

def select_free_tier() -> str:
    """Select free-tier provider."""
    # Priority: GitHub Models → Cerebras → Cloudflare → Ollama
    free_providers = ["github", "cerebras", "cloudflare", "ollama"]
    
    for provider in free_providers:
        if not quota_ledger.is_near_limit(provider):
            return provider
    
    return "ollama"  # terminal fallback

def select_balanced() -> str:
    """Select balanced provider."""
    # Priority: Groq → DeepSeek → Mistral → Ollama
    balanced_providers = ["groq", "deepseek", "mistral", "ollama"]
    
    for provider in balanced_providers:
        if not quota_ledger.is_near_limit(provider):
            return provider
    
    return "ollama"

def select_premium() -> str:
    """Select premium provider."""
    # Priority: Anthropic → OpenAI → Gemini → Ollama
    # NOTE: Paid providers not available at runtime (owner decision)
    # Fallback to best free-tier
    return select_free_tier()
```

---

## Model Catalog

### YAML Catalog

**File:** `core/inference/model_catalog.yaml`  
**Status:** ✅ IMPLEMENTED

```yaml
providers:
  github:
    free_models:
      - gpt-5
      - o3
    limits:
      requests_per_day: 100
  
  cerebras:
    free_models:
      - zai-glm-4.7
    limits:
      tokens_per_day: 100000
  
  cloudflare:
    free_models:
      - kimi-k2.7-code
    limits:
      neurons_per_day: 10000
  
  ollama:
    models:
      - vector-focus
      - vector-coder
      - vector-reasoning
      - vector-deep
      - vector-chairman
```

---

## Budget Tracking

### Quota Ledger

**File:** `core/inference/quota_ledger.py`  
**Status:** ✅ IMPLEMENTED

```python
class QuotaLedger:
    """Track free-tier quota usage."""
    
    def __init__(self):
        self.usage = {}  # provider → {date → count}
        self._load()
    
    def is_near_limit(self, provider: str, threshold: float = 0.9) -> bool:
        """Check if provider is near limit."""
        limit = self._get_limit(provider)
        if not limit:
            return False
        
        today = datetime.now().strftime("%Y-%m-%d")
        used = self.usage.get(provider, {}).get(today, 0)
        
        return used >= limit * threshold
    
    def record_usage(self, provider: str, amount: int = 1):
        """Record usage."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if provider not in self.usage:
            self.usage[provider] = {}
        
        if today not in self.usage[provider]:
            self.usage[provider][today] = 0
        
        self.usage[provider][today] += amount
        
        self._save()
```

---

## Hard Whitelist

### Paid Model Guardrail

**File:** `core/inference/provider_client.py`  
**Status:** ✅ IMPLEMENTED

```python
def _enforce_whitelist(self, provider: str, model: str) -> str:
    """Enforce free-model whitelist."""
    
    # opencode_zen and zai keys can reach paid models
    # but are hard-clamped to free whitelist
    
    if provider in ["opencode_zen", "zai"]:
        free_models = ["gpt-5", "o3", "claude-sonnet", "gemini-2.5-pro"]
        
        if model not in free_models:
            logger.warning(f"[VECTOR][inference] Paid model blocked: {model}")
            return "vector-focus"  # fallback to local
    
    return model
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Provider selection | <1ms | Memory access |
| LLM call (cloud) | 1-10s | API latency |
| LLM call (Ollama) | 0.5-5s | GPU inference |
| Budget check | <1ms | Memory access |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `06_CONTEXT_ENGINE.md` — Context injection
- `09_GOVERNOR_AND_PERMISSIONS.md` — Intent classification

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
