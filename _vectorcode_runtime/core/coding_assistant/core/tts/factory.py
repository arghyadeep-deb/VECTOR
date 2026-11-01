from __future__ import annotations

__all__ = [
    "make_tts_client",
    "MistralTTSClient",
]


from loguru import logger

from core.coding_assistant.core.config import TTSClient, TTSModelConfig, TTSProviderConfig
from core.coding_assistant.core.tts.tts_client_port import TTSClientPort, TTSResult


class MistralTTSClient(TTSClientPort):
    """Stub — Mistral cloud TTS removed. Use VECTOR's local Kokoro at core/voice/tts.py."""
    def __init__(self, provider: TTSProviderConfig, model: TTSModelConfig) -> None:
        self._provider = provider
        self._model = model

    async def speak(self, text: str) -> TTSResult:
        logger.warning(
            "MistralTTSClient stub called — TTS not available. "
            "Use VECTOR's Kokoro TTS via core/voice/tts.py instead. "
            "provider=%s, model=%s", self._provider, self._model,
        )
        return TTSResult(audio_data=b"")

    async def close(self) -> None:
        from loguru import logger
        logger.debug("[VECTOR][factory] close called (no-op)")


TTS_CLIENT_MAP: dict[TTSClient, type[TTSClientPort]] = {
    TTSClient.MISTRAL: MistralTTSClient,
}


def make_tts_client(
    provider: TTSProviderConfig, model: TTSModelConfig
) -> TTSClientPort:
    return TTS_CLIENT_MAP.get(provider.client, MistralTTSClient)(
        provider=provider, model=model
    )
