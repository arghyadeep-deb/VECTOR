from __future__ import annotations

from core.coding_assistant.core.transcribe.factory import make_transcribe_client
from core.coding_assistant.core.transcribe.transcribe_client_port import (
    TranscribeClientPort,
    TranscribeDone,
    TranscribeError,
    TranscribeEvent,
    TranscribeSessionCreated,
    TranscribeTextDelta,
)

# MistralTranscribeClient removed — VECTOR uses local Whisper (core/voice/stt.py)
class MistralTranscribeClient(TranscribeClientPort):
    """Stub — Mistral cloud STT removed; VECTOR uses local Whisper at core/voice/stt.py."""
    async def transcribe(self, audio: bytes, **kwargs) -> str:
        raise NotImplementedError("Use VECTOR's Whisper STT via core/voice/stt.py")

__all__ = [
    "MistralTranscribeClient",
    "TranscribeClientPort",
    "TranscribeDone",
    "TranscribeError",
    "TranscribeEvent",
    "TranscribeSessionCreated",
    "TranscribeTextDelta",
    "make_transcribe_client",
]
