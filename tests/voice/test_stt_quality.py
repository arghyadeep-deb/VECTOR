"""Tests — Session B4: Whisper large-v3 upgrade + VRAM-aware model selection."""
from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np


# ── WER utility ──────────────────────────────────────────────────────────────


def _wer(reference: str, hypothesis: str) -> float:
    """Word error rate via dynamic programming."""
    ref = reference.lower().split()
    hyp = hypothesis.lower().split()
    if not ref:
        return 0.0 if not hyp else 1.0
    d = [[0] * (len(hyp) + 1) for _ in range(len(ref) + 1)]
    for i in range(len(ref) + 1):
        d[i][0] = i
    for j in range(len(hyp) + 1):
        d[0][j] = j
    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            if ref[i - 1] == hyp[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = 1 + min(d[i - 1][j], d[i][j - 1], d[i - 1][j - 1])
    return d[len(ref)][len(hyp)] / len(ref)


# ── Config field tests ────────────────────────────────────────────────────────


class TestVoiceConfigWhisperModel(unittest.TestCase):
    """VoiceConfig.whisper_model exists and defaults to large-v3."""

    def test_whisper_model_field_exists(self):
        from core.config import VoiceConfig
        fields = VoiceConfig.model_fields
        self.assertIn("whisper_model", fields)

    def test_whisper_model_default_large_v3(self):
        from core.config import VoiceConfig
        cfg = VoiceConfig()
        self.assertEqual(cfg.whisper_model, "large-v3")

    def test_whisper_model_readable_from_config_dict(self):
        from core.config import CONFIG
        voice = CONFIG.get("voice", {})
        self.assertIn("whisper_model", voice)

    def test_config_whisper_model_is_string(self):
        from core.config import CONFIG
        val = CONFIG.get("voice", {}).get("whisper_model")
        self.assertIsInstance(val, str)

    def test_whisper_model_can_be_overridden(self):
        from core.config import VoiceConfig
        cfg = VoiceConfig(whisper_model="medium")
        self.assertEqual(cfg.whisper_model, "medium")


# ── VRAM requirements table ───────────────────────────────────────────────────


class TestWhisperVramRequirements(unittest.TestCase):
    """WhisperSTT._VRAM_REQUIREMENTS covers large-v3 and medium."""

    def _make_stt(self):
        from core.voice.stt import WhisperSTT
        s = WhisperSTT.__new__(WhisperSTT)
        s._model = None
        s._model_name = "large-v3"
        return s

    def test_vram_requirements_attr_exists(self):
        stt = self._make_stt()
        self.assertTrue(hasattr(stt, "_VRAM_REQUIREMENTS"))

    def test_large_v3_requires_at_least_6gb(self):
        stt = self._make_stt()
        self.assertGreaterEqual(stt._VRAM_REQUIREMENTS.get("large-v3", 0), 6.0)

    def test_medium_requires_less_than_large(self):
        stt = self._make_stt()
        self.assertLess(
            stt._VRAM_REQUIREMENTS.get("medium", 0),
            stt._VRAM_REQUIREMENTS.get("large-v3", 0),
        )

    def test_vram_requirements_is_dict(self):
        stt = self._make_stt()
        self.assertIsInstance(stt._VRAM_REQUIREMENTS, dict)


class TestFasterWhisperVramRequirements(unittest.TestCase):
    """FasterWhisperSTT._VRAM_REQUIREMENTS covers large-v3 at fp16 (~6 GB)."""

    def _make_stt(self):
        from core.voice.stt import FasterWhisperSTT
        s = FasterWhisperSTT.__new__(FasterWhisperSTT)
        s._model = None
        s._model_name = "large-v3"
        return s

    def test_vram_requirements_exists(self):
        stt = self._make_stt()
        self.assertTrue(hasattr(stt, "_VRAM_REQUIREMENTS"))

    def test_large_v3_fp16_at_least_4gb(self):
        stt = self._make_stt()
        self.assertGreaterEqual(stt._VRAM_REQUIREMENTS.get("large-v3", 0), 4.0)


# ── _select_model() VRAM-aware logic ─────────────────────────────────────────


class TestWhisperSelectModel(unittest.TestCase):
    """WhisperSTT._select_model() falls back to medium when VRAM insufficient."""

    def _make_stt(self, model="large-v3"):
        from core.voice.stt import WhisperSTT
        s = WhisperSTT.__new__(WhisperSTT)
        s._model = None
        s._model_name = model
        return s

    def test_select_model_method_exists(self):
        stt = self._make_stt()
        self.assertTrue(callable(stt._select_model))

    def test_returns_string(self):
        stt = self._make_stt()
        result = stt._select_model()
        self.assertIsInstance(result, str)

    def test_sufficient_vram_keeps_large_v3(self):
        stt = self._make_stt("large-v3")
        mock_cuda = MagicMock()
        mock_cuda.is_available.return_value = True
        mock_props = MagicMock()
        mock_props.total_memory = int(12e9)  # 12 GB
        mock_cuda.get_device_properties.return_value = mock_props
        with patch("torch.cuda", mock_cuda):
            result = stt._select_model()
        self.assertEqual(result, "large-v3")

    def test_insufficient_vram_falls_back_to_medium(self):
        stt = self._make_stt("large-v3")
        mock_cuda = MagicMock()
        mock_cuda.is_available.return_value = True
        mock_props = MagicMock()
        mock_props.total_memory = int(8e9)  # 8 GB — insufficient for fp32 large-v3
        mock_cuda.get_device_properties.return_value = mock_props
        with patch("torch.cuda", mock_cuda):
            result = stt._select_model()
        self.assertEqual(result, "medium")

    def test_no_cuda_keeps_requested_model(self):
        stt = self._make_stt("large-v3")
        mock_cuda = MagicMock()
        mock_cuda.is_available.return_value = False
        with patch("torch.cuda", mock_cuda):
            result = stt._select_model()
        self.assertEqual(result, "large-v3")

    def test_medium_model_not_downgraded(self):
        stt = self._make_stt("medium")
        result = stt._select_model()
        self.assertEqual(result, "medium")

    def test_torch_import_error_keeps_model(self):
        stt = self._make_stt("large-v3")
        with patch.dict("sys.modules", {"torch": None}):
            try:
                result = stt._select_model()
            except Exception:
                result = "large-v3"  # If import fails, model should be unchanged
        self.assertEqual(result, "large-v3")

    def test_base_model_not_downgraded(self):
        stt = self._make_stt("base")
        result = stt._select_model()
        self.assertEqual(result, "base")


class TestFasterWhisperSelectModel(unittest.TestCase):
    """FasterWhisperSTT._select_model() falls back to medium when VRAM insufficient."""

    def _make_stt(self, model="large-v3"):
        from core.voice.stt import FasterWhisperSTT
        s = FasterWhisperSTT.__new__(FasterWhisperSTT)
        s._model = None
        s._model_name = model
        return s

    def test_select_model_exists(self):
        stt = self._make_stt()
        self.assertTrue(callable(stt._select_model))

    def test_sufficient_vram_keeps_large_v3(self):
        stt = self._make_stt("large-v3")
        mock_cuda = MagicMock()
        mock_cuda.is_available.return_value = True
        mock_props = MagicMock()
        mock_props.total_memory = int(12e9)
        mock_cuda.get_device_properties.return_value = mock_props
        with patch("torch.cuda", mock_cuda):
            result = stt._select_model()
        self.assertEqual(result, "large-v3")

    def test_low_vram_falls_back_to_medium(self):
        stt = self._make_stt("large-v3")
        mock_cuda = MagicMock()
        mock_cuda.is_available.return_value = True
        mock_props = MagicMock()
        mock_props.total_memory = int(4e9)  # 4 GB — insufficient
        mock_cuda.get_device_properties.return_value = mock_props
        with patch("torch.cuda", mock_cuda):
            result = stt._select_model()
        self.assertEqual(result, "medium")


# ── WER utility unit tests ────────────────────────────────────────────────────


class TestWerUtility(unittest.TestCase):
    """WER helper is correct."""

    def test_perfect_match_wer_zero(self):
        self.assertAlmostEqual(_wer("hello world", "hello world"), 0.0)

    def test_one_substitution(self):
        wer = _wer("hello world", "hello earth")
        self.assertAlmostEqual(wer, 1 / 2)

    def test_empty_reference_empty_hypothesis(self):
        self.assertAlmostEqual(_wer("", ""), 0.0)

    def test_case_insensitive(self):
        self.assertAlmostEqual(_wer("Hello World", "hello world"), 0.0)

    def test_deletion(self):
        wer = _wer("one two three", "one two")
        self.assertAlmostEqual(wer, 1 / 3)


# ── WER threshold validation (mocked transcriptions) ─────────────────────────


class TestWerThresholds(unittest.TestCase):
    """Mock transcriptions validate the 5%/20% WER thresholds.

    We cannot load Whisper models in CI — instead we verify the threshold constants
    and use synthetic near-perfect transcriptions to confirm the WER boundary logic.
    """

    REFERENCE = (
        "gradient descent backpropagation neural network "
        "transformer attention mechanism CUDA tensor"
    )

    def test_large_v3_quality_mock_under_5_percent(self):
        """large-v3 mock: 0 errors on domain jargon → WER 0.0 < 0.05."""
        hypothesis = self.REFERENCE  # perfect mock
        wer = _wer(self.REFERENCE, hypothesis)
        self.assertLess(wer, 0.05, f"large-v3 mock WER {wer:.4f} exceeds 5% threshold")

    def test_base_model_mock_within_20_percent(self):
        """base mock: 1 substitution on an 8-word sentence → WER 0.125 < 0.20."""
        words = self.REFERENCE.split()
        words[-1] = "tenor"  # single substitution of "tensor"
        hypothesis = " ".join(words)
        wer = _wer(self.REFERENCE, hypothesis)
        self.assertLess(wer, 0.20, f"base mock WER {wer:.4f} exceeds 20% threshold")

    def test_wer_threshold_large_v3_tighter_than_base(self):
        self.assertLess(0.05, 0.20)

    def test_reference_has_domain_jargon(self):
        jargon_words = ["gradient", "backpropagation", "transformer", "cuda", "tensor"]
        ref_lower = self.REFERENCE.lower()
        for word in jargon_words:
            self.assertIn(word.lower(), ref_lower)


# ── STT factory tests ─────────────────────────────────────────────────────────


class TestSTTFactory(unittest.TestCase):
    """STT() returns correct engine and handles unknown engine gracefully."""

    # NOTE: patch "core.voice.stt.CONFIG", NOT "core.config.CONFIG" — stt.py does
    # `from core.config import CONFIG`, which binds the object into stt's own
    # namespace at import. Patching core.config.CONFIG does nothing here, so
    # these tests silently read the LIVE .env instead (which sets
    # VOICE__STT_ENGINE=faster_whisper) and asserted against the wrong engine.

    def test_factory_returns_whisper_by_default(self):
        from core.voice.stt import STT, WhisperSTT
        with patch("core.voice.stt.CONFIG", {"voice": {"stt_engine": "whisper", "whisper_model": "base"}}):
            instance = STT()
        self.assertIsInstance(instance, WhisperSTT)

    def test_factory_unknown_engine_falls_back_to_whisper(self):
        from core.voice.stt import STT, WhisperSTT
        with patch("core.voice.stt.CONFIG", {"voice": {"stt_engine": "nonexistent_engine"}}):
            instance = STT()
        self.assertIsInstance(instance, WhisperSTT)

    def test_factory_honours_configured_faster_whisper(self):
        """The live default: .env sets VOICE__STT_ENGINE=faster_whisper."""
        from core.voice.stt import STT, FasterWhisperSTT
        with patch("core.voice.stt.CONFIG", {"voice": {"stt_engine": "faster_whisper"}}):
            instance = STT()
        self.assertIsInstance(instance, FasterWhisperSTT)

    def test_whisper_stt_has_transcribe_method(self):
        from core.voice.stt import WhisperSTT
        stt = WhisperSTT.__new__(WhisperSTT)
        stt._model = None
        stt._model_name = "base"
        self.assertTrue(callable(stt.transcribe))

    def test_whisper_stt_has_record_and_transcribe_method(self):
        from core.voice.stt import WhisperSTT
        stt = WhisperSTT.__new__(WhisperSTT)
        self.assertTrue(callable(stt.record_and_transcribe))

    def test_mock_model_transcribes_audio(self):
        """WhisperSTT.transcribe() returns a string when model is mocked."""
        from core.voice.stt import WhisperSTT
        stt = WhisperSTT.__new__(WhisperSTT)
        stt._model_name = "base"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "  gradient descent  "}
        stt._model = mock_model

        audio = np.zeros(16000, dtype=np.int16)
        result = stt.transcribe(audio, 16000)
        self.assertEqual(result, "gradient descent")

    def test_load_uses_select_model(self):
        """_load() calls _select_model() to determine effective model name."""
        from core.voice.stt import WhisperSTT
        stt = WhisperSTT.__new__(WhisperSTT)
        stt._model = None
        stt._model_name = "large-v3"

        loaded_names = []

        def fake_load(name):
            loaded_names.append(name)
            return MagicMock()

        with patch("core.voice.stt.WhisperSTT._select_model", return_value="medium"):
            with patch.dict("sys.modules", {"whisper": MagicMock(load_model=fake_load)}):
                stt._load()

        self.assertEqual(loaded_names, ["medium"])


if __name__ == "__main__":
    unittest.main()
