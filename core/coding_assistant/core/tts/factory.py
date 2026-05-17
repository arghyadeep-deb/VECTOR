from __future__ import annotations

from core.coding_assistant.core.config import TTSClient, TTSModelConfig, TTSProviderConfig
from core.coding_assistant.core.tts.tts_client_port import TTSClientPort
from core.coding_assistant.core.tts import MistralTTSClient  # stub pointing to Kokoro

TTS_CLIENT_MAP: dict[TTSClient, type[TTSClientPort]] = {
    TTSClient.MISTRAL: MistralTTSClient,
}


def make_tts_client(
    provider: TTSProviderConfig, model: TTSModelConfig
) -> TTSClientPort:
    return TTS_CLIENT_MAP[provider.client](provider=provider, model=model)
