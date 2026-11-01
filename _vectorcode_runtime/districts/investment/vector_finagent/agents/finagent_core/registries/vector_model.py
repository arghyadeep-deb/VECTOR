"""
VectorProviderModel - Agno-compatible model adapter backed by VECTOR's provider_client.

Routes all LLM calls through core/inference/provider_client.py:
  Ollama first (local, free, private) → cloud API keys as fallback.

Model name mapping (OpenAI names → VECTOR equivalents):
  gpt-4 / gpt-4o / gpt-4-turbo / gpt-4o-mini → vector-focus (fast, real-time)
  gpt-4-32k / o1 / o1-preview                 → vector-reasoning (long-context overnight)
  gpt-3.5-turbo                               → vector-focus (fast, real-time)
  o1-mini / gpt-4o-mini                       → vector-focus
  (default)                                   → vector-focus
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# OpenAI → VECTOR model name map
# ---------------------------------------------------------------------------
OPENAI_TO_VECTOR: Dict[str, str] = {
    # gpt-4 family → vector-reasoning (high-quality, large-context)
    "gpt-4":              "vector-reasoning",
    "gpt-4o":             "vector-reasoning",
    "gpt-4-turbo":        "vector-reasoning",
    "gpt-4-32k":          "vector-reasoning",
    "gpt-4-32k-0613":     "vector-reasoning",
    "gpt-4-turbo-preview":"vector-reasoning",
    # o1 / reasoning family → vector-reasoning (slow deep tasks)
    "o1":                 "vector-reasoning",
    "o1-preview":         "vector-reasoning",
    # fast / mini → vector-focus (real-time, permanent VRAM)
    "gpt-4o-mini":        "vector-focus",
    "gpt-3.5-turbo":      "vector-focus",
    "gpt-3.5-turbo-16k":  "vector-focus",
    "gpt-3.5-turbo-0125": "vector-focus",
    "o1-mini":            "vector-focus",
}

DEFAULT_VECTOR_MODEL = "vector-focus"


def map_model_name(model_id: Optional[str]) -> str:
    """Translate an OpenAI model name (or any alias) to a VECTOR model name.

    If the name is already a known VECTOR model it is returned unchanged.
    Falls back to DEFAULT_VECTOR_MODEL when no mapping is found.
    """
    if not model_id:
        return DEFAULT_VECTOR_MODEL
    # Already a VECTOR model name
    if model_id.startswith("vector-"):
        return model_id
    return OPENAI_TO_VECTOR.get(model_id, DEFAULT_VECTOR_MODEL)


# ---------------------------------------------------------------------------
# Agno Model subclass
# ---------------------------------------------------------------------------

try:
    from agno.models.base import Model
    from agno.models.message import Message
    from agno.models.response import ModelResponse
    _AGNO_AVAILABLE = True
except ImportError:
    _AGNO_AVAILABLE = False
    # Provide minimal stubs so the registry can still import without agno
    class Model:  # type: ignore[no-redef]
        pass
    class Message:  # type: ignore[no-redef]
        pass
    class ModelResponse:  # type: ignore[no-redef]
        def __init__(self, content="", role="assistant"):
            self.content = content
            self.role = role


@dataclass
class VectorProviderModel(Model):
    """
    Agno-compatible LLM model that routes all calls through
    VECTOR's core/inference/provider_client.py.

    Supports the full Agno Model interface used by AgnoAgent:
      response(), invoke(), ainvoke(), invoke_stream(), ainvoke_stream()
    """

    id: str = DEFAULT_VECTOR_MODEL
    name: str = "VectorProviderModel"
    provider: str = "VECTOR"

    # Optional overrides (provider_client uses its own routing when None)
    _provider_override: Optional[str] = field(default=None, repr=False)
    temperature: float = 0.7
    max_tokens: int = 4096

    def __post_init__(self):
        # Translate OpenAI model names to VECTOR equivalents
        self.id = map_model_name(self.id)

    # ------------------------------------------------------------------
    # Core call helper
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_legacy_event_loop() -> None:
        """
        Keep sync orchestration using get_event_loop() compatible with Python 3.10+.

        ``_sync_call`` runs inside a worker thread (via ``loop.run_in_executor`` in
        the calling district agents). Worker threads never get an event loop set
        on them automatically — ``asyncio.get_event_loop()`` raises
        ``RuntimeError: There is no current event loop in thread '...'`` there.
        Mirrors the established house pattern in core/city/agent_base.py.
        """
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def _sync_call(self, messages: List[Any]) -> str:
        """Synchronous wrapper around provider_client.chat()."""
        try:
            from core.inference.provider_client import ProviderClient
        except ImportError:
            logger.warning(
                "[VECTOR][VectorProviderModel] provider_client unavailable — "
                "falling back to empty response"
            )
            return "[VECTOR provider_client not available]"

        msg_dicts = self._messages_to_dicts(messages)
        client = ProviderClient()

        try:
            self._ensure_legacy_event_loop()
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Inside an already-running event loop (e.g. Jupyter / Agno async)
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        asyncio.run,
                        client.chat(
                            msg_dicts,
                            model=self.id,
                            provider=self._provider_override,
                            temperature=self.temperature,
                            max_tokens=self.max_tokens,
                        ),
                    )
                    result = future.result(timeout=120)
            else:
                result = loop.run_until_complete(
                    client.chat(
                        msg_dicts,
                        model=self.id,
                        provider=self._provider_override,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                    )
                )
            return result.content
        except Exception as e:
            logger.error("[VECTOR][VectorProviderModel] call failed: {}", e)
            return f"[VECTOR provider_client error: {e}]"

    async def _async_call(self, messages: List[Any]) -> str:
        """Async call through provider_client."""
        try:
            from core.inference.provider_client import ProviderClient
        except ImportError:
            return "[VECTOR provider_client not available]"

        msg_dicts = self._messages_to_dicts(messages)
        client = ProviderClient()
        try:
            result = await client.chat(
                msg_dicts,
                model=self.id,
                provider=self._provider_override,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return result.content
        except Exception as e:
            logger.error("[VECTOR][VectorProviderModel] async call failed: {}", e)
            return f"[VECTOR provider_client error: {e}]"

    # ------------------------------------------------------------------
    # Agno Model interface
    # ------------------------------------------------------------------

    def response(
        self,
        messages: List[Any],
        response_format=None,
        tools=None,
        tool_choice=None,
        tool_call_limit=None,
        run_response=None,
        send_media_to_model: bool = True,
        compression_manager=None,
        **kwargs,
    ) -> "ModelResponse":
        content = self._sync_call(messages)
        return ModelResponse(content=content, role="assistant")

    def invoke(self, *args, **kwargs) -> "ModelResponse":
        messages = args[0] if args else kwargs.get("messages", [])
        content = self._sync_call(messages)
        return ModelResponse(content=content, role="assistant")

    async def ainvoke(self, *args, **kwargs) -> "ModelResponse":
        messages = args[0] if args else kwargs.get("messages", [])
        content = await self._async_call(messages)
        return ModelResponse(content=content, role="assistant")

    def invoke_stream(self, *args, **kwargs) -> Iterator["ModelResponse"]:
        yield self.invoke(*args, **kwargs)

    async def ainvoke_stream(self, *args, **kwargs):
        result = await self.ainvoke(*args, **kwargs)
        yield result

    def _parse_provider_response(self, response: Any, **kwargs) -> "ModelResponse":
        return ModelResponse(content=str(response) if response else "", role="assistant")

    def _parse_provider_response_delta(self, response: Any) -> "ModelResponse":
        return ModelResponse(content=str(response) if response else "", role="assistant")

    def get_provider(self) -> str:
        return "VECTOR"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _messages_to_dicts(messages: List[Any]) -> List[Dict[str, str]]:
        """Convert Agno Message objects or plain dicts to provider_client format."""
        result = []
        for msg in messages:
            if isinstance(msg, dict):
                result.append({"role": msg.get("role", "user"), "content": str(msg.get("content", ""))})
            else:
                # Agno Message object
                content = getattr(msg, "content", "") or ""
                if isinstance(content, list):
                    # Multi-modal content blocks — extract text parts
                    parts = [
                        p.get("text", "")
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    content = "\n".join(parts) if parts else str(content)
                role = getattr(msg, "role", "user") or "user"
                result.append({"role": str(role), "content": str(content).strip()})
        return result


if __name__ == "__main__":
    # Real test — no mocks
    model = VectorProviderModel(id="gpt-4o")
    assert model.id == "vector-reasoning", f"Expected vector-reasoning, got {model.id}"

    model2 = VectorProviderModel(id="gpt-3.5-turbo")
    assert model2.id == "vector-focus", f"Expected vector-focus, got {model2.id}"

    model3 = VectorProviderModel(id="vector-coder")
    assert model3.id == "vector-coder", f"Expected vector-coder unchanged, got {model3.id}"

    print("OK vector_model.py")
