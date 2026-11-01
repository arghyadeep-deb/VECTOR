"""
VECTOR LLM Provider Registry — 27 providers, fully configurable via API keys.

RULE 11 UPDATE: Ollama remains the primary runtime (free, local, private).
API key providers are now supported as fallbacks, for build sessions,
ElevenLabs content, and tasks requiring cloud-grade models.

Priority routing:
  1. Ollama (local) — always tried first for runtime tasks
  2. API key providers — used when explicitly requested or Ollama unavailable

Set API keys in .env:
  ANTHROPIC_API_KEY=...
  OPENAI_API_KEY=...
  GEMINI_API_KEY=...
  GROQ_API_KEY=...
  DEEPSEEK_API_KEY=...
  OPENROUTER_API_KEY=...
  MISTRAL_API_KEY=...
  TOGETHER_API_KEY=...
  FIREWORKS_API_KEY=...
  AZURE_OPENAI_API_KEY=...
  AZURE_OPENAI_ENDPOINT=...

Ported from the agent OS runtime/drivers/ (anthropic.rs, gemini.rs, openai.rs).
"""
from __future__ import annotations

__all__ = [
    "configured_providers",
    "get_provider",
    "list_free",
    "LLMProvider",
    "route_for_tier",
]


import os
from dataclasses import dataclass, field

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.config import CONFIG

# ── Provider dataclass ─────────────────────────────────────────────────────────

@dataclass
class LLMProvider:
    slug: str
    name: str
    base_url: str
    api_key_env: str           # env var holding the API key
    driver: str                # "openai_compat" | "anthropic" | "gemini" | "ollama"
    default_model: str
    models: list[str] = field(default_factory=list)
    free: bool = False         # True for local/no-cost providers
    context_window: int = 128_000
    supports_tools: bool = True
    supports_vision: bool = False
    supports_stream: bool = True
    rate_limit_rpm: int = 60
    pricing_per_1m: dict = field(default_factory=lambda: {"input": 0.0, "output": 0.0})
    notes: str = ""
    # HARD whitelist: only entries in `models` may EVER be sent to this
    # provider (opencode_zen/zai keys can reach PAID models — owner card on
    # file). provider_client._enforce_whitelist clamps.
    locked_models: bool = False

    @property
    def api_key(self) -> str:
        """Next key from the provider's pool (round-robin across comma-separated keys)."""
        from core.inference.key_pool import get_pool
        return get_pool(self.api_key_env).next_key()

    @property
    def is_configured(self) -> bool:
        if self.free:
            return True
        from core.inference.key_pool import get_pool
        return get_pool(self.api_key_env).has_keys()

    @property
    def effective_base_url(self) -> str:
        """Resolve env-var-based URLs (Azure)."""
        if self.base_url.startswith("$"):
            env_var = self.base_url[1:]
            return os.getenv(env_var, "") + "/openai/deployments"
        return self.base_url


# ── 27 Provider definitions ───────────────────────────────────────────────────

PROVIDERS: dict[str, LLMProvider] = {p.slug: p for p in [

    # ── Ollama (local, always free, primary runtime) ───────────────────────────
    LLMProvider(
        slug="ollama",
        name="Ollama (Local)",
        base_url="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY",       # not required
        driver="openai_compat",
        default_model="qwen3:14b",
        models=["qwen3:14b","qwen3:8b","vector-coder","deepseek-r1:14b",
                "qwen3:14b","vector-focus","vector-focus","vector-coder"],
        free=True,
        context_window=32_768,
        rate_limit_rpm=999,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Primary VECTOR runtime. All local models. Zero cost, zero latency overhead.",
    ),

    # ── Ollama Cloud (hosted big models, requires OLLAMA_API_KEY) ──────────────
    LLMProvider(
        slug="ollama_cloud",
        name="Ollama Cloud",
        base_url="https://ollama.com/v1",
        api_key_env="OLLAMA_API_KEY",
        driver="openai_compat",
        default_model="kimi-k2:cloud",
        models=["kimi-k2:cloud", "glm-4.6:cloud", "qwen3-coder:cloud"],
        free=False,
        context_window=128_000,
        rate_limit_rpm=60,
        pricing_per_1m={"input": 0.0, "output": 0.0},
        notes="Ollama-hosted cloud models. Requires OLLAMA_API_KEY (ollama.com signin).",
    ),

    # ── Anthropic (Claude) ────────────────────────────────────────────────────
    LLMProvider(
        slug="anthropic",
        name="Anthropic (Claude)",
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        driver="anthropic",
        default_model="claude-sonnet-4-6",
        models=["claude-opus-4-7","claude-sonnet-4-6","claude-haiku-4-5-20251001"],
        context_window=200_000,
        supports_vision=True,
        rate_limit_rpm=50,
        pricing_per_1m={"input":3.0,"output":15.0},
        notes="Build sessions only. claude-sonnet-4-6 = default. claude-opus-4-7 = deep reasoning.",
    ),

    # ── Google Gemini ─────────────────────────────────────────────────────────
    LLMProvider(
        slug="gemini",
        name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key_env="GEMINI_API_KEY",
        driver="gemini",
        # Probed live 2026-07-03: 2.0-flash / 2.5-pro have free_tier limit=0 on
        # this key (no free quota). Only 2.5-flash + flash-lite actually work.
        default_model="gemini-2.5-flash",
        models=["gemini-2.5-flash","gemini-2.5-flash-lite","gemini-flash-latest","gemini-flash-lite-latest"],
        context_window=1_000_000,
        supports_vision=True,
        rate_limit_rpm=60,
        free=True,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Free tier: 360M tokens/month. Set GEMINI_API_KEY from aistudio.google.com. 2.5-flash: 1M context, vision, grounding.",
    ),

    # ── OpenAI ────────────────────────────────────────────────────────────────
    LLMProvider(
        slug="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        driver="openai_compat",
        default_model="gpt-4o-mini",
        models=["gpt-4o","gpt-4o-mini","o1","o1-mini","o3-mini","gpt-4-turbo"],
        context_window=128_000,
        supports_vision=True,
        rate_limit_rpm=60,
        pricing_per_1m={"input":5.0,"output":15.0},
    ),

    # ── Groq (ultra-fast inference) ───────────────────────────────────────────
    LLMProvider(
        slug="groq",
        name="Groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        driver="openai_compat",
        default_model="openai/gpt-oss-120b",
        # Verified against GET /openai/v1/models 2026-09-25: the Llama/Mixtral/Gemma2/
        # DeepSeek-distill models were retired.
        models=["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"],
        context_window=128_000,
        rate_limit_rpm=30,
        pricing_per_1m={"input":0.59,"output":0.79},
        notes="Fastest inference. Free tier: 30 req/min. Great for summarization.",
    ),

    # ── DeepSeek ─────────────────────────────────────────────────────────────
    LLMProvider(
        slug="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        driver="openai_compat",
        # deepseek-chat/reasoner DEPRECATE 2026-07-24 (docs fetched 2026-07-02)
        default_model="deepseek-v4-flash",
        models=["deepseek-v4-flash","deepseek-v4-pro"],
        context_window=1_000_000,
        pricing_per_1m={"input":0.14,"output":0.28},
        notes="No free tier — dormant until owner tops up balance. "
              "deepseek-v4-flash-free is available FREE via opencode_zen.",
    ),

    # ── Mistral AI ────────────────────────────────────────────────────────────
    LLMProvider(
        slug="mistral",
        name="Mistral AI",
        base_url="https://api.mistral.ai/v1",
        api_key_env="MISTRAL_API_KEY",
        driver="openai_compat",
        default_model="mistral-large-latest",
        models=["mistral-large-latest","mistral-small-latest","codestral-latest",
                "open-mistral-nemo","open-codestral-mamba"],
        context_window=128_000,
        pricing_per_1m={"input":2.0,"output":6.0},
        notes="codestral-latest = best for code. European privacy compliance.",
    ),

    # ── OpenRouter (aggregator, 300+ models) ──────────────────────────────────
    LLMProvider(
        slug="openrouter",
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        driver="openai_compat",
        # Default routing = :free models only (key has paid credits — real
        # money; model_catalog allow_pattern ':free$' gates selection).
        default_model="meta-llama/llama-3.3-70b-instruct:free",
        models=[
            "meta-llama/llama-3.3-70b-instruct:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "nousresearch/hermes-3-llama-3.1-405b:free",
            "openai/gpt-oss-120b:free", "openai/gpt-oss-20b:free",
            "qwen/qwen3-coder:free", "cohere/north-mini-code:free",
            "poolside/laguna-m.1:free", "poolside/laguna-xs.2:free",
            "qwen/qwen3-next-80b-a3b-instruct:free",
            "google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free",
            "nvidia/nemotron-3-nano-30b-a3b:free",
            "nvidia/nemotron-nano-12b-v2-vl:free",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
            "nvidia/nemotron-nano-9b-v2:free",
            "nvidia/nemotron-3.5-content-safety:free",
            "meta-llama/llama-3.2-3b-instruct:free",
            "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
            "liquid/lfm-2.5-1.2b-instruct:free", "liquid/lfm-2.5-1.2b-thinking:free",
        ],
        context_window=200_000,
        pricing_per_1m={"input":0.0,"output":0.0},    # :free models
        notes="22 :free models on owner key (probed 2026-07-02; ~1000 req/day, 20/min). "
              "Paid catalog reachable but kept out of default routing.",
    ),

    # ── Together AI ───────────────────────────────────────────────────────────
    LLMProvider(
        slug="together",
        name="Together AI",
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        driver="openai_compat",
        default_model="meta-llama/Llama-3-70b-chat-hf",
        models=["meta-llama/Llama-3-70b-chat-hf","mistralai/Mixtral-8x7B-Instruct-v0.1",
                "Qwen/Qwen1.5-72B-Chat"],
        context_window=32_000,
        pricing_per_1m={"input":0.9,"output":0.9},
    ),

    # ── Fireworks AI ─────────────────────────────────────────────────────────
    LLMProvider(
        slug="fireworks",
        name="Fireworks AI",
        base_url="https://api.fireworks.ai/inference/v1",
        api_key_env="FIREWORKS_API_KEY",
        driver="openai_compat",
        default_model="accounts/fireworks/models/llama-v3p1-70b-instruct",
        models=["accounts/fireworks/models/llama-v3p1-70b-instruct",
                "accounts/fireworks/models/mixtral-8x7b-instruct",
                "accounts/fireworks/models/qwen2p5-72b-instruct"],
        context_window=128_000,
        pricing_per_1m={"input":0.9,"output":0.9},
    ),

    # ── Perplexity ────────────────────────────────────────────────────────────
    LLMProvider(
        slug="perplexity",
        name="Perplexity",
        base_url="https://api.perplexity.ai",
        api_key_env="PERPLEXITY_API_KEY",
        driver="openai_compat",
        default_model="llama-3.1-sonar-large-128k-online",
        models=["llama-3.1-sonar-large-128k-online","llama-3.1-sonar-small-128k-online"],
        context_window=128_000,
        pricing_per_1m={"input":1.0,"output":1.0},
        notes="Online models with live web search built-in.",
    ),

    # ── Cohere ────────────────────────────────────────────────────────────────
    LLMProvider(
        slug="cohere",
        name="Cohere",
        base_url="https://api.cohere.com/v2",
        api_key_env="COHERE_API_KEY",
        driver="openai_compat",
        default_model="command-a-03-2025",
        models=[
            "command-a-03-2025",          # confirmed free, working 2026-06-18
            "command-a-plus-05-2026",
            "command-a-reasoning-08-2025",
            "command-a-translate-08-2025", # multilingual specialist
            "command-a-vision-07-2025",    # vision
            "c4ai-aya-expanse-32b",
            "c4ai-aya-vision-32b",
        ],
        context_window=128_000,
        supports_vision=True,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Free trial key. Confirmed working 2026-06-18. API v2 endpoint.",
    ),

    # ── Azure OpenAI ──────────────────────────────────────────────────────────
    LLMProvider(
        slug="azure",
        name="Azure OpenAI",
        base_url="$AZURE_OPENAI_ENDPOINT",
        api_key_env="AZURE_OPENAI_API_KEY",
        driver="openai_compat",
        default_model="gpt-4o",
        models=["gpt-4o","gpt-4","gpt-4-turbo","gpt-35-turbo"],
        context_window=128_000,
        pricing_per_1m={"input":5.0,"output":15.0},
        notes="Enterprise compliance. Set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY.",
    ),

    # ── LM Studio (local OpenAI-compat) ──────────────────────────────────────
    LLMProvider(
        slug="lmstudio",
        name="LM Studio",
        base_url="http://localhost:1234/v1",
        api_key_env="LM_STUDIO_API_KEY",
        driver="openai_compat",
        default_model="local-model",
        models=["local-model"],
        free=True,
        context_window=32_000,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Local GUI for running any GGUF model. Free.",
    ),

    # ── vLLM (self-hosted) ────────────────────────────────────────────────────
    LLMProvider(
        slug="vllm",
        name="vLLM (Self-hosted)",
        base_url=CONFIG.get("vllm_base_url","http://localhost:8000/v1"),
        api_key_env="VLLM_API_KEY",
        driver="openai_compat",
        default_model="meta-llama/Llama-3-8b",
        models=["meta-llama/Llama-3-8b","mistralai/Mistral-7B-v0.1"],
        free=True,
        context_window=32_000,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Self-hosted high-throughput inference. Needs GPU server.",
    ),

    # ── Hugging Face Inference API ────────────────────────────────────────────
    LLMProvider(
        slug="huggingface",
        name="HuggingFace Inference",
        base_url="https://api-inference.huggingface.co/v1",
        api_key_env="HUGGINGFACE_API_KEY",
        driver="openai_compat",
        default_model="meta-llama/Llama-3.1-8B-Instruct",
        models=["meta-llama/Llama-3.1-8B-Instruct","mistralai/Mistral-7B-Instruct-v0.2",
                "Qwen/Qwen2.5-72B-Instruct"],
        context_window=8_000,
        pricing_per_1m={"input":0.2,"output":0.2},
    ),

    # ── Replicate ─────────────────────────────────────────────────────────────
    LLMProvider(
        slug="replicate",
        name="Replicate",
        base_url="https://api.replicate.com/v1",
        api_key_env="REPLICATE_API_KEY",
        driver="openai_compat",
        default_model="meta/llama-2-70b-chat",
        models=["meta/llama-2-70b-chat","mistralai/mistral-7b-instruct-v0.2"],
        context_window=4_096,
        pricing_per_1m={"input":0.65,"output":2.75},
        notes="Run any model on serverless GPU. Good for image models too.",
    ),

    # ── Anyscale ──────────────────────────────────────────────────────────────
    LLMProvider(
        slug="anyscale",
        name="Anyscale",
        base_url="https://api.endpoints.anyscale.com/v1",
        api_key_env="ANYSCALE_API_KEY",
        driver="openai_compat",
        default_model="meta-llama/Llama-2-70b-chat-hf",
        models=["meta-llama/Llama-2-70b-chat-hf","mistralai/Mixtral-8x7B-Instruct-v0.1"],
        context_window=16_000,
        pricing_per_1m={"input":1.0,"output":1.0},
    ),

    # ── Cloudflare Workers AI ─────────────────────────────────────────────────
    LLMProvider(
        slug="cloudflare",
        name="Cloudflare Workers AI",
        base_url=f"https://api.cloudflare.com/client/v4/accounts/{CONFIG.get('cloudflare_account_id','')}/ai/v1",
        api_key_env="CLOUDFLARE_API_KEY",
        driver="openai_compat",
        # llama-3.1-8b retired by Cloudflare (HTTP 410 "Model has been
        # deprecated", verified live 2026-07-02)
        default_model="@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        models=["@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                "@cf/mistral/mistral-7b-instruct-v0.2",
                "@cf/qwen/qwen1.5-14b-chat-awq"],
        context_window=8_000,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Free tier via Cloudflare Workers. Good for VECTOR cloud deployment.",
    ),

    # ── Cerebras (ultra-fast, free) ───────────────────────────────────────────
    LLMProvider(
        slug="cerebras",
        name="Cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key_env="CEREBRAS_API_KEY",
        driver="openai_compat",
        default_model="gpt-oss-120b",
        models=["gpt-oss-120b", "qwen-3.8-27b"],   # verified vs GET /v1/models 2026-09-25 (zai-glm-4.7, gemma-4-31b retired)
        context_window=65_536,
        rate_limit_rpm=5,   # owner console: 5 req/min, 1M tokens/day per model
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Free. Owner quotas 2026-07-02: 5rpm/150rph/2400rpd + 1M tok/day per model. "
              "gpt-oss-120b ~3000 tok/s (fastest in fleet); zai-glm-4.7 was archived 2026-09.",
    ),

    # ── SambaNova ─────────────────────────────────────────────────────────────
    LLMProvider(
        slug="sambanova",
        name="SambaNova",
        base_url="https://fast-api.snova.ai/v1",
        api_key_env="SAMBANOVA_API_KEY",
        driver="openai_compat",
        default_model="Meta-Llama-3.1-70B-Instruct",
        models=["Meta-Llama-3.1-70B-Instruct","Meta-Llama-3.1-405B-Instruct"],
        context_window=16_000,
        pricing_per_1m={"input":0.6,"output":1.2},
    ),

    # ── NVIDIA NIM ────────────────────────────────────────────────────────────
    LLMProvider(
        slug="nvidia",
        name="NVIDIA NIM",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key_env="NVIDIA_API_KEY",
        driver="openai_compat",
        default_model="meta/llama-3.1-70b-instruct",
        models=["meta/llama-3.1-70b-instruct","mistralai/mistral-7b-instruct-v0.3",
                "google/gemma-7b","nv-mistralai/mistral-nemo-12b-instruct"],
        context_window=128_000,
        pricing_per_1m={"input":0.68,"output":0.68},
    ),

    # ── Moonshot AI (Kimi) ────────────────────────────────────────────────────
    LLMProvider(
        slug="moonshot",
        name="Moonshot AI (Kimi)",
        base_url="https://api.moonshot.cn/v1",
        api_key_env="MOONSHOT_API_KEY",
        driver="openai_compat",
        default_model="moonshot-v1-8k",
        models=["moonshot-v1-8k","moonshot-v1-32k","moonshot-v1-128k"],
        context_window=128_000,
        pricing_per_1m={"input":1.0,"output":3.0},
        notes="Chinese provider. Kimi model. Good for Chinese language tasks.",
    ),

    # ── Zhipu AI (GLM) ────────────────────────────────────────────────────────
    LLMProvider(
        slug="zhipu",
        name="Zhipu AI (GLM)",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZHIPU_API_KEY",
        driver="openai_compat",
        default_model="glm-4-flash",
        models=["glm-4","glm-4-flash","glm-4-air","codegeex-4"],
        context_window=128_000,
        pricing_per_1m={"input":0.5,"output":0.5},
        notes="Chinese provider. glm-4-flash is free.",
    ),

    # ── Baidu Wenxin ─────────────────────────────────────────────────────────
    LLMProvider(
        slug="baidu",
        name="Baidu Wenxin",
        base_url="https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
        api_key_env="BAIDU_API_KEY",
        driver="openai_compat",
        default_model="ernie-4.0-8k",
        models=["ernie-4.0-8k","ernie-speed-128k","ernie-lite-8k"],
        context_window=128_000,
        pricing_per_1m={"input":0.8,"output":0.8},
        notes="Chinese provider. ERNIE model family.",
    ),

    # ── 01.AI (Yi) ────────────────────────────────────────────────────────────
    LLMProvider(
        slug="yi",
        name="01.AI (Yi)",
        base_url="https://api.lingyiwanwu.com/v1",
        api_key_env="YI_API_KEY",
        driver="openai_compat",
        default_model="yi-large",
        models=["yi-large","yi-medium","yi-spark","yi-large-turbo"],
        context_window=200_000,
        pricing_per_1m={"input":3.0,"output":3.0},
    ),

    # ── LLM7 (free plan, confirmed working 2026-06-18) ────────────────────────
    LLMProvider(
        slug="llm7",
        name="LLM7",
        base_url="https://api.llm7.io/v1",
        api_key_env="LLM7_API_KEY",
        driver="openai_compat",
        # Catalog rotates — old default mistral-small-3.2 vanished (400s).
        # Live /v1/models list fetched 2026-07-02:
        default_model="gemini-2.5-flash",
        models=[
            "gemini-2.5-flash", "gemini-3-flash", "gemini-3.1-pro",
            "deepseek-v4-flash", "codestral-latest", "devstral-small-2:24b",
            "kimi-k2.6", "minimax-m2.7", "gpt-5.5", "gpt-5.4",
            "gpt-5.4-mini", "gpt-5.3-codex-spark", "claude-fable-5",
            "claude-sonnet-5",
        ],
        context_window=240_000,
        rate_limit_rpm=60,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Free gateway (proxied frontier models — bonus capacity, not backbone). "
              "Catalog rotates; refresh from public GET /v1/models.",
    ),

    # ── GitHub Models (free, needs GitHub Personal Access Token) ──────────────
    # Catalog: GPT-5, o3, o4-mini, GPT-4o, Phi-4 series — all free with GitHub account
    # Rate limit: ~15 RPM, ~150 requests/day for most models (use for high-value tasks)
    # 2026-10-12 (live FL-012 provider acceptance run): models.inference.ai.azure.com
    # is a dead domain (confirmed NXDOMAIN) -- GitHub Models moved off the Azure AI
    # Inference preview to its own first-party host. _call_openai_compat() appends
    # "/chat/completions" to base_url, so this must stop at ".../inference" (verified
    # both bare "gpt-4o-mini" and publisher-prefixed "openai/gpt-4o-mini" model ids
    # return 200 against the real endpoint from a network that isn't filtering it).
    LLMProvider(
        slug="github_models",
        name="GitHub Models",
        base_url="https://models.github.ai/inference",
        api_key_env="GITHUB_TOKEN",
        driver="openai_compat",
        default_model="gpt-4o",
        models=[
            # OpenAI — flagship + reasoning
            "gpt-5", "gpt-5-mini", "gpt-5-chat", "gpt-5-nano",
            "gpt-4o", "gpt-4o-mini", "GPT-4.1", "GPT-4.1-mini", "GPT-4.1-nano",
            "o4-mini", "o3", "o3-mini", "o1", "o1-mini", "o1-preview",
            # Microsoft Phi-4
            "Phi-4", "Phi-4-reasoning", "Phi-4-mini-reasoning",
            "Phi-4-mini-instruct", "Phi-4-multimodal-instruct",
            # Meta Llama
            "Meta-Llama-3.1-8B-Instruct", "Meta-Llama-3.1-405B-Instruct",
            "Llama-3.3-70B-Instruct",
            "Llama-3.2-90B-Vision-Instruct", "Llama-3.2-11B-Vision-Instruct",
            "Llama-4-Scout-17B-16E-Instruct", "Llama-4-Maverick-17B-128E-Instruct-FP8",
            # DeepSeek
            "DeepSeek-R1", "DeepSeek-R1-0528", "DeepSeek-V3-0324",
            # Mistral
            "Mistral-Small-3.1", "Codestral-25.01", "Mistral-Medium-3", "Ministral-3B",
            # Cohere
            "Cohere-Command-A",
            # Embeddings
            "text-embedding-3-large", "text-embedding-3-small",
        ],
        context_window=128_000,
        supports_vision=True,
        rate_limit_rpm=15,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Free with GitHub account. GPT-5+o3+Phi-4. ~150 req/day — use for high-value tasks.",
    ),

    # ── Z.ai / ZhipuAI (GLM models) ──────────────────────────────────────────
    LLMProvider(
        slug="zai",
        name="Z.ai (GLM/ZhipuAI)",
        base_url="https://api.z.ai/api/paas/v4",   # verified live 2026-07-02
        api_key_env="ZAI_API_KEY",
        driver="openai_compat",
        # glm-4.5 is PAID (caused "insufficient balance" 429s); the flash
        # line is free — verified 200 OK with owner key 2026-07-02.
        default_model="glm-4.7-flash",
        models=["glm-4.7-flash", "glm-4.5-flash", "glm-4.6V-flash"],
        locked_models=True,   # non-flash models bill the (empty) paid balance
        context_window=128_000,
        rate_limit_rpm=60,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Z.ai GLM API. FREE flash models only (hard whitelist) — glm-4.5/5.2 are paid.",
    ),

    # ── OpenCode Zen (added 2026-07-02, all 5 free models verified live) ─────
    LLMProvider(
        slug="opencode_zen",
        name="OpenCode Zen",
        base_url="https://opencode.ai/zen/v1",
        api_key_env="OPENCODE_API_KEY",
        driver="openai_compat",
        default_model="deepseek-v4-flash-free",
        models=["deepseek-v4-flash-free", "big-pickle", "mimo-v2.5-free",
                "north-mini-code-free", "nemotron-3-ultra-free"],
        # The same key serves PAID models (claude-fable-5, gpt-5.5, ...) and
        # the owner's card is on file — selection must NEVER fall through.
        locked_models=True,
        context_window=256_000,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="5 free models ONLY (hard whitelist — owner card on file; paid catalog "
              "reachable by the same key). Free models log prompts; 'limited time'. "
              "big-pickle is thinking-mode: give generous max_tokens.",
    ),

    # NOTE: FreeLLMAPI is deliberately NOT a PROVIDERS entry. It's a local
    # gateway that forwards to 60+ third-party providers, some of which reach
    # paid tiers on the same key — its upstream cost is not guaranteed free,
    # so it must never be reachable by the unsupervised autonomous loop. It's
    # wired as a coding-only, explicit-selection provider instead; see
    # vectorcode/src/providers/coding_catalog.py.

]}

# ── Routing helpers ────────────────────────────────────────────────────────────

# Map of task tier → preferred provider priority list
TIER_ROUTING: dict[str, list[str]] = {
    # STRATEGY (regenerated 2026-07-02 from owner's measured free-tier data —
    # see core/inference/model_catalog.yaml): cloud primary, ollama terminal.
    # Provider order per tier ranks capability strength x free-limit generosity.
    # The catalog picks the best MODEL per provider per tier (rank 1 first);
    # quota_ledger soft-deprioritizes anything past 90% of its daily free tier.
    #
    #   groq          — gpt-oss-20b/120b + qwen3.8-27b (Llama models retired 2026-09); ~1K req/day
    #   mistral       — ministral-3b 12.5 RPS; codestral/devstral; huge TPMs
    #   cerebras      — gpt-oss-120b (heavy/reasoning lead; zai-glm-4.7 archived); ~3000 tok/s; 1M tok/day/model
    #   github_models — gpt-5/o3 (assumed 50/day), Codestral, DeepSeek-R1, vision (150/day)
    #   opencode_zen  — 5 unlimited free models (HARD whitelist — paid catalog on same key)
    #   cloudflare    — kimi-k2.7-code, qwen-coder, sea-lion; 10K neurons/day
    #   nvidia        — 40 RPM; qwen3-coder-480b, sarvam-m (Indic), 90b-vision
    #   gemini        — 2.5-flash/pro, best vision/long-context (daily quotas modest)
    #   zai           — glm-4.7-flash FREE (locked whitelist); Asian languages
    #   openrouter    — 22 :free models ~1000/day; nemotron-ultra-550b headliner
    #   llm7          — free proxied frontier models; bonus capacity, not backbone
    #   cohere        — TRIAL 1000 req/month: demoted everywhere; translate/aya niche
    #   ollama        — LOCAL TERMINAL: all-cloud failure or sensitivity=high
    #
    # Private/sensitive districts always route local via route_policy.py.

    # Agentic loop — high frequency: biggest req/day budgets first
    "agentic":       ["groq", "mistral", "cerebras", "zai", "llm7", "gemini", "opencode_zen", "nvidia", "openrouter", "ollama"],

    # Coding — Codestral/gpt-5, kimi-k2.7-code, north-mini-code, devstral
    "coding":        ["github_models", "cloudflare", "opencode_zen", "mistral", "llm7", "nvidia", "groq", "openrouter", "ollama"],

    # SaaS architecture / API design — gpt-5 + 355B-class quality
    "saas":          ["github_models", "cerebras", "nvidia", "opencode_zen", "openrouter", "groq", "ollama"],

    # Reasoning — cerebras gpt-oss-120b (1M tok/day) leads; o3/gpt-5 premium quota next
    "reasoning":     ["cerebras", "github_models", "groq", "opencode_zen", "nvidia", "cloudflare", "openrouter", "llm7", "ollama"],

    # Summarization — gemini flash; mistral-small 2.25M TPM; llama-4-scout 30K tok/min
    "summarization": ["gemini", "mistral", "groq", "cloudflare", "opencode_zen", "llm7", "openrouter", "ollama"],

    # Multilingual — glm-4.7-flash free; sarvam-m (Indic) on nvidia; sea-lion on cloudflare
    "multilingual":  ["zai", "nvidia", "cloudflare", "gemini", "llm7", "cohere", "openrouter", "ollama"],

    # Long context — gemini 1M ctx; llama-4-scout on github/groq
    "long_context":  ["gemini", "llm7", "github_models", "groq", "nvidia", "openrouter", "ollama"],

    # Vision — gemini native; 90b-vision on nvidia/github; glm-4.6V-flash free
    "vision":        ["gemini", "nvidia", "github_models", "zai", "cloudflare", "openrouter", "ollama"],

    # Fast — 8b-instant 14.4K/day, ministral-3b 12.5 RPS, gpt-oss-120b 3000 tok/s
    "fast":          ["groq", "mistral", "cerebras", "gemini", "opencode_zen", "llm7", "cloudflare", "openrouter", "ollama"],

    # Council — rare, high-stakes: 355B + o3/gpt-5 + nemotron-ultra
    "council":       ["cerebras", "github_models", "nvidia", "opencode_zen", "openrouter", "llm7", "ollama"],

    # Translation — glm-4.7-flash, riva-translate, gemini; cohere command-a-translate niche
    "translate":     ["zai", "nvidia", "gemini", "cohere", "llm7", "ollama"],

    # Conversation — latency: groq ~500 tok/s, cerebras wafer-speed
    # NOTE: STT (Whisper) and TTS (Kokoro) are always local regardless of this tier.
    "conversation":  ["groq", "cerebras", "mistral", "gemini", "llm7", "ollama"],
}


def get_provider(slug: str) -> LLMProvider | None:
    return PROVIDERS.get(slug)


def configured_providers() -> list[LLMProvider]:
    """Return providers that have API keys set or are free."""
    return [p for p in PROVIDERS.values() if p.is_configured]


def route_for_tier(tier: str) -> LLMProvider | None:
    """Return the first configured provider for a task tier."""
    for slug in TIER_ROUTING.get(tier, ["ollama"]):
        p = PROVIDERS.get(slug)
        if p and p.is_configured:
            return p
    return PROVIDERS.get("ollama")


def list_free() -> list[LLMProvider]:
    return [p for p in PROVIDERS.values() if p.free]


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    assert len(PROVIDERS) >= 27
    ollama = get_provider("ollama")
    assert ollama and ollama.free and ollama.pricing_per_1m["input"] == 0.0

    # freellmapi must NEVER appear here: it's a coding-only, explicit-selection
    # gateway (vectorcode/src/providers/coding_catalog.py) — it forwards to
    # providers whose upstream cost is not guaranteed free, so it must not be
    # reachable by the unsupervised autonomous loop. See 2026-10-28 correction.
    assert get_provider("freellmapi") is None
    assert all("freellmapi" not in chain for chain in TIER_ROUTING.values())

    # Routing
    agentic = route_for_tier("agentic")
    assert agentic is not None   # at least Ollama is always configured

    free = list_free()
    assert any(p.slug == "ollama" for p in free)

    configured = configured_providers()
    assert len(configured) >= 1  # at minimum Ollama

    print(f"OK llm_providers.py — {len(PROVIDERS)} providers, {len(configured)} configured")
