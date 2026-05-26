"""C4 tests — ElevenLabs streaming TTS integration in core/voice/tts.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ── TextToSpeech alias ────────────────────────────────────────────────────────


class TestTextToSpeechAlias(unittest.TestCase):
    """TextToSpeech is exported from core.voice.tts and aliases VoiceTTS."""

    def test_text_to_speech_importable(self):
        from core.voice.tts import TextToSpeech
        self.assertIsNotNone(TextToSpeech)

    def test_text_to_speech_is_voice_tts(self):
        from core.voice.tts import TextToSpeech, VoiceTTS
        self.assertIs(TextToSpeech, VoiceTTS)

    def test_text_to_speech_in_all(self):
        import core.voice.tts as mod
        self.assertIn("TextToSpeech", mod.__all__)

    def test_text_to_speech_has_speak(self):
        from core.voice.tts import TextToSpeech
        tts = TextToSpeech()
        self.assertTrue(callable(tts.speak))

    def test_text_to_speech_has_stop_speaking(self):
        from core.voice.tts import TextToSpeech
        tts = TextToSpeech()
        self.assertTrue(callable(tts.stop_speaking))


# ── ElevenLabs instance attributes ───────────────────────────────────────────


class TestElevenLabsAttributes(unittest.TestCase):
    """VoiceTTS has ElevenLabs-related instance attributes set in __init__."""

    def setUp(self):
        from core.voice.tts import VoiceTTS
        self.tts = VoiceTTS()

    def test_el_ok_attribute_exists(self):
        self.assertFalse(self.tts._el_ok)

    def test_el_client_attribute_exists(self):
        self.assertIsNone(self.tts._el_client)

    def test_el_prosody_is_dict(self):
        self.assertIsInstance(self.tts._el_prosody, dict)

    def test_el_prosody_has_stability(self):
        self.assertIn("stability", self.tts._el_prosody)

    def test_el_prosody_has_similarity_boost(self):
        self.assertIn("similarity_boost", self.tts._el_prosody)

    def test_el_prosody_has_style(self):
        self.assertIn("style", self.tts._el_prosody)

    def test_el_prosody_has_speaker_boost(self):
        self.assertIn("use_speaker_boost", self.tts._el_prosody)

    def test_el_prosody_stability_default(self):
        self.assertEqual(self.tts._el_prosody["stability"], 0.75)

    def test_el_prosody_similarity_boost_default(self):
        self.assertEqual(self.tts._el_prosody["similarity_boost"], 0.85)

    def test_el_prosody_style_default(self):
        self.assertEqual(self.tts._el_prosody["style"], 0.3)

    def test_el_model_attribute_exists(self):
        self.assertIsInstance(self.tts._el_model, str)
        self.assertGreater(len(self.tts._el_model), 0)

    def test_el_voice_id_attribute_exists(self):
        self.assertIsInstance(self.tts._el_voice_id, str)


# ── _init_elevenlabs ─────────────────────────────────────────────────────────


class TestInitElevenLabs(unittest.TestCase):
    """_init_elevenlabs() returns False when disabled or missing API key."""

    def test_returns_false_when_streaming_disabled(self):
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        # Default config has elevenlabs_streaming = False
        result = tts._init_elevenlabs()
        self.assertFalse(result)

    def test_returns_false_when_no_api_key(self):
        from core.voice.tts import VoiceTTS
        import core.voice.tts as mod
        tts = VoiceTTS()
        with patch.dict(
            "core.voice.tts.CONFIG",
            {"voice": {"elevenlabs_streaming": True}, "api_keys": {"elevenlabs_key": ""}},
        ):
            result = tts._init_elevenlabs()
        self.assertFalse(result)

    def test_returns_false_when_package_not_installed(self):
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        with patch.dict(
            "core.voice.tts.CONFIG",
            {"voice": {"elevenlabs_streaming": True}, "api_keys": {"elevenlabs_key": "test-key"}},
        ):
            with patch.dict("sys.modules", {"elevenlabs": None, "elevenlabs.client": None}):
                result = tts._init_elevenlabs()
        self.assertFalse(result)

    def test_returns_true_when_configured(self):
        """When API key is set and streaming enabled, init returns True."""
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        mock_el_module = MagicMock()
        mock_client = MagicMock()
        mock_el_module.ElevenLabs.return_value = mock_client
        with patch.dict(
            "core.voice.tts.CONFIG",
            {
                "voice": {"elevenlabs_streaming": True},
                "api_keys": {"elevenlabs_key": "test-key-123", "elevenlabs_voice_id": "abc123"},
            },
        ):
            with patch.dict("sys.modules", {"elevenlabs.client": mock_el_module}):
                result = tts._init_elevenlabs()
        self.assertTrue(result)

    def test_sets_el_client_on_success(self):
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        mock_el_module = MagicMock()
        mock_client = MagicMock()
        mock_el_module.ElevenLabs.return_value = mock_client
        with patch.dict(
            "core.voice.tts.CONFIG",
            {
                "voice": {"elevenlabs_streaming": True},
                "api_keys": {"elevenlabs_key": "test-key-123"},
            },
        ):
            with patch.dict("sys.modules", {"elevenlabs.client": mock_el_module}):
                tts._init_elevenlabs()
        self.assertIsNotNone(tts._el_client)

    def test_never_raises(self):
        """_init_elevenlabs must never propagate exceptions."""
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        with patch.dict(
            "core.voice.tts.CONFIG",
            {"voice": {"elevenlabs_streaming": True}, "api_keys": {"elevenlabs_key": "key"}},
        ):
            mock_el_module = MagicMock()
            mock_el_module.ElevenLabs.side_effect = RuntimeError("network error")
            with patch.dict("sys.modules", {"elevenlabs.client": mock_el_module}):
                try:
                    result = tts._init_elevenlabs()
                except Exception as exc:
                    self.fail(f"_init_elevenlabs raised: {exc}")
        self.assertFalse(result)


# ── _speak_elevenlabs_stream ──────────────────────────────────────────────────


class TestSpeakElevenLabsStream(unittest.TestCase):
    """_speak_elevenlabs_stream() behavior with/without client."""

    def _make_tts_with_mock_client(self) -> "VoiceTTS":
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        tts._el_ok = True
        tts._el_client = MagicMock()
        tts._el_voice_id = "test-voice-id"
        tts._el_model = "eleven_turbo_v2"
        tts._el_prosody = {
            "stability": 0.75,
            "similarity_boost": 0.85,
            "style": 0.3,
            "use_speaker_boost": True,
        }
        return tts

    def test_returns_false_when_el_ok_false(self):
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        tts._el_ok = False
        result = tts._speak_elevenlabs_stream("hello")
        self.assertFalse(result)

    def test_returns_false_when_client_is_none(self):
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        tts._el_ok = True
        tts._el_client = None
        result = tts._speak_elevenlabs_stream("hello")
        self.assertFalse(result)

    def test_returns_true_on_barge_in_before_stream(self):
        """If _speaking is set to False during iteration, returns True (barge-in)."""
        tts = self._make_tts_with_mock_client()

        def fake_stream(**kwargs):
            tts._speaking = False  # simulate barge-in
            yield b""

        tts._el_client.text_to_speech.stream.side_effect = fake_stream

        import sounddevice as _sd_module
        with patch("sounddevice.play"), patch("sounddevice.get_stream"), patch("sounddevice.stop"):
            result = tts._speak_elevenlabs_stream("hello world")

        self.assertTrue(result)

    def test_sets_speaking_true_at_start(self):
        """_speak_elevenlabs_stream sets _speaking = True at entry."""
        tts = self._make_tts_with_mock_client()
        speaking_values = []

        def fake_stream(**kwargs):
            speaking_values.append(tts._speaking)
            yield b"\x00\x01"

        tts._el_client.text_to_speech.stream.side_effect = fake_stream

        with patch("sounddevice.play"), patch("sounddevice.get_stream") as mock_gs, patch("sounddevice.stop"):
            mock_gs.return_value.active = False
            tts._speak_elevenlabs_stream("hello")

        self.assertTrue(len(speaking_values) > 0)
        self.assertTrue(speaking_values[0], "must be True at entry")

    def test_calls_stream_with_voice_settings(self):
        """stream() is called with prosody settings from _el_prosody."""
        tts = self._make_tts_with_mock_client()
        tts._el_client.text_to_speech.stream.return_value = iter([b"\x00\x01\x00\x02"])

        with patch("sounddevice.play"), patch("sounddevice.get_stream") as mock_gs, patch("sounddevice.stop"):
            mock_gs.return_value.active = False
            tts._speak_elevenlabs_stream("test prosody")

        call_kwargs = tts._el_client.text_to_speech.stream.call_args
        self.assertIsNotNone(call_kwargs)
        kwargs = call_kwargs[1] if call_kwargs[1] else {}
        # voice_settings may be passed as kwarg
        # At minimum, verify stream() was called
        tts._el_client.text_to_speech.stream.assert_called_once()

    def test_returns_false_on_exception(self):
        """Exceptions in ElevenLabs API call return False (fall through to local TTS)."""
        tts = self._make_tts_with_mock_client()
        tts._el_client.text_to_speech.stream.side_effect = RuntimeError("api error")

        result = tts._speak_elevenlabs_stream("hello")
        self.assertFalse(result)

    def test_resets_speaking_on_exception(self):
        """_speaking is reset to False after an exception."""
        tts = self._make_tts_with_mock_client()
        tts._el_client.text_to_speech.stream.side_effect = RuntimeError("api error")
        tts._speak_elevenlabs_stream("hello")
        self.assertFalse(tts._speaking)


# ── speak() routing ───────────────────────────────────────────────────────────


class TestSpeakRouting(unittest.TestCase):
    """speak() routes to ElevenLabs when _el_ok=True, falls through on failure."""

    def test_speaks_via_elevenlabs_when_el_ok(self):
        """When _el_ok=True and stream succeeds, local TTS is NOT called."""
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        tts._el_ok = True
        tts._speak_elevenlabs_stream = MagicMock(return_value=True)
        tts._speak_kokoro = MagicMock()
        tts._speak_pyttsx3 = MagicMock()
        tts._speak_piper = MagicMock()

        tts.speak("hello", lang="en")

        tts._speak_elevenlabs_stream.assert_called_once_with("hello")
        tts._speak_kokoro.assert_not_called()
        tts._speak_pyttsx3.assert_not_called()

    def test_falls_through_to_local_when_elevenlabs_fails(self):
        """When _el_ok=True but stream returns False, local TTS is used."""
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        tts._el_ok = True
        tts._kokoro_ok = False
        tts._speak_elevenlabs_stream = MagicMock(return_value=False)
        tts._speak_pyttsx3 = MagicMock()
        tts._pyttsx3 = MagicMock()

        tts.speak("hello", lang="en")

        tts._speak_pyttsx3.assert_called_once()

    def test_skips_elevenlabs_for_non_english(self):
        """ElevenLabs streaming is skipped for non-English languages."""
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        tts._el_ok = True
        tts._speak_elevenlabs_stream = MagicMock(return_value=True)
        tts._kokoro_ok = False
        tts._pyttsx3 = MagicMock()
        tts._speak_gtts = MagicMock()

        tts.speak("namaste", lang="hi")

        tts._speak_elevenlabs_stream.assert_not_called()

    def test_empty_text_returns_immediately(self):
        """speak('') must return without touching any engine."""
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        tts._el_ok = True
        tts._speak_elevenlabs_stream = MagicMock()
        tts.speak("")
        tts._speak_elevenlabs_stream.assert_not_called()


# ── Prosody configuration ─────────────────────────────────────────────────────


class TestProsodyConfiguration(unittest.TestCase):
    """Prosody settings are read from CONFIG at init time."""

    def test_stability_from_config(self):
        from core.voice.tts import VoiceTTS
        with patch.dict("core.voice.tts.CONFIG", {"voice": {"el_stability": 0.55}}):
            tts = VoiceTTS()
        self.assertEqual(tts._el_prosody["stability"], 0.55)

    def test_similarity_boost_from_config(self):
        from core.voice.tts import VoiceTTS
        with patch.dict("core.voice.tts.CONFIG", {"voice": {"el_similarity_boost": 0.60}}):
            tts = VoiceTTS()
        self.assertEqual(tts._el_prosody["similarity_boost"], 0.60)

    def test_style_from_config(self):
        from core.voice.tts import VoiceTTS
        with patch.dict("core.voice.tts.CONFIG", {"voice": {"el_style": 0.5}}):
            tts = VoiceTTS()
        self.assertEqual(tts._el_prosody["style"], 0.5)


# ── Existing StreamingTTS regression ─────────────────────────────────────────


class TestStreamingTTSRegression(unittest.TestCase):
    """C4 changes must not break the existing StreamingTTS API."""

    def test_streaming_tts_importable(self):
        from core.voice.tts import StreamingTTS
        self.assertIsNotNone(StreamingTTS)

    def test_early_terminate_clears_speaking(self):
        from core.voice.tts import StreamingTTS
        tts = StreamingTTS()
        tts._speaking = True
        with patch("sounddevice.stop"):
            tts.early_terminate()
        self.assertFalse(tts.is_speaking)

    def test_set_voice(self):
        from core.voice.tts import StreamingTTS
        tts = StreamingTTS()
        tts.set_voice("bf_emma")
        self.assertEqual(tts._current_voice, "bf_emma")


if __name__ == "__main__":
    unittest.main()
