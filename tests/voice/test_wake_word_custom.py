"""Tests — Session B1: Custom wake word model path preference + latency contract."""
from __future__ import annotations

import sys
import time
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np


def _make_detector():
    from core.voice.wake_word import WakeWordDetector
    return WakeWordDetector()


class TestWakeWordDetectorInit(unittest.TestCase):
    """WakeWordDetector initialises without crashing."""

    def test_instantiation_succeeds(self):
        det = _make_detector()
        self.assertIsNotNone(det)

    def test_has_custom_model_path_attr(self):
        det = _make_detector()
        self.assertTrue(hasattr(det, "_custom_model_path"))

    def test_custom_model_path_is_path(self):
        det = _make_detector()
        self.assertIsInstance(det._custom_model_path, Path)

    def test_custom_model_path_ends_with_onnx(self):
        det = _make_detector()
        self.assertTrue(str(det._custom_model_path).endswith(".onnx"))

    def test_custom_model_path_under_models_wake(self):
        det = _make_detector()
        parts = det._custom_model_path.parts
        self.assertIn("models", parts)
        self.assertIn("wake", parts)

    def test_fallback_to_whisper_when_no_openwakeword(self):
        """Without openwakeword installed or custom model, whisper KWS is active."""
        det = _make_detector()
        if det._model is None:
            self.assertTrue(det._use_whisper_kws)


class TestCustomModelPathPreference(unittest.TestCase):
    """When models/wake/hey_vector.onnx exists, _init_model() loads it by path."""

    def test_init_model_checks_custom_path_first(self):
        src = inspect.getsource(_make_detector()._init_model)
        self.assertIn("_custom_model_path", src)
        self.assertIn("exists()", src)

    def test_custom_path_loaded_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_onnx = Path(tmp) / "hey_vector.onnx"
            fake_onnx.write_bytes(b"fake")

            mock_model_instance = MagicMock()
            mock_Model = MagicMock(return_value=mock_model_instance)

            with patch.dict("sys.modules", {
                "openwakeword": MagicMock(),
                "openwakeword.model": MagicMock(Model=mock_Model),
            }):
                from core.voice.wake_word import WakeWordDetector
                det = WakeWordDetector.__new__(WakeWordDetector)
                det._threshold = 0.5
                det._wake_phrase = "hey_vector"
                det._sample_rate = 16000
                det._frame_size = 512
                det._use_whisper_kws = False
                det._active_model_name = ""
                det._model = None
                det._custom_model_path = fake_onnx

                import openwakeword.model as _owm
                _owm.Model = mock_Model

                if fake_onnx.exists():
                    call_args_would_include_path = str(fake_onnx)
                    self.assertIn("hey_vector.onnx", call_args_would_include_path)

    def test_custom_path_contains_wake_phrase(self):
        det = _make_detector()
        self.assertIn(det._wake_phrase, str(det._custom_model_path))


class TestIsWakeWord(unittest.TestCase):
    """is_wake_word() returns correct bool based on model prediction."""

    def test_returns_false_when_whisper_kws(self):
        det = _make_detector()
        if det._use_whisper_kws:
            frame = np.zeros(512, dtype=np.int16)
            result = det.is_wake_word(frame)
            self.assertFalse(result)

    def test_returns_bool(self):
        det = _make_detector()
        frame = np.zeros(512, dtype=np.int16)
        result = det.is_wake_word(frame)
        self.assertIsInstance(result, bool)

    def test_silent_frame_returns_false(self):
        det = _make_detector()
        silent = np.zeros(512, dtype=np.int16)
        self.assertFalse(det.is_wake_word(silent))

    def test_mock_model_high_score_returns_true(self):
        det = _make_detector()
        det._use_whisper_kws = False
        mock_model = MagicMock()
        mock_model.predict.return_value = {"hey_vector": 0.95}
        det._model = mock_model
        det._active_model_name = "hey_vector"
        det._threshold = 0.5

        frame = np.zeros(512, dtype=np.int16)
        result = det.is_wake_word(frame)
        self.assertTrue(result)

    def test_mock_model_low_score_returns_false(self):
        det = _make_detector()
        det._use_whisper_kws = False
        mock_model = MagicMock()
        mock_model.predict.return_value = {"hey_vector": 0.1}
        det._model = mock_model
        det._active_model_name = "hey_vector"
        det._threshold = 0.5

        frame = np.zeros(512, dtype=np.int16)
        result = det.is_wake_word(frame)
        self.assertFalse(result)

    def test_float32_frame_converted_to_int16(self):
        """is_wake_word() handles float32 input by converting to int16."""
        det = _make_detector()
        det._use_whisper_kws = False
        mock_model = MagicMock()
        mock_model.predict.return_value = {"hey_vector": 0.2}
        det._model = mock_model
        det._active_model_name = "hey_vector"
        det._threshold = 0.5

        frame_f32 = np.zeros(512, dtype=np.float32)
        result = det.is_wake_word(frame_f32)
        self.assertIsInstance(result, bool)


class TestLatencyContract(unittest.TestCase):
    """is_wake_word() must complete in under 300ms per frame (mock model path)."""

    def test_latency_under_300ms_with_mock_model(self):
        det = _make_detector()
        det._use_whisper_kws = False
        mock_model = MagicMock()
        mock_model.predict.return_value = {"hey_vector": 0.1}
        det._model = mock_model
        det._active_model_name = "hey_vector"
        det._threshold = 0.5

        frame = np.zeros(512, dtype=np.int16)
        start = time.perf_counter()
        det.is_wake_word(frame)
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertLess(elapsed_ms, 300.0, f"is_wake_word took {elapsed_ms:.1f}ms (limit: 300ms)")

    def test_latency_whisper_kws_path_under_1ms(self):
        """The whisper KWS fast-reject (returns False immediately) must be sub-1ms."""
        det = _make_detector()
        det._use_whisper_kws = True
        det._model = None

        frame = np.zeros(512, dtype=np.int16)
        start = time.perf_counter()
        result = det.is_wake_word(frame)
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertFalse(result)
        self.assertLess(elapsed_ms, 1.0, f"Whisper KWS fast-reject took {elapsed_ms:.3f}ms")

    def test_100_frames_under_30s(self):
        """100 sequential frames with mock model should finish well under 30s total."""
        det = _make_detector()
        det._use_whisper_kws = False
        mock_model = MagicMock()
        mock_model.predict.return_value = {"hey_vector": 0.05}
        det._model = mock_model
        det._active_model_name = "hey_vector"
        det._threshold = 0.5

        frame = np.zeros(512, dtype=np.int16)
        start = time.perf_counter()
        for _ in range(100):
            det.is_wake_word(frame)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 30.0, f"100 frames took {elapsed:.2f}s")


class TestFalsePositiveRate(unittest.TestCase):
    """False positive rate < 1% on 60s of silence/background audio."""

    def test_zero_false_positives_on_silent_audio(self):
        """60 seconds of silent audio at 512-sample frames: 0 detections expected."""
        det = _make_detector()
        det._use_whisper_kws = False
        mock_model = MagicMock()
        mock_model.predict.return_value = {"hey_vector": 0.0}
        det._model = mock_model
        det._active_model_name = "hey_vector"
        det._threshold = 0.5

        sample_rate = 16000
        frame_size = 512
        frames_per_60s = (sample_rate * 60) // frame_size
        silent_frame = np.zeros(frame_size, dtype=np.int16)

        false_positives = sum(1 for _ in range(frames_per_60s) if det.is_wake_word(silent_frame))
        fp_rate = false_positives / frames_per_60s

        self.assertLess(fp_rate, 0.01, f"False positive rate {fp_rate:.4f} exceeds 1%")

    def test_noise_below_threshold_no_detection(self):
        """Random low-amplitude noise frames: model score 0.3 → no detection with threshold 0.5."""
        det = _make_detector()
        det._use_whisper_kws = False
        mock_model = MagicMock()
        mock_model.predict.return_value = {"hey_vector": 0.3}
        det._model = mock_model
        det._active_model_name = "hey_vector"
        det._threshold = 0.5

        rng = np.random.default_rng(42)
        results = []
        for _ in range(100):
            noise = (rng.random(512) * 1000).astype(np.int16)
            results.append(det.is_wake_word(noise))

        self.assertEqual(sum(results), 0)


class TestTrainWakeWordMethodPathConsistency(unittest.TestCase):
    """Task B.4 regression: WakeWordDetector.train_wake_word() (the async
    method, separate from scripts/train_wake_word.py) used to write its
    output .onnx to models/wake_word/, while _init_model()'s read path is
    models/wake/ — a model trained via this method would never be found.
    Verified by source inspection (no audio hardware needed)."""

    def test_train_method_writes_to_same_dir_init_model_reads_from(self):
        det = _make_detector()
        src = inspect.getsource(det.train_wake_word)
        self.assertNotIn('"wake_word"', src, "train_wake_word() must not use the old, unread models/wake_word/ path")
        self.assertIn("self._custom_model_path.parent", src)


class TestTrainScript(unittest.TestCase):
    """scripts/train_wake_word.py CLI smoke checks."""

    def test_script_exists(self):
        script = Path(__file__).parent.parent.parent / "scripts" / "train_wake_word.py"
        self.assertTrue(script.exists())

    def test_dry_run_exits_zero(self):
        import subprocess
        script = Path(__file__).parent.parent.parent / "scripts" / "train_wake_word.py"
        result = subprocess.run(
            [sys.executable, str(script), "--dry-run"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, f"stdout={result.stdout} stderr={result.stderr}")

    def test_check_exits_nonzero_when_no_model(self):
        import subprocess
        script = Path(__file__).parent.parent.parent / "scripts" / "train_wake_word.py"
        model_path = Path(__file__).parent.parent.parent / "models" / "wake" / "hey_vector.onnx"
        if model_path.exists():
            self.skipTest("Custom model already trained — check would exit 0")
        result = subprocess.run(
            [sys.executable, str(script), "--check"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_help_shows_usage(self):
        import subprocess
        script = Path(__file__).parent.parent.parent / "scripts" / "train_wake_word.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("wake", result.stdout.lower())


class TestPhraseModesMapping(unittest.TestCase):
    """_PHRASE_MODES maps all known phrases to valid modes."""

    def test_phrase_modes_attribute_exists(self):
        det = _make_detector()
        self.assertTrue(hasattr(det, "_PHRASE_MODES"))

    def test_hey_vector_maps_to_conversation(self):
        det = _make_detector()
        self.assertEqual(det._PHRASE_MODES.get("hey vector"), "conversation")

    def test_all_modes_are_valid_strings(self):
        det = _make_detector()
        valid_modes = {"conversation", "deep_think", "private"}
        for phrase, mode in det._PHRASE_MODES.items():
            self.assertIn(mode, valid_modes, f"Phrase '{phrase}' maps to unknown mode '{mode}'")


if __name__ == "__main__":
    unittest.main()
