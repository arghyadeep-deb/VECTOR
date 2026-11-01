from __future__ import annotations

__all__ = [
    "make_transcribe_client",
    "MistralTranscribeClient",
]

from collections.abc import AsyncIterator

from loguru import logger

from core.coding_assistant.core.config import (
    TranscribeClient,
    TranscribeModelConfig,
    TranscribeProviderConfig,
)
from core.coding_assistant.core.transcribe.transcribe_client_port import (
    TranscribeClientPort,
    TranscribeDone,
    TranscribeEvent,
    TranscribeSessionCreated,
)

# MistralTranscribeClient stub defined in __init__.py (points to VECTOR's Whisper)
class MistralTranscribeClient(TranscribeClientPort):  # type: ignore[no-redef]
    """Stub — use VECTOR's core/voice/stt.py (Whisper) instead."""
    def __init__(
        self, provider: TranscribeProviderConfig, model: TranscribeModelConfig
    ) -> None:
        self._provider = provider
        self._model = model

    async def transcribe(
        self, audio_stream: AsyncIterator[bytes]
    ) -> AsyncIterator[TranscribeEvent]:
        logger.warning(
            "MistralTranscribeClient stub called — STT not available. "
            "Use VECTOR's Whisper via core/voice/stt.py instead. "
            "provider=%s, model=%s", self._provider, self._model,
        )
        yield TranscribeDone()

    async def close(self) -> None:
        from loguru import logger
        logger.debug("[VECTOR][factory] close called (no-op)")

TRANSCRIBE_CLIENT_MAP: dict[TranscribeClient, type[TranscribeClientPort]] = {
    TranscribeClient.MISTRAL: MistralTranscribeClient
}


def make_transcribe_client(
    provider: TranscribeProviderConfig, model: TranscribeModelConfig
) -> TranscribeClientPort:
    return TRANSCRIBE_CLIENT_MAP[provider.client](provider=provider, model=model)
