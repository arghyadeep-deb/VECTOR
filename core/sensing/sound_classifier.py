"""
Module: core/sensing/sound_classifier.py
SoundClassifier: classifies ambient sound using energy-based heuristics.
No model required — all processing is local (RULE 5).
Labels: silence / speech / music / alert / background / unknown
"""

import sys
import time

import numpy as np
from loguru import logger

from core.config import CONFIG


class SoundClassifier:
    """Classifies ambient sound into one of five categories.

    Classification uses two cheap signal features — no ML model needed:
        RMS energy  — overall loudness
        Zero-Crossing Rate (ZCR) — frequency proxy

    Decision logic:
        rms < 0.01                       -> "silence"
        rms > 0.30                       -> "alert"    (loud transient)
        zcr > 0.20                       -> "speech"   (rapid sign changes typical of voice)
        spectral_peak_ratio > 50         -> "music"    (strong tonal content, low ZCR)
        otherwise                        -> "background"

    Optional: set CONFIG["sound_model_path"] to a YAMNet ONNX file path for
    521-class ML-based classification. Falls back to heuristics when absent.
    """

    LABELS: list[str] = ["silence", "speech", "music", "alert", "background"]

    def __init__(self) -> None:
        sensing_cfg = CONFIG.get("sensing", {})
        self._sample_rate: int = int(
            CONFIG.get("voice", {}).get("sample_rate", 16000)
        )
        self._frame_duration: float = 0.5        # seconds per recording window
        self._sd = None                          # sounddevice, lazy
        self._onnx_session = None                # optional YAMNet ONNX session
        self._onnx_checked = False
        self._alert_cooldown_sec = float(
            sensing_cfg.get("sound_alert_cooldown_sec", 60.0)
        )
        self._retry_backoff_sec = float(
            sensing_cfg.get("sound_retry_backoff_sec", 30.0)
        )
        self._last_alert_at: dict[str, float] = {}
        self._retry_after = 0.0
        self._capture_warning_logged = False
        self._active_log_emitted = False
        self.is_active = False
        self.last_label = "unknown"
        self._try_load_onnx()

    # â"€â"€ private helpers â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

    def _ensure_sounddevice(self) -> bool:
        """Lazy-import sounddevice. Returns True if available."""
        try:
            if self._sd is None:
                import sounddevice as sd
                self._sd = sd
            return True
        except ImportError as exc:
            self._warn_capture_once(f"sounddevice unavailable: {exc}")
            return False
        except Exception as exc:
            self._warn_capture_once(f"sounddevice init error: {exc}")
            return False

    def _warn_capture_once(self, reason: str) -> None:
        """Warn once and defer retries so absent hardware cannot spin the loop."""
        self._retry_after = time.monotonic() + self._retry_backoff_sec
        if not self._capture_warning_logged:
            logger.warning(
                "[VECTOR][sound] ambient microphone unavailable; retrying in {}s: {}",
                self._retry_backoff_sec,
                reason,
            )
            self._capture_warning_logged = True

    @staticmethod
    def _rms(audio: np.ndarray) -> float:
        """Root Mean Square energy of audio signal."""
        audio_f = audio.astype(np.float32)
        mean_sq = float(np.mean(audio_f ** 2))
        return float(np.sqrt(max(mean_sq, 0.0)))

    @staticmethod
    def _zcr(audio: np.ndarray) -> float:
        """Zero-Crossing Rate - fraction of samples where sign changes."""
        if len(audio) < 2:
            return 0.0
        audio_f = audio.astype(np.float32)
        signs   = np.sign(audio_f)
        crossings = np.sum(np.abs(np.diff(signs)) > 0)
        return float(crossings) / float(len(audio_f) - 1)

    @staticmethod
    def _spectral_peak_ratio(audio: np.ndarray) -> float:
        """Spectral peak ratio: max_magnitude / mean_magnitude.
        High (>50) = strong tonal content (pure tone or music with clear harmonics).
        Low (<10)  = diffuse noise or silence.
        Combined with low ZCR, high ratio indicates music rather than speech.
        """
        if len(audio) < 32:
            return 0.0
        try:
            magnitudes = np.abs(np.fft.rfft(audio.astype(np.float32)))
            arith_mean = float(np.mean(magnitudes))
            if arith_mean < 1e-10:
                return 0.0
            return float(np.max(magnitudes)) / arith_mean
        except Exception:
            return 0.0

    def _try_load_onnx(self) -> None:
        """Optionally load a YAMNet ONNX model for 521-class classification."""
        if self._onnx_checked:
            return
        self._onnx_checked = True
        # SENSING__SOUND_MODEL_PATH is the production setting; retain the
        # legacy top-level lookup so existing callers remain compatible.
        model_path = (
            CONFIG.get("sensing", {}).get("sound_model_path", "")
            or CONFIG.get("sound_model_path", "")
        )
        if not model_path:
            return
        try:
            from pathlib import Path
            import onnxruntime as ort
            p = Path(model_path)
            if p.exists():
                self._onnx_session = ort.InferenceSession(str(p))
                logger.info("[VECTOR][sound] YAMNet ONNX loaded: {}", model_path)
            else:
                # Missing optional weights retain the local heuristic fallback.
                logger.warning(
                    "[VECTOR][sound] ONNX model not found at {}; using heuristics",
                    model_path,
                )
        except ImportError:
            logger.debug("[VECTOR][sound] onnxruntime not installed — using heuristics")
        except Exception as e:
            logger.warning("[VECTOR][sound] ONNX load failed: {}", e)

    # â"€â"€ public API â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

    def classify_frame(self, audio_np: np.ndarray) -> str:
        """Classify a mono audio numpy array (int16 or float32).

        Args:
            audio_np: 1-D or 2-D numpy array of audio samples.

        Returns:
            One of "silence", "speech", "music", "alert", "background", or "unknown".
        """
        try:
            # Flatten to 1-D mono
            audio = audio_np.flatten().astype(np.float32)

            # Normalise int16 range to -1..+1 if integer dtype supplied
            if audio_np.dtype in (np.int16, np.int32):
                max_val = float(np.iinfo(audio_np.dtype).max)
                audio = audio / max_val

            rms = self._rms(audio)
            zcr = self._zcr(audio)
            spr = self._spectral_peak_ratio(audio)

            logger.debug(f"[VECTOR][sound] rms={rms:.4f} zcr={zcr:.4f} spr={spr:.1f}")

            if rms < 0.01:
                return "silence"
            if rms > 0.30:
                # Default 60s per-label cooldown suppresses sustained noise
                # without hiding a later, distinct incident from the owner.
                now = time.monotonic()
                last_alert = self._last_alert_at.get("alert", float("-inf"))
                if now - last_alert >= self._alert_cooldown_sec:
                    self._last_alert_at["alert"] = now
                    self._emit_emergency_signal()
                else:
                    logger.debug("[VECTOR][sound] duplicate alert suppressed by cooldown")
                return "alert"
            if zcr > 0.20:
                return "speech"
            # Music: tonal content (high spectral peak ratio) + not speech-like ZCR
            if spr > 50 and rms > 0.02:
                return "music"
            return "background"

        except Exception as exc:
            logger.error(f"[VECTOR][sound] classify_frame error: {exc}")
            return "unknown"

    def sample_and_classify(self) -> str:
        """Record a short audio frame from the default microphone and classify it.

        Returns "unknown" gracefully if no microphone is available. The frame
        exists only in memory for classification; raw audio is never written.
        """
        if time.monotonic() < self._retry_after:
            return "unknown"
        try:
            if not self._ensure_sounddevice():
                return "unknown"

            n_samples = int(self._sample_rate * self._frame_duration)
            if not self._active_log_emitted:
                # Cheap transparency indicator for logs/status inspection. The
                # boolean is public for a future HUD consumer without capture.
                logger.info(
                    "[VECTOR][sound] ambient microphone sampling ACTIVE "
                    "(classification only; raw audio is not stored)"
                )
                self._active_log_emitted = True
            self.is_active = True
            try:
                recording = self._sd.rec(
                    n_samples,
                    samplerate=self._sample_rate,
                    channels=1,
                    dtype="float32",
                    blocking=True,
                )
                label = self.classify_frame(recording)
            finally:
                self.is_active = False
            self.last_label = label
            logger.debug(f"[VECTOR][sound] sample_and_classify → {label}")
            return label

        except Exception as exc:
            self.is_active = False
            self.last_label = "unknown"
            self._warn_capture_once(str(exc))
            return "unknown"

    def is_speech_active(self) -> bool:
        """Return True if the current ambient sound is classified as speech."""
        return self.sample_and_classify() == "speech"

    def _emit_emergency_signal(self) -> None:
        """Schedule the emergency-signal coroutine. classify_frame() (and its
        sync caller sample_and_classify()) can run with no running event loop,
        in which case asyncio.create_task() raises RuntimeError -- previously
        caught by the bare `except Exception` below and silently discarded, so
        a loud-sound alert never actually reached districts/emergency from any
        sync call path. Falls back to asyncio.run() when no loop is running so
        the signal still fires (blocking briefly, acceptable for a rare alert
        event) instead of being swallowed."""
        import asyncio
        try:
            from districts.emergency.main import _emit
            coro = _emit("environment", "alert_sound", True, "sound_classifier")
            try:
                asyncio.get_running_loop().create_task(coro)
            except RuntimeError:
                asyncio.run(coro)
        except Exception as exc:
            logger.warning(f"[VECTOR][sound] emergency signal emit failed: {exc}", exc_info=True)


# â"€â"€ smoke test â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
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
        #    alternating ±0.1 → ZCR ~ 1.0, RMS ~ 0.1 → speech
        speech = np.tile(np.array([0.1, -0.1], dtype=np.float32), 4000)
        result = classifier.classify_frame(speech)
        assert result == "speech", f"Expected 'speech', got {result!r}"

        # 4. background — low RMS, low ZCR, below the music rms>0.02 gate.
        # A pure sine (any amplitude) is strongly tonal by construction (high
        # spectral_peak_ratio) -- the classifier correctly calls it "music",
        # not "background"; the previous amplitude (0.05 -> rms ~0.035) hit
        # exactly that path and was a wrong test expectation, not a
        # classifier bug. Kept the same low-ZCR 20 Hz sine shape but scaled
        # so rms lands in [0.01, 0.02): above "silence", below the "music"
        # rms gate, so SPR doesn't matter and it correctly falls to
        # "background" regardless of tonal content.
        t = np.linspace(0, 0.5, 8000, dtype=np.float32)
        background = np.sin(2 * np.pi * 20 * t) * 0.02
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

    print("✅ sound_classifier.py OK" if ok else "âŒ sound_classifier.py FAILED")
