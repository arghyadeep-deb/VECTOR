from __future__ import annotations

__all__ = [
    "create_narrator_backend",
    "NARRATOR_MODEL",
]


import os

from core.coding_assistant.core.config import ModelConfig, VectorCAConfig
from core.coding_assistant.core.llm.backend.factory import BACKEND_FACTORY
from core.coding_assistant.core.llm.types import BackendLike

NARRATOR_MODEL = ModelConfig(
    name="vector-coding-assistant-cli-fast",
    provider="mistral",
    alias="mistral-small",
    input_price=0.1,
    output_price=0.3,
)


def create_narrator_backend(
    config: VectorCAConfig,
) -> tuple[BackendLike, ModelConfig] | None:
    try:
        provider = config.get_provider_for_model(NARRATOR_MODEL)
    except ValueError:
        return None
    if provider.api_key_env_var and not os.getenv(provider.api_key_env_var):
        return None
    backend = BACKEND_FACTORY[provider.backend](
        provider=provider, timeout=config.api_timeout
    )
    return backend, NARRATOR_MODEL
