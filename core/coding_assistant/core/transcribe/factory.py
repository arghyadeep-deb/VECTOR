from __future__ import annotations

from core.coding_assistant.core.config import (
    TranscribeClient,
    TranscribeModelConfig,
    TranscribeProviderConfig,
)
from core.coding_assistant.core.transcribe.transcribe_client_port import TranscribeClientPort

# MistralTranscribeClient stub defined in __init__.py (points to VECTOR's Whisper)
class MistralTranscribeClient(TranscribeClientPort):  # type: ignore[no-redef]
    """Stub — use VECTOR's core/voice/stt.py (Whisper) instead."""
    async def transcribe(self, audio: bytes, **kwargs) -> str:
        raise NotImplementedError("Use core/voice/stt.py")

TRANSCRIBE_CLIENT_MAP: dict[TranscribeClient, type[TranscribeClientPort]] = {
    TranscribeClient.MISTRAL: MistralTranscribeClient
}


def make_transcribe_client(
    provider: TranscribeProviderConfig, model: TranscribeModelConfig
) -> TranscribeClientPort:
    return TRANSCRIBE_CLIENT_MAP[provider.client](provider=provider, model=model)
