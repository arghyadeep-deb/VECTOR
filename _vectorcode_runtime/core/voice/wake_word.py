import sys
import asyncio
from pathlib import Path

import numpy as np
from loguru import logger
from core.config import CONFIG

_KWS_PHRASES = ["vector", "hey vector", "okay vector", "hey vecto"]


class WakeWordDetector:
    def __init__(self):
        self._model = None
        self._threshold = CONFIG.get("voice", {}).get("wake_threshold", 0.5)
        self._wake_phrase = CONFIG.get("voice", {}).get("wake_phrase", "hey_vector")
        self._sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
        self._frame_size = 512
        self._use_whisper_kws = False  # fallback when openwakeword unavailable
        self._active_model_name = ""
        self._init_model()

    def _init_model(self):
        _root = __file__  # resolved below
        import os as _os
        _root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
        self._custom_model_path = Path(_root) / "models" / "wake" / f"{self._wake_phrase}.onnx"
        try:
            import openwakeword
            from openwakeword.model import Model
            if self._custom_model_path.exists():
                self._model = Model(
                    wakeword_models=[str(self._custom_model_path)],
                    inference_framework="onnx",
                )
                logger.info(f"[VECTOR][wake] Custom model loaded: {self._custom_model_path}")
            else:
                self._model = Model(wakeword_models=[self._wake_phrase], inference_framework="onnx")
                logger.info(f"[VECTOR][wake] openWakeWord built-in model ready (phrase='{self._wake_phrase}')")
            self._active_model_name = self._wake_phrase
            return
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        # Custom model not available — Whisper KWS: user can say "Hey Vector" or "Vector"
        logger.info(
            f"[VECTOR][wake] Custom model '{self._wake_phrase}.onnx' not found. "
            f"Using Whisper keyword detection. Say 'Hey Vector' or 'Vector' to activate. "
            f"To train custom wake word: https://github.com/dscripka/openWakeWord#training"
        )
        self._model = None
        self._use_whisper_kws = True

    def is_wake_word(self, audio_frame: np.ndarray) -> bool:
        """Per-frame check — only used in the openwakeword path."""
        if self._use_whisper_kws or self._model is None:
            return False
        try:
            if audio_frame.dtype != np.int16:
                audio_frame = (audio_frame * 32767).astype(np.int16)
            prediction = self._model.predict(audio_frame)
            score = prediction.get(self._active_model_name, 0.0)
            return float(score) > self._threshold
        except Exception as e:
            logger.error(f"[VECTOR][wake] is_wake_word error: {e}")
            return False

    # Maps detected phrase → conversation mode
    _PHRASE_MODES = {
        "vector think": "deep_think",
        "vector private": "private",
        "hey vector": "conversation",
        "okay vector": "conversation",
        "hey vecto": "conversation",
        "vector": "conversation",
    }

    async def listen_for_wake(self) -> str | None:
        """Block until wake word/phrase detected. Returns the mode string or None on error."""
        if self._use_whisper_kws:
            return await self._listen_whisper_kws()
        return await self._listen_openwakeword()

    async def _listen_openwakeword(self) -> str | None:
        """Frame-by-frame openwakeword detection."""
        try:
            import sounddevice as sd
            logger.info(f"[VECTOR][wake] Listening ({self._active_model_name})...")
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self._frame_size,
            ) as stream:
                while True:
                    frame, _ = await asyncio.to_thread(stream.read, self._frame_size)
                    if self.is_wake_word(frame.flatten()):
                        logger.info("[VECTOR][wake] Wake word detected!")
                        return "conversation"
                    await asyncio.sleep(0)
        except Exception as e:
            logger.error(f"[VECTOR][wake] _listen_openwakeword error: {e}")
            return None

    async def _listen_whisper_kws(self) -> str | None:
        """Whisper KWS: record 2s chunks, transcribe, detect phrase and map to mode."""
        try:
            import sounddevice as sd
            from core.voice.stt import WhisperSTT
            stt = WhisperSTT()
            chunk_sec = 2.0
            logger.info(f"[VECTOR][wake] Whisper KWS — say 'Hey Vector', 'Vector Think', or 'Vector Private'")
            while True:
                audio = await asyncio.to_thread(
                    sd.rec,
                    int(chunk_sec * self._sample_rate),
                    samplerate=self._sample_rate,
                    channels=1,
                    dtype="float32",
                )
                await asyncio.to_thread(sd.wait)
                audio_flat = audio.flatten()
                rms = float(np.sqrt(np.mean(audio_flat ** 2)))
                # 0.0012 (was 0.004): laptop mic arrays at default Windows input
                # levels produce speech at rms ~0.003 — the old gate classified
                # the owner's actual voice as silence, so wake NEVER triggered.
                if rms < 0.0012:
                    await asyncio.sleep(0.1)
                    continue
                # Normalize quiet audio so Whisper gets a usable signal level.
                peak = float(np.max(np.abs(audio_flat)))
                if 0 < peak < 0.3:
                    audio_flat = audio_flat * (0.9 / peak)
                try:
                    text = stt.transcribe(audio_flat, self._sample_rate).lower().strip()
                    if text:
                        for phrase, mode in self._PHRASE_MODES.items():
                            if phrase in text:
                                logger.info(f"[VECTOR][wake] KWS triggered: '{text}' → mode={mode}")
                                return mode
                except Exception:
                    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
                await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"[VECTOR][wake] _listen_whisper_kws error: {e}")
            return None

    async def train_wake_word(self, n_samples: int = 10) -> dict:
        """
        Gap 9: Record n_samples of 'Hey Vector' and train a custom openWakeWord model.
        Saves the .onnx file to the expected path so _init_model() picks it up on restart.
        Returns {"status": "ok", "model_path": "..."} or {"status": "error", "error": "..."}.
        """
        import sounddevice as sd
        import soundfile as sf
        import tempfile
        import subprocess
        from pathlib import Path

        # Task B.4 (governor-wiring-and-ambient-perception.md): this used to
        # write to models/wake_word/, but _init_model()'s read path (and the
        # already-correct scripts/train_wake_word.py CLI) is models/wake/ —
        # a trained model from this method would have been silently
        # invisible to _init_model() forever. Aligned to the same folder
        # the 15 existing recorded samples already live in.
        model_dir = self._custom_model_path.parent
        model_dir.mkdir(parents=True, exist_ok=True)
        samples_dir = model_dir / "samples"
        samples_dir.mkdir(exist_ok=True)
        model_out = model_dir / f"{self._wake_phrase}.onnx"

        logger.info(f"[VECTOR][wake] Training '{self._wake_phrase}' — recording {n_samples} samples")
        recorded: list[Path] = []

        for i in range(n_samples):
            logger.info(f"[VECTOR][wake] Sample {i+1}/{n_samples} — say '{self._wake_phrase}' now...")
            try:
                audio = await asyncio.to_thread(
                    sd.rec,
                    int(1.5 * self._sample_rate),
                    samplerate=self._sample_rate,
                    channels=1,
                    dtype="int16",
                )
                await asyncio.to_thread(sd.wait)
                sample_path = samples_dir / f"sample_{i:03d}.wav"
                await asyncio.to_thread(sf.write, str(sample_path), audio, self._sample_rate)
                recorded.append(sample_path)
                logger.info(f"[VECTOR][wake] Saved {sample_path.name}")
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"[VECTOR][wake] Sample {i+1} failed: {e}")

        if len(recorded) < 3:
            return {"status": "error", "error": f"Only {len(recorded)} samples recorded (need ≥3)"}

        # Run openWakeWord training script
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "python", "-m", "openwakeword.train",
                    "--positive_reference_clips", str(samples_dir),
                    "--output_dir", str(model_dir),
                    "--model_name", self._wake_phrase,
                ],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                return {"status": "error", "error": result.stderr[:500]}
        except Exception as e:
            return {"status": "error", "error": str(e)}

        if model_out.exists():
            # Reload the model without restarting
            self._init_model()
            logger.info(f"[VECTOR][wake] Custom model trained and loaded: {model_out}")
            return {"status": "ok", "model_path": str(model_out), "samples": len(recorded)}

        return {"status": "error", "error": "Training completed but .onnx not found"}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    detector = WakeWordDetector()
    silent_frame = np.zeros(512, dtype=np.int16)
    result = detector.is_wake_word(silent_frame)
    model_ok = detector._model is not None or detector._use_whisper_kws
    method = "whisper_kws" if detector._use_whisper_kws else f"openwakeword({detector._active_model_name})"
    print(f"✅ wake_word OK (method={method})" if model_ok else "âŒ FAILED — no detection method available")
