from __future__ import annotations

from core.coding_assistant.core.tts.factory import make_tts_client
from core.coding_assistant.core.tts.tts_client_port import TTSClientPort, TTSResult

# MistralTTSClient removed — VECTOR uses local Kokoro TTS
class MistralTTSClient(TTSClientPort):
    """Stub — Mistral cloud TTS removed; VECTOR uses core/voice/tts.py (Kokoro)."""
    async def synthesize(self, text: str, **kwargs) -> TTSResult:
        raise NotImplementedError("Use VECTOR's local Kokoro TTS via core/voice/tts.py")

__all__ = ["MistralTTSClient", "TTSClientPort", "TTSResult", "make_tts_client"]
