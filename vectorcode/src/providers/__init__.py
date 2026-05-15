"""VectorCode Model Router — resolves "provider/model" strings to provider adapters.

Usage:
    from providers import ModelRouter
    router = ModelRouter()
    result = router.complete("anthropic/claude-sonnet-4-6", messages)
    result = router.complete("ollama/vector-focus", messages)
    result = router.complete("groq/llama-4-scout", messages)
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode package

from loguru import logger
from providers.base import (
    BaseProvider, CompletionResult, ModelCapabilities, TokenUsage
)
from providers.ollama import OllamaProvider
from providers.openai_compat import (
    OpenAICompatProvider, OpenAIProvider, AnthropicProvider, GoogleProvider,
    GroqProvider, MistralProvider, DeepSeekProvider, OpenRouterProvider,
    LMStudioProvider,
)
from providers.capability_probe import CapabilityProbe

try:
    from config import VectorConfig as _VectorConfig
    class _ConfigShim:
        def __init__(self, project_dir=None):
            self._cfg = {}
        def provider_config(self, name):
            return {}
        def get(self, key, default=None):
            return default
    VectorConfig = _VectorConfig
except (ImportError, Exception):
    class VectorConfig:  # type: ignore
        def __init__(self, project_dir=None):
            self._cfg = {}
        def provider_config(self, name):
            import os
            return {"api_key": os.getenv(f"{name.upper()}_API_KEY", "")}
        def get(self, key, default=None):
            return default


_BUILTIN_PROVIDERS: dict[str, type] = {
    "ollama":     OllamaProvider,
    "anthropic":  AnthropicProvider,
    "openai":     OpenAIProvider,
    "google":     GoogleProvider,
    "groq":       GroqProvider,
    "mistral":    MistralProvider,
    "deepseek":   DeepSeekProvider,
    "openrouter": OpenRouterProvider,
    "lmstudio":   LMStudioProvider,
}


class ModelRouter:
    """
    Routes "provider/model" identifiers to the correct provider adapter.

    Supports:
    - "anthropic/claude-sonnet-4-6"
    - "openai/gpt-4o"
    - "groq/llama-4-scout"
    - "ollama/vector-focus"
    - "ollama/qwen2.5-coder:32b"
    - bare names like "vector-focus" (treated as ollama/)
    """

    def __init__(self, project_dir: Path | None = None) -> None:
        self._cfg = VectorConfig(project_dir=project_dir)
        self._instances: dict[str, BaseProvider] = {}
        self._prober = CapabilityProbe()

    def _get_provider(self, provider_name: str) -> BaseProvider:
        if provider_name in self._instances:
            return self._instances[provider_name]

        prov_cfg = self._cfg.provider_config(provider_name)
        cls = _BUILTIN_PROVIDERS.get(provider_name)

        if cls is None:
            # Unknown provider — try OpenAI-compat with configured base_url
            base_url = prov_cfg.get("base_url", "")
            api_key  = prov_cfg.get("api_key", "")
            api_key_env = prov_cfg.get("api_key_env", "")
            if api_key_env:
                api_key = os.environ.get(api_key_env, api_key)
            instance: BaseProvider = OpenAICompatProvider(base_url=base_url, api_key=api_key)
        elif provider_name == "ollama":
            base_url = prov_cfg.get("base_url", "http://localhost:11434")
            instance = OllamaProvider(base_url=base_url)
        else:
            # Cloud provider — extract api_key from config or env
            api_key  = prov_cfg.get("api_key", "")
            api_key_env = prov_cfg.get("api_key_env", "")
            instance = cls(api_key=api_key, api_key_env=api_key_env)  # type: ignore

        self._instances[provider_name] = instance
        return instance

    def parse(self, model_id: str) -> tuple[str, str]:
        """Parse "provider/model" → ("provider", "model"). Bare names → ollama."""
        if "/" in model_id:
            provider, model = model_id.split("/", 1)
            return provider.lower(), model
        return "ollama", model_id

    def complete(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
        max_tokens: int = 8192,
    ) -> CompletionResult:
        provider_name, model = self.parse(model_id)
        provider = self._get_provider(provider_name)
        logger.debug(f"[VECTOR][router] routing {model_id} → {provider_name} / {model}")
        return provider.complete(model, messages, tools=tools, stream=stream, max_tokens=max_tokens)

    def get_capabilities(self, model_id: str) -> ModelCapabilities:
        provider_name, model = self.parse(model_id)
        provider = self._get_provider(provider_name)
        return self._prober.get_or_probe(model_id, provider)

    def list_configured_models(self) -> list[str]:
        """Return list of provider names that have config entries."""
        providers_cfg = self._cfg.get("providers", default={})
        return [f"{pname}/*" for pname in (providers_cfg or {}).keys()]

    def test_connection(self, model_id: str) -> dict:
        """Test if a model is reachable. Returns {ok, latency_ms, error}."""
        import time
        t0 = time.perf_counter()
        try:
            result = self.complete(
                model_id,
                [{"role": "user", "content": "reply with the single word: ok"}],
                stream=False,
                max_tokens=10,
            )
            latency = int((time.perf_counter() - t0) * 1000)
            ok = "error" not in result.message.content.lower()[:20]
            return {"ok": ok, "latency_ms": latency, "response": result.message.content[:50]}
        except Exception as e:
            return {"ok": False, "latency_ms": -1, "error": str(e)}

    async def chat(
        self,
        model: str,
        messages: list,
        tools: list | None = None,
        **kwargs,
    ) -> dict:
        """Async chat interface used by engine/conversation.py.

        Wraps the sync complete() in a thread to avoid blocking the event loop.
        Returns a normalized dict with 'message.content' and 'message.tool_calls'.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.complete(model, messages, tools=tools, stream=False),
        )
        # Normalize to dict format expected by engine
        content = getattr(getattr(result, "message", None), "content", "") or ""
        tool_calls = getattr(getattr(result, "message", None), "tool_calls", []) or []
        return {
            "message": {
                "content": content,
                "tool_calls": [
                    {
                        "id": getattr(tc, "id", ""),
                        "name": getattr(tc, "name", "") or getattr(getattr(tc, "function", None), "name", ""),
                        "arguments": getattr(tc, "arguments", "") or getattr(getattr(tc, "function", None), "arguments", "{}"),
                    }
                    for tc in (tool_calls or [])
                ],
            }
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    """Return the global ModelRouter singleton."""
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    router = ModelRouter()
    pname, model = router.parse("anthropic/claude-sonnet-4-6")
    assert pname == "anthropic" and model == "claude-sonnet-4-6"
    pname2, model2 = router.parse("vector-focus")
    assert pname2 == "ollama" and model2 == "vector-focus"
    caps = router.get_capabilities("openai/gpt-4o")
    assert caps.context_window == 128_000
    print("providers/__init__.py OK")





