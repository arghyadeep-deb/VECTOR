from __future__ import annotations

__all__ = [
    "APIAdapter",
    "PreparedRequest",
]


from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, Protocol

from core.coding_assistant.core.types import AvailableTool, LLMChunk, LLMMessage, StrToolChoice

if TYPE_CHECKING:
    from core.coding_assistant.core.config import ProviderConfig


class PreparedRequest(NamedTuple):
    endpoint: str
    headers: dict[str, str]
    body: bytes
    base_url: str = ""


class APIAdapter(Protocol):
    endpoint: ClassVar[str]

    def prepare_request(
        self,
        *,
        model_name: str,
        messages: Sequence[LLMMessage],
        temperature: float,
        tools: list[AvailableTool] | None,
        max_tokens: int | None,
        tool_choice: StrToolChoice | AvailableTool | None,
        enable_streaming: bool,
        provider: ProviderConfig,
        api_key: str | None = None,
        thinking: str = "off",
    ) -> PreparedRequest: ...

    def parse_response(
        self, data: dict[str, Any], provider: ProviderConfig
    ) -> LLMChunk: ...
