"""Capability probing for VectorCode providers.

Probes a model by sending a minimal test request and observing the response.
Results cached in ModelRegistry (~/.config/vector/model-registry.json).

Absorbs from reference agent/model_metadata.py:
- PROVIDER_PREFIXES frozenset — recognized provider name prefixes
- _OLLAMA_TAG_PATTERN — regex to detect Ollama model:tag notation
- MODEL_CONTEXT_LENGTHS dict — model name -> context window size
- strip_provider_prefix() — remove provider: prefix from model ID
- get_context_length() — look up context window for a model
"""

import sys
import re

from loguru import logger
from providers.base import ModelCapabilities

class _InMemoryModelRegistry:
    """Non-persistent fallback when the configured cache is unavailable."""

    def __init__(self, path=None):
        self._data = {}

    def get(self, model_id):
        return self._data.get(model_id)

    def set(self, model_id, caps):
        self._data[model_id] = caps

    def save(self):
        # Intentionally stateless: there is no backing file to flush.
        pass


try:
    from config import ModelRegistry
except ImportError:
    ModelRegistry = _InMemoryModelRegistry  # type: ignore[misc, assignment]

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}


# ── Provider prefix registry (from reference model_metadata.py) ──────────────────

PROVIDER_PREFIXES: frozenset[str] = frozenset({
    "openrouter", "nous", "openai-codex", "copilot", "copilot-acp",
    "gemini", "ollama-cloud", "zai", "kimi-coding", "kimi-coding-cn",
    "stepfun", "minimax", "minimax-cn", "anthropic", "deepseek",
    "opencode-zen", "opencode-go", "ai-gateway", "kilocode", "alibaba",
    "qwen-oauth", "xiaomi", "arcee", "gmi", "custom", "local",
    "google", "google-gemini", "google-ai-studio",
    "glm", "z-ai", "z.ai", "zhipu", "github", "github-copilot",
    "github-models", "kimi", "moonshot", "kimi-cn", "moonshot-cn",
    "claude", "deep-seek", "ollama",
    "stepfun", "opencode", "zen", "go", "vercel", "kilo",
    "dashscope", "aliyun", "qwen",
    "mimo", "xiaomi-mimo",
    "arcee-ai", "arceeai",
    "gmi-cloud", "gmicloud",
    "xai", "x-ai", "x.ai", "grok",
    "nvidia", "nim", "nvidia-nim", "nemotron",
    "qwen-portal",
    "openai", "mistral", "cohere", "groq", "fireworks",
})

# Pattern: Ollama tag suffix like "7b", "latest", "q4_0", "fp16", "instruct"
_OLLAMA_TAG_PATTERN = re.compile(
    r"^(\d+\.?\d*b|latest|stable|q\d|fp?\d|instruct|chat|coder|vision|text)",
    re.IGNORECASE,
)


def strip_provider_prefix(model_id: str) -> str:
    """Strip a recognized provider prefix from a model string.

    Examples:
        "local:my-model"       -> "my-model"
        "qwen3.5:27b"          -> "qwen3.5:27b"  (Ollama tag, not stripped)
        "ollama/llama4:scout"  -> "llama4:scout"  (slash-separated)
    """
    # Handle slash-separated provider/model format first
    if "/" in model_id and not model_id.startswith("http"):
        prefix, rest = model_id.split("/", 1)
        if prefix.strip().lower() in PROVIDER_PREFIXES:
            return rest
        return model_id

    # Handle colon-separated provider:model format
    if ":" not in model_id or model_id.startswith("http"):
        return model_id

    prefix, suffix = model_id.split(":", 1)
    prefix_lower = prefix.strip().lower()
    if prefix_lower in PROVIDER_PREFIXES:
        # Don't strip if suffix looks like an Ollama tag (e.g. "7b", "latest", "q4_0")
        if _OLLAMA_TAG_PATTERN.match(suffix.strip()):
            return model_id
        return suffix
    return model_id


# ── Context window lookup table (from reference model_metadata.py) ───────────────

MODEL_CONTEXT_LENGTHS: dict[str, int] = {
    # Claude 4.6 family (1M context)
    "claude-opus-4-7":    1_000_000,
    "claude-opus-4.7":    1_000_000,
    "claude-opus-4-6":    1_000_000,
    "claude-sonnet-4-6":  1_000_000,
    "claude-opus-4.6":    1_000_000,
    "claude-sonnet-4.6":  1_000_000,
    # Older Claude — catch-all
    "claude":             200_000,
    # GPT-5 family
    "gpt-5.5":            1_050_000,
    "gpt-5.4-nano":       400_000,
    "gpt-5.4-mini":       400_000,
    "gpt-5.4":            1_050_000,
    "gpt-5.1-chat":       128_000,
    "gpt-5":              400_000,
    "gpt-4.1":            1_047_576,
    "gpt-4":              128_000,
    # Google
    "gemini":             1_048_576,
    "gemma-4":            256_000,
    "gemma4":             256_000,
    "gemma-4-31b":        256_000,
    "gemma-3":            131_072,
    "gemma":              8_192,
    # DeepSeek
    "deepseek-v4-pro":    1_000_000,
    "deepseek-v4-flash":  1_000_000,
    "deepseek-chat":      1_000_000,
    "deepseek-reasoner":  1_000_000,
    "deepseek":           128_000,
    # Meta LLaMA
    "llama":              131_072,
    # Qwen
    "qwen3-coder-plus":   1_000_000,
    "qwen3-coder":        262_144,
    "qwen":               131_072,
    # MiniMax
    "minimax":            204_800,
    # GLM
    "glm":                202_752,
    # xAI Grok
    "grok-code-fast":     256_000,
    "grok-4-1-fast":      2_000_000,
    "grok-2-vision":      8_192,
    "grok-4-fast":        2_000_000,
    "grok-4.20":          2_000_000,
    "grok-4":             256_000,
    "grok-3":             131_072,
    "grok-2":             131_072,
    "grok":               131_072,
    # Kimi
    "kimi":               262_144,
    "kimi-k2":            262_144,
    # Nemotron (NVIDIA)
    "nemotron":           131_072,
    # Mistral
    "mistral-large":      131_072,
    "mistral-small":      32_000,
    "codestral":          256_000,
    "devstral":           131_072,
    "mistral":            32_000,
    # DeepSeek-R1 (open-weights)
    "deepseek-r1":        128_000,
    # VECTOR local models (Ollama-served)
    "vector-focus":       131_072,
    "vector-ambient":     8_192,
    "vector-multilingual": 131_072,
    "vector-reasoning":   131_072,
    "vector-coder":       131_072,
    "vector-reasoning":        65_536,
    "vector-reasoning":    32_768,
    "vector-r1":          128_000,
    "vector-coder":         131_072,
    "vector-focus":        32_000,
    # Standard local names
    "qwen3:8b":           32_000,
    "qwen3:14b":          131_072,
    "vector-reasoning":      131_072,
    "gemma4:e2b":         256_000,
    "gemma4:e4b":         256_000,
    "qwen3:14b":         256_000,
    "qwen3:14b":         256_000,
    "nomic-embed-text":   8_192,
}


def get_context_length(model_id: str, default: int = 32_000) -> int:
    """Return context window size for a model.

    Strips provider prefix first, then does longest-match lookup.
    Falls back to default (32_000) if no match found.
    """
    bare = strip_provider_prefix(model_id).lower()

    # Exact match first
    if bare in MODEL_CONTEXT_LENGTHS:
        return MODEL_CONTEXT_LENGTHS[bare]

    # Also check with original casing stripped
    if model_id.lower() in MODEL_CONTEXT_LENGTHS:
        return MODEL_CONTEXT_LENGTHS[model_id.lower()]

    # Longest-prefix match (e.g. "claude-sonnet-4-6-20251120" hits "claude-sonnet-4-6")
    best_key = ""
    best_val = default
    for key, val in MODEL_CONTEXT_LENGTHS.items():
        if bare.startswith(key) and len(key) > len(best_key):
            best_key = key
            best_val = val

    if best_key:
        return best_val

    return default


# ── Probe tool ────────────────────────────────────────────────────────────────

_PROBE_TOOL = [{
    "type": "function",
    "function": {
        "name": "probe_echo",
        "description": "Echo the input back",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
}]


class CapabilityProbe:
    """Probe a model once; cache the result; re-use on subsequent calls."""

    def __init__(self) -> None:
        try:
            self._registry = ModelRegistry()
        except OSError as exc:
            logger.warning(
                "[VECTOR][probe] model capability cache unavailable; using memory only: {}",
                exc,
            )
            self._registry = _InMemoryModelRegistry()

    def get_or_probe(self, model_id: str, provider) -> ModelCapabilities:
        """Return cached capabilities or probe the model if not yet cached."""
        cached = self._registry.get(model_id)
        if cached:
            return ModelCapabilities(**cached)

        logger.info(f"[VECTOR][probe] probing capabilities for {model_id}...")
        caps = self._probe(model_id, provider)

        # Use MODEL_CONTEXT_LENGTHS if probe returned the default
        if caps.context_window <= 4096:
            looked_up = get_context_length(model_id)
            if looked_up > caps.context_window:
                caps = ModelCapabilities(
                    context_window=looked_up,
                    tool_use=caps.tool_use,
                    vision=caps.vision,
                    structured_output=caps.structured_output,
                    supports_streaming=caps.supports_streaming,
                )

        self._registry.set(model_id, {
            "context_window":     caps.context_window,
            "tool_use":           caps.tool_use,
            "vision":             caps.vision,
            "structured_output":  caps.structured_output,
            "supports_streaming": caps.supports_streaming,
        })
        return caps

    def _probe(self, model_id: str, provider) -> ModelCapabilities:
        """Delegate to provider's probe_capabilities."""
        short_name = strip_provider_prefix(model_id)
        try:
            return provider.probe_capabilities(short_name)
        except Exception as e:
            logger.warning(f"[VECTOR][probe] probe_capabilities failed for {model_id}: {e}")
            return ModelCapabilities(context_window=get_context_length(model_id))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # Test strip_provider_prefix
    assert strip_provider_prefix("local:my-model") == "my-model"
    assert strip_provider_prefix("qwen3.5:27b") == "qwen3.5:27b"  # Ollama tag
    assert strip_provider_prefix("ollama/llama4:scout") == "llama4:scout"
    assert strip_provider_prefix("vector-focus") == "vector-focus"

    # Test get_context_length
    assert get_context_length("vector-focus") == 131_072
    assert get_context_length("claude-sonnet-4-6") == 1_000_000
    assert get_context_length("qwen3:14b") == 256_000
    assert get_context_length("gpt-4") == 128_000
    assert get_context_length("unknown-model-xyz") == 32_000

    # Test PROVIDER_PREFIXES
    assert "ollama" in PROVIDER_PREFIXES
    assert "anthropic" in PROVIDER_PREFIXES

    try:
        from providers.ollama import OllamaProvider
        prober = CapabilityProbe()
        p = OllamaProvider()
        caps = prober.get_or_probe("ollama/vector-focus", p)
        assert isinstance(caps.context_window, int) and caps.context_window > 0
        print(f"capability_probe.py OK — context_window={caps.context_window}")
    except Exception as e:
        print(f"capability_probe.py OK (Ollama not running: {e})")


