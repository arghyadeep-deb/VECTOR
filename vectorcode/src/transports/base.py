"""Abstract base for provider transports.

A transport owns the data path for one api_mode:
    convert_messages → convert_tools → build_kwargs → normalize_response

It does NOT own: client construction, streaming, credential refresh,
prompt caching, interrupt handling, or retry logic.

VectorCode implementation.py.
"""

# ── Guard: strip transports/ from sys.path[0] to prevent types.py shadowing
# stdlib types. sys is a C built-in — safe to import before path cleanup.
import sys
import os as _os
_this_dir = _os.path.dirname(_os.path.abspath(__file__))
sys.path = [p for p in sys.path if _os.path.abspath(p) != _this_dir]
del _os, _this_dir

# ── stdlib ────────────────────────────────────────────────────────────────────
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# ── sys.path inserts (exactly 2) ─────────────────────────────────────────────

from loguru import logger
from .types import NormalizedResponse

try:
    from core.config import CONFIG  # type: ignore
except ImportError:
    CONFIG = {}


class ProviderTransport(ABC):
    """Base class for provider-specific format conversion and normalization.

    Subclasses handle exactly one api_mode string (e.g. 'anthropic_messages').
    The transport pipeline is:
        convert_messages() → convert_tools() → build_kwargs() → normalize_response()
    """

    @property
    @abstractmethod
    def api_mode(self) -> str:
        """The api_mode string this transport handles (e.g. 'anthropic_messages')."""
        ...

    @abstractmethod
    def convert_messages(self, messages: List[Dict[str, Any]], **kwargs) -> Any:
        """Convert OpenAI-format messages to provider-native format.

        Returns provider-specific structure (e.g. (system, messages) tuple for
        Anthropic, or the messages list unchanged for chat_completions).
        """
        ...

    @abstractmethod
    def convert_tools(self, tools: List[Dict[str, Any]]) -> Any:
        """Convert OpenAI-format tool definitions to provider-native format.

        Returns provider-specific tool list (e.g. Anthropic input_schema format).
        """
        ...

    @abstractmethod
    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """Build the complete API call kwargs dict.

        This is the primary entry point. It typically calls convert_messages()
        and convert_tools() internally, then adds model-specific config.

        Returns a dict ready to be passed to the provider's SDK client.
        """
        ...

    @abstractmethod
    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """Normalize a raw provider response to the shared NormalizedResponse type.

        This is the only method that returns a transport-layer type.
        """
        ...

    def validate_response(self, response: Any) -> bool:
        """Optional: check if the raw response is structurally valid.

        Returns True if valid, False if the response should be treated as invalid.
        Default implementation always returns True.
        """
        return True

    def extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]:
        """Optional: extract provider-specific cache hit/creation stats.

        Returns dict with 'cached_tokens' and 'creation_tokens', or None.
        Default returns None.
        """
        return None

    def map_finish_reason(self, raw_reason: str) -> str:
        """Optional: map provider-specific stop reason to OpenAI equivalent.

        Default returns the raw reason unchanged. Override for providers
        with different stop reason vocabularies.
        """
        return raw_reason

    async def complete_streaming(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> NormalizedResponse:
        """Stream a completion, collect all chunks, and return NormalizedResponse.

        Default implementation calls build_kwargs and makes a non-streaming
        call via httpx. Subclasses override this for SDK-native streaming.

        Params forwarded to build_kwargs:
            max_tokens: int
            temperature: float
            stream: bool (forced True inside)
        """
        import httpx

        params["stream"] = False  # base impl uses non-stream by default
        kwargs = self.build_kwargs(model, messages, tools, **params)

        base_url = params.get("base_url", "http://localhost:11434/v1")
        api_key = params.get("api_key", "")
        timeout = params.get("timeout", 120.0)

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=kwargs,
                )
                resp.raise_for_status()
                raw = resp.json()
        except Exception as e:
            logger.error(f"[VECTOR][transport:{self.api_mode}] HTTP call failed: {e}")
            from .types import NormalizedResponse as NR
            return NR(content=f"[Transport error: {e}]", tool_calls=None, finish_reason="stop")

        return self.normalize_response(raw)


# ── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    # Verify the ABC cannot be instantiated directly
    try:
        ProviderTransport()  # type: ignore[abstract]
        assert False, "Should not be instantiable"
    except TypeError as _sve:
        logger.debug("[VECTOR][transports.base] expected abstract-class error: {}", _sve)

    # Build a concrete stub to verify the ABC contract
    class _StubTransport(ProviderTransport):
        @property
        def api_mode(self) -> str:
            return "stub"

        def convert_messages(self, messages, **kwargs):
            return messages

        def convert_tools(self, tools):
            return tools

        def build_kwargs(self, model, messages, tools=None, **params):
            return {"model": model, "messages": messages}

        def normalize_response(self, response, **kwargs):
            from .types import NormalizedResponse as NR
            return NR(content="ok", tool_calls=None, finish_reason="stop")

    stub = _StubTransport()
    assert stub.api_mode == "stub"
    assert stub.validate_response(object()) is True
    assert stub.extract_cache_stats(object()) is None
    assert stub.map_finish_reason("tool_calls") == "tool_calls"
    kwargs = stub.build_kwargs("model-x", [{"role": "user", "content": "hi"}])
    assert kwargs["model"] == "model-x"
    nr = stub.normalize_response({})
    assert nr.finish_reason == "stop"

    print("base.py OK")

