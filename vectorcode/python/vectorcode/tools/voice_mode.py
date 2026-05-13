"""Voice mode — push-to-talk audio recording and playback."""

import asyncio
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    _AUDIO = True
except ImportError:
    _AUDIO = False


class VoiceMode:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._recording: Optional[np.ndarray] = None

    async def record(self, duration: float = 5.0) -> str:
        if not _AUDIO: return "sounddevice not installed"
        path = os.path.join(tempfile.gettempdir(), "vector_voice_input.wav")
        recording = sd.rec(int(duration * self.sample_rate), samplerate=self.sample_rate, channels=1)
        sd.wait()
        sf.write(path, recording, self.sample_rate)
        self._recording = recording
        return path

    async def play(self, audio_path: str):
        if not _AUDIO: return
        data, sr = sf.read(audio_path)
        sd.play(data, sr)
        sd.wait()

    async def transcribe(self, audio_path: str, provider: str = "local") -> str:
        from tools.stt_tool import transcribe_audio
        result = await transcribe_audio(audio_path, provider=provider)
        return result.get("text", "") if result.get("success") else result.get("error", "transcription failed")
