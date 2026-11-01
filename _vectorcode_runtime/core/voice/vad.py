import sys
import time

import numpy as np
from loguru import logger

from core.config import CONFIG


class VoiceActivityDetector:
    SILENCE = "SILENCE"
    SPEECH = "SPEECH"

    def __init__(self):
        voice_cfg = CONFIG.get("voice", {})
        self._energy_threshold = voice_cfg.get("vad_threshold", 0.02)
        self._min_speech_ms = voice_cfg.get("min_speech_duration_ms", 100)
        self._min_silence_ms = voice_cfg.get("min_silence_duration_ms", 500)
        self._state = self.SILENCE
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._total_speech_ms = 0.0
        self._total_silence_ms = 0.0

    @property
    def state(self) -> str:
        return self._state

    def is_speech(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> bool:
        if len(audio_chunk) == 0:
            return False
        rms = float(np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2)))
        frame_ms = (len(audio_chunk) / sample_rate) * 1000.0

        if rms > self._energy_threshold:
            self._silence_ms = 0.0
            if self._state == self.SILENCE:
                self._speech_ms += frame_ms
                if self._speech_ms >= self._min_speech_ms:
                    self._state = self.SPEECH
                    self._speech_ms = 0.0
                    self._total_speech_ms += frame_ms
                    logger.debug(f"[VECTOR][vad] SILENCE -> SPEECH (rms={rms:.4f})")
                    return True
                return False
            self._total_speech_ms += frame_ms
            return True
        else:
            self._speech_ms = 0.0
            if self._state == self.SPEECH:
                self._silence_ms += frame_ms
                if self._silence_ms >= self._min_silence_ms:
                    self._state = self.SILENCE
                    self._silence_ms = 0.0
                    logger.debug(f"[VECTOR][vad] SPEECH -> SILENCE")
                else:
                    self._total_speech_ms += frame_ms
                    return True
            else:
                self._total_silence_ms += frame_ms
            return False

    def speech_duration(self) -> float:
        return self._total_speech_ms

    def silence_duration(self) -> float:
        return self._total_silence_ms

    def reset(self) -> None:
        self._state = self.SILENCE
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._total_speech_ms = 0.0
        self._total_silence_ms = 0.0
        logger.debug("[VECTOR][vad] reset")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    vad = VoiceActivityDetector()
    sr = 16000
    silence = np.zeros(int(sr * 0.3), dtype=np.float32)
    speech = np.random.rand(int(sr * 0.3)).astype(np.float32) * 0.1
    results = [vad.is_speech(silence, sr), vad.is_speech(speech, sr)]
    logger.info(f"[VECTOR][vad] test results: {results}")
    print(f"\u2705 vad OK (speech_dur={vad.speech_duration():.0f}ms, sil_dur={vad.silence_duration():.0f}ms)")
