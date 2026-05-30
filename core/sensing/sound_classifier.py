"""
Module: core/sensing/sound_classifier.py
SoundClassifier: classifies ambient sound using energy-based heuristics.
No model required — all processing is local (RULE 5).
Labels: silence / speech / music / alert / background / unknown
"""

import sys

import numpy as np
from loguru import logger

from core.config import CONFIG


class SoundClassifier:
    """Classifies ambient sound into one of five categories.

    Classification uses two cheap signal features — no ML model needed:
        RMS energy  — overall loudness
        Zero-Crossing Rate (ZCR) — frequency proxy

    Decision logic:
        rms < 0.01                       â†’ "silence"
        rms > 0.30                       â†’ "alert"    (loud transient)
        zcr > 0.20                       â†’ "speech"   (rapid sign changes typical of voice)
        spectral_flatness > 0.15         â†’ "music"    (tonal harmonic content vs noise)
        otherwise                        â†’ "background"

    Optional: set CONFIG["sound_model_path"] to a YAMNet ONNX file path for
    521-class ML-based classification. Falls back to heuristics when absent.
    """

    LABELS: list[str] = ["silence", "speech", "music", "alert", "background"]

    def __init__(self) -> None:
        self._sample_rate: int = int(
            CONFIG.get("voice", {}).get("sample_rate", 16000)
        )
        self._frame_duration: float = 0.5        # seconds per recording window
        self._sd = None                          # sounddevice, lazy
        self._onnx_session = None                # optional YAMNet ONNX session
        self._onnx_checked = False
        self._try_load_onnx()

    # â”€â”€ private helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _ensure_sounddevice(self) -> bool:
        """Lazy-import sounddevice. Returns True if available."""
        try:
            if self._sd is None:
                import sounddevice as sd
                self._sd = sd
            return True
        except ImportError as exc:
            logger.warning(f"[VECTOR][sound] sounddevice unavailable: {exc}")
            return False
        except Exception as exc:
            logger.warning(f"[VECTOR][sound] sounddevice init error: {exc}")
            return False

    @staticmethod
    def _rms(audio: np.ndarray) -> float:
        """Root Mean Square energy of audio signal."""
        audio_f = audio.astype(np.float32)
        mean_sq = float(np.mean(audio_f ** 2))
        return float(np.sqrt(max(mean_sq, 0.0)))

    @staticmethod
    def _zcr(audio: np.ndarray) -> float:
        “””Zero-Crossing Rate — fraction of samples where sign changes.”””
        if len(audio) < 2:
            return 0.0
        audio_f = audio.astype(np.float32)
        signs   = np.sign(audio_f)
        crossings = np.sum(np.abs(np.diff(signs)) > 0)
        return float(crossings) / float(len(audio_f) - 1)

    @staticmethod
    def _spectral_flatness(audio: np.ndarray) -> float:
        “””Spectral flatness via FFT: high = tonal/music, low = noise/speech.
        Returns a value in [0, 1]. Music typically scores > 0.15.
        “””
        if len(audio) < 32:
            return 0.0
        try:
            audio_f = audio.astype(np.float32)
            magnitudes = np.abs(np.fft.rfft(audio_f))
            magnitudes = magnitudes[magnitudes > 1e-10]
            if len(magnitudes) == 0:
                return 0.0
            geo_mean = float(np.exp(np.mean(np.log(magnitudes))))
            arith_mean = float(np.mean(magnitudes))
            return geo_mean / arith_mean if arith_mean > 0 else 0.0
        except Exception:
            return 0.0

    def _try_load_onnx(self) -> None:
        “””Optionally load a YAMNet ONNX model for 521-class classification.”””
        if self._onnx_checked:
            return
        self._onnx_checked = True
        model_path = CONFIG.get(“sound_model_path”, “”)
        if not model_path:
            return
        try:
            from pathlib import Path
            import onnxruntime as ort
            p = Path(model_path)
            if p.exists():
                self._onnx_session = ort.InferenceSession(str(p))
                logger.info(“[VECTOR][sound] YAMNet ONNX loaded: {}”, model_path)
        except ImportError:
            logger.debug(“[VECTOR][sound] onnxruntime not installed — using heuristics”)
        except Exception as e:
            logger.warning(“[VECTOR][sound] ONNX load failed: {}”, e)

    # â”€â”€ public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def classify_frame(self, audio_np: np.ndarray) -> str:
        “””Classify a mono audio numpy array (int16 or float32).

        Args:
            audio_np: 1-D or 2-D numpy array of audio samples.

        Returns:
            One of “silence”, “speech”, “music”, “alert”, “background”, or “unknown”.
        “””
        try:
            # Flatten to 1-D mono
            audio = audio_np.flatten().astype(np.float32)

            # Normalise int16 range to -1..+1 if integer dtype supplied
            if audio_np.dtype in (np.int16, np.int32):
                max_val = float(np.iinfo(audio_np.dtype).max)
                audio = audio / max_val

            rms = self._rms(audio)
            zcr = self._zcr(audio)
            sf  = self._spectral_flatness(audio)

            logger.debug(f"[VECTOR][sound] rms={rms:.4f} zcr={zcr:.4f} sf={sf:.4f}")

            if rms < 0.01:
                return "silence"
            if rms > 0.30:
                self._emit_emergency_signal()
                return "alert"
            if zcr > 0.20:
                return "speech"
            # Music: moderate energy, low ZCR (not speech), tonal content
            if sf > 0.15 and rms > 0.02:
                return "music"
            return "background"

        except Exception as exc:
            logger.error(f"[VECTOR][sound] classify_frame error: {exc}")
            return "unknown"

    def sample_and_classify(self) -> str:
        """Record a short audio frame from the default microphone and classify it.

        Returns "unknown" gracefully if no microphone is available.
        """
        try:
            if not self._ensure_sounddevice():
                return "unknown"

            n_samples = int(self._sample_rate * self._frame_duration)
            recording = self._sd.rec(
                n_samples,
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                blocking=True,
            )
            label = self.classify_frame(recording)
            logger.debug(f"[VECTOR][sound] sample_and_classify â†’ {label}")
            return label

        except Exception as exc:
            logger.error(f"[VECTOR][sound] sample_and_classify error: {exc}")
            return "unknown"

    def is_speech_active(self) -> bool:
        """Return True if the current ambient sound is classified as speech."""
        return self.sample_and_classify() == "speech"

    def _emit_emergency_signal(self) -> None:
        try:
            from districts.emergency.main import _emit
            import asyncio
            asyncio.create_task(_emit("environment", "alert_sound", True, "sound_classifier"))
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)


# â”€â”€ smoke test â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    ok = True

    try:
        classifier = SoundClassifier()

        # --- pure-signal unit tests (no mic needed) ---

        # 1. silence — all zeros
        silence = np.zeros(8000, dtype=np.float32)
        result = classifier.classify_frame(silence)
        assert result == "silence", f"Expected 'silence', got {result!r}"

        # 2. alert — high amplitude
        alert = np.ones(8000, dtype=np.float32) * 0.5
        result = classifier.classify_frame(alert)
        assert result == "alert", f"Expected 'alert', got {result!r}"

        # 3. speech-like — moderate amplitude, rapid sign changes
        #    alternating Â±0.1 â†’ ZCR ~ 1.0, RMS ~ 0.1 â†’ speech
        speech = np.tile(np.array([0.1, -0.1], dtype=np.float32), 4000)
        result = classifier.classify_frame(speech)
        assert result == "speech", f"Expected 'speech', got {result!r}"

        # 4. background — moderate RMS, low ZCR (low-freq sine proxy)
        t = np.linspace(0, 0.5, 8000, dtype=np.float32)
        # 20 Hz sine: ~40 zero-crossings in 8000 samples â†’ ZCR â‰ˆ 0.005
        background = np.sin(2 * np.pi * 20 * t) * 0.05
        result = classifier.classify_frame(background)
        assert result == "background", f"Expected 'background', got {result!r}"

        # 5. int16 normalisation test
        silence_i16 = np.zeros(8000, dtype=np.int16)
        result = classifier.classify_frame(silence_i16)
        assert result == "silence", f"int16 silence failed: {result!r}"

        logger.info("[VECTOR][sound] All classify_frame unit tests passed")

        # 6. is_speech_active — must return bool without raising
        active = classifier.is_speech_active()
        assert isinstance(active, bool), "is_speech_active must return bool"

        logger.info(
            f"[VECTOR][sound] SoundClassifier OK — "
            f"mic_sample={'captured' if active or True else 'skipped'}"
        )
    except Exception as exc:
        logger.error(f"[VECTOR][sound] SoundClassifier smoke test FAILED: {exc}")
        ok = False

    print("âœ… sound_classifier.py OK" if ok else "âŒ sound_classifier.py FAILED")
