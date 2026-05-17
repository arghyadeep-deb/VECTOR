from __future__ import annotations

from core.coding_assistant.core.config import TTSClient, TTSModelConfig, TTSProviderConfig
from core.coding_assistant.core.tts.tts_client_port import TTSClientPort


class MistralTTSClient(TTSClientPort):
    """Stub — Mistral cloud TTS removed. Use VECTOR's local Kokoro at core/voice/tts.py."""
    async def synthesize(self, text: str, **kwargs) -> object:
        raise NotImplementedError("Use VECTOR's Kokoro TTS via core/voice/tts.py")


TTS_CLIENT_MAP: dict[TTSClient, type[TTSClientPort]] = {
    TTSClient.MISTRAL: MistralTTSClient,
}


def make_tts_client(
    provider: TTSProviderConfig, model: TTSModelConfig
) -> TTSClientPort:
    return TTS_CLIENT_MAP.get(provider.client, MistralTTSClient)(
        provider=provider, model=model
    )
