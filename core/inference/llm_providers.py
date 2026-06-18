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
    rate_limit_rpm: int = 60
    pricing_per_1m: dict = field(default_factory=lambda: {"input": 0.0, "output": 0.0})
    notes: str = ""

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
        models=["qwen3:14b","qwen3:8b","devstral:24b","deepseek-r1:14b",
                "gemma4:26b","mistral-small3.1","vector-focus","vector-coder"],
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
        default_model="gemini-2.5-flash",
        models=["gemini-2.5-flash","gemini-2.0-flash","gemini-1.5-pro","gemini-1.5-flash"],
        context_window=1_000_000,
        supports_vision=True,
        rate_limit_rpm=60,
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
        default_model="llama-3.3-70b-versatile",
        models=["llama-3.3-70b-versatile","llama-3.1-8b-instant","mixtral-8x7b-32768",
                "gemma2-9b-it","deepseek-r1-distill-llama-70b"],
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
        default_model="deepseek-chat",
        models=["deepseek-chat","deepseek-coder","deepseek-reasoner"],
        context_window=64_000,
        pricing_per_1m={"input":0.14,"output":0.28},
        notes="Very cheap. deepseek-reasoner = R1 reasoning chain.",
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
        default_model="meta-llama/llama-3.3-70b-instruct",
        models=["meta-llama/llama-3.3-70b-instruct","anthropic/claude-3.5-sonnet",
                "google/gemini-flash-1.5","mistralai/mixtral-8x7b-instruct",
                "cohere/command-r-plus","01-ai/yi-large"],
        context_window=200_000,
        pricing_per_1m={"input":0.0,"output":0.0},    # varies per model
        notes="Access 300+ models with one API key. Useful for model fallback chains.",
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
                "NousResearch/Nous-Hermes-2-Yi-34B","Qwen/Qwen1.5-72B-Chat"],
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
        default_model="@cf/meta/llama-3.1-8b-instruct",
        models=["@cf/meta/llama-3.1-8b-instruct","@cf/mistral/mistral-7b-instruct-v0.2",
                "@cf/qwen/qwen1.5-14b-chat-awq"],
        context_window=8_000,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Free tier via Cloudflare Workers. Good for VECTOR cloud deployment.",
    ),

    # ── Cohere Command R ─────────────────────────────────────────────────────
    LLMProvider(
        slug="cohere-rag",
        name="Cohere (RAG-optimized)",
        base_url="https://api.cohere.com/v2",
        api_key_env="COHERE_API_KEY",
        driver="openai_compat",
        default_model="command-a-03-2025",
        models=["command-a-03-2025","command-a-translate-08-2025","command-a-vision-07-2025"],
        context_window=128_000,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Duplicate entry — primary Cohere block above is authoritative.",
    ),

    # ── Cerebras (ultra-fast, free) ───────────────────────────────────────────
    LLMProvider(
        slug="cerebras",
        name="Cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key_env="CEREBRAS_API_KEY",
        driver="openai_compat",
        default_model="gpt-oss-120b",
        models=["gpt-oss-120b", "zai-glm-4.7"],
        context_window=128_000,
        rate_limit_rpm=60,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Free. Confirmed 2026-06-18. gpt-oss-120b (120B) + zai-glm-4.7 (GLM). Ultra-fast Cerebras silicon.",
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
        default_model="mistral-small-3.2",
        models=[
            "mistral-small-3.2",    # confirmed free
            "codestral-latest",     # confirmed free
            "qwen3-235b",           # confirmed free (slow, 240K ctx)
            "kimi-k2.6",            # confirmed free via LLM7
            "glm-5.2",              # confirmed free via LLM7
            "GLM-4.6V-Flash",       # confirmed free via LLM7 (vision)
            "minimax-m2.7",         # likely free
            "devstral-small-2:24b", # likely free
        ],
        context_window=240_000,
        rate_limit_rpm=60,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="Free plan, verified 2026-06-18. Base URL: api.llm7.io/v1. Pro models (deepseek-v4) require upgrade.",
    ),

    # ── GitHub Models (free, needs GitHub Personal Access Token) ──────────────
    # Catalog: GPT-5, o3, o4-mini, GPT-4o, Phi-4 series — all free with GitHub account
    # Rate limit: ~15 RPM, ~150 requests/day for most models (use for high-value tasks)
    LLMProvider(
        slug="github_models",
        name="GitHub Models",
        base_url="https://models.inference.ai.azure.com",
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
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZAI_API_KEY",
        driver="openai_compat",
        default_model="glm-4.5",
        models=["glm-4.5", "glm-4.7-flash", "glm-4-flash", "glm-4-air"],
        context_window=128_000,
        rate_limit_rpm=60,
        pricing_per_1m={"input":0.0,"output":0.0},
        notes="ZhipuAI/GLM API. Key env: ZAI_API_KEY. Free credits on signup; may hit 429 when exhausted.",
    ),

]}

# ── Routing helpers ────────────────────────────────────────────────────────────

# Map of task tier → preferred provider priority list
TIER_ROUTING: dict[str, list[str]] = {
    # Priority: ollama (free local) → groq/cerebras/gemini (free, fast) → llm7/openrouter (free cloud)
    # github_models = rate-limited (50/day premium) — reserved for high-value tasks only
    # gemini = 360M tokens/month free once GEMINI_API_KEY is set
    "agentic":       ["ollama", "groq", "cerebras", "gemini", "llm7", "openrouter", "nvidia"],
    "coding":        ["ollama", "groq", "llm7", "mistral", "cerebras", "github_models", "openrouter"],
    "reasoning":     ["ollama", "groq", "github_models", "gemini", "llm7", "nvidia", "openrouter"],
    "summarization": ["ollama", "groq", "cerebras", "gemini", "llm7", "cohere"],
    "multilingual":  ["ollama", "cohere", "gemini", "llm7", "zai"],
    "vision":        ["gemini", "github_models", "nvidia", "cohere", "openrouter"],
    "fast":          ["ollama", "groq", "cerebras", "gemini", "llm7"],
    "council":       ["ollama", "groq", "github_models", "gemini", "llm7", "nvidia", "openrouter"],
    "translate":     ["cohere", "gemini", "ollama", "llm7", "zai"],
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
    assert len(PROVIDERS) >= 27
    ollama = get_provider("ollama")
    assert ollama and ollama.free and ollama.pricing_per_1m["input"] == 0.0

    # Routing
    agentic = route_for_tier("agentic")
    assert agentic is not None   # at least Ollama is always configured

    free = list_free()
    assert any(p.slug == "ollama" for p in free)

    configured = configured_providers()
    assert len(configured) >= 1  # at minimum Ollama

    print(f"OK llm_providers.py — {len(PROVIDERS)} providers, {len(configured)} configured")
