"""
docs/repo_analysis/supertonic.md's own integration plan (lines 34-41):
create core/voice/supertonic_tts.py (SupertonicTTS wrapper, lazy singleton,
guarded import), a live_engine config seam mirroring get_cloner(), and
these specific tests: available()=False graceful path, engine-factory
dispatch, lang-code mapping, bn/as still routed to gTTS, config validation.

core/voice/engines/supertonic_engine.py (pre-existing, used by the voice
benchmark harness) is a DIFFERENT, thinner seam — this file is the doc's
actual "live-conversation TTS engine" plan, not a benchmark probe.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_supertonic_tts_available_false_without_package():
    from core.voice.supertonic_tts import SupertonicTTS

    tts = SupertonicTTS(enabled=True)
    assert tts.available() is False


def test_supertonic_tts_available_false_when_disabled():
    from core.voice.supertonic_tts import SupertonicTTS

    tts = SupertonicTTS(enabled=False)
    assert tts.available() is False


def test_supertonic_tts_create_raises_clean_error_when_unavailable():
    from core.voice.supertonic_tts import SupertonicTTS

    tts = SupertonicTTS(enabled=True)
    try:
        tts.create("hello", lang="en")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "supertonic" in str(exc).lower()


def test_lang_code_maps_en_hi_ja_directly():
    from core.voice.supertonic_tts import map_lang_code

    assert map_lang_code("en") == "en"
    assert map_lang_code("hi") == "hi"
    assert map_lang_code("ja") == "ja"


def test_lang_code_bn_as_not_supported_by_supertonic():
    from core.voice.supertonic_tts import map_lang_code, SUPERTONIC_UNSUPPORTED_LANGS

    assert "bn" in SUPERTONIC_UNSUPPORTED_LANGS
    assert "as" in SUPERTONIC_UNSUPPORTED_LANGS
    assert map_lang_code("bn") is None
    assert map_lang_code("as") is None


def test_get_live_tts_factory_defaults_to_kokoro_marker():
    from core.voice.supertonic_tts import get_live_tts

    engine_name, engine = get_live_tts(live_engine="kokoro")
    assert engine_name == "kokoro"
    assert engine is None  # Kokoro stays the existing tts.py code path, no wrapper object


def test_get_live_tts_factory_dispatches_to_supertonic():
    from core.voice.supertonic_tts import get_live_tts, SupertonicTTS

    engine_name, engine = get_live_tts(live_engine="supertonic")
    assert engine_name == "supertonic"
    assert isinstance(engine, SupertonicTTS)


def test_config_defaults_are_safe():
    from core.config import CONFIG

    voice_cfg = CONFIG.get("voice", {}) or {}
    assert voice_cfg.get("live_engine", "kokoro") == "kokoro"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
