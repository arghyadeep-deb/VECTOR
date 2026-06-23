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


def test_supertonic_tts_available_false_when_disabled():
    from core.voice.supertonic_tts import SupertonicTTS

    tts = SupertonicTTS(enabled=False)
    assert tts.available() is False


def test_supertonic_tts_available_true_when_enabled_and_package_installed():
    """supertonic was installed this pass (docs/repo_analysis/OWNER_ACTIONS_NEEDED.md
    item resolved) -- available() must reflect that honestly rather than
    assume the package is absent."""
    from core.voice.supertonic_tts import SupertonicTTS

    tts = SupertonicTTS(enabled=True)
    assert tts.available() is True


def test_supertonic_tts_create_raises_clean_error_when_disabled():
    from core.voice.supertonic_tts import SupertonicTTS

    tts = SupertonicTTS(enabled=False)
    try:
        tts.create("hello", lang="en")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "supertonic" in str(exc).lower()


def test_supertonic_tts_load_constructs_real_tts_class_with_auto_download_off(monkeypatch):
    """Root-caused real bug: _load() called a nonexistent
    supertonic.load_model() -- confirmed via the actual installed package's
    public API (supertonic.TTS, not a module-level load_model function).
    Fixed to construct the real class. Mocked rather than instantiated for
    real -- a real TTS() with no local weights triggers an actual ~260MB
    HuggingFace download, a separate explicit owner action, not something
    a test should trigger."""
    from core.voice.supertonic_tts import SupertonicTTS
    import supertonic

    captured = {}

    class _FakeTTS:
        def __init__(self, model_dir=None, auto_download=True):
            captured["model_dir"] = model_dir
            captured["auto_download"] = auto_download

    monkeypatch.setattr(supertonic, "TTS", _FakeTTS)

    tts = SupertonicTTS(enabled=True)
    engine = tts._load()
    assert isinstance(engine, _FakeTTS)
    assert captured["auto_download"] is False


def test_supertonic_tts_load_raises_clean_error_when_weights_missing(monkeypatch):
    """auto_download=False (the default) must fail fast with a clear,
    actionable error when weights aren't available locally -- mocked so
    this doesn't depend on the real environment's cache state (weights
    were downloaded for real during this session's verification)."""
    from core.voice.supertonic_tts import SupertonicTTS
    import supertonic

    def _raise_missing(*a, **kw):
        raise FileNotFoundError("model weights not cached locally")

    monkeypatch.setattr(supertonic, "TTS", _raise_missing)

    tts = SupertonicTTS(enabled=True)
    try:
        tts._load()
        assert False, "expected RuntimeError (no local weights, auto_download=False)"
    except RuntimeError as exc:
        assert "auto_download" in str(exc) or "OWNER_ACTIONS_NEEDED" in str(exc)


def test_supertonic_tts_create_returns_samples_and_sample_rate(monkeypatch):
    """create() must obtain a real Style object via get_voice_style()
    before calling synthesize() -- synthesize() requires a Style instance,
    not a bare string/None, which the original code passed."""
    from core.voice.supertonic_tts import SupertonicTTS
    import numpy as np

    tts = SupertonicTTS(enabled=True)

    class _FakeStyle:
        pass

    class _FakeEngine:
        def get_voice_style(self, name):
            # Real bug found 2026-06-24 (live verification after weights
            # downloaded): "default" is not a real preset -- the real
            # package raises FileNotFoundError, listing M1-M5/F1-F5 as the
            # only valid names. Assert the fix uses a real one.
            assert name in {"M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5"}, name
            return _FakeStyle()

        def synthesize(self, text, voice_style, total_steps=8, speed=1.0, lang=None, **kw):
            assert isinstance(voice_style, _FakeStyle)
            return (np.zeros(100), 24000)

    monkeypatch.setattr(tts, "_load", lambda: _FakeEngine())
    samples, sr = tts.create("hello", lang="en")
    assert sr == 24000
    assert len(samples) == 100


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


def test_get_live_tts_factory_defaults_auto_download_off():
    """~260MB model weights are a separate, explicit owner action --
    the factory must never default to auto-downloading them."""
    from core.voice.supertonic_tts import get_live_tts

    _, engine = get_live_tts(live_engine="supertonic")
    assert engine.auto_download is False


def test_config_defaults_are_safe():
    from core.config import CONFIG

    voice_cfg = CONFIG.get("voice", {}) or {}
    assert voice_cfg.get("live_engine", "kokoro") == "kokoro"


def test_speak_supertonic_returns_false_when_default_kokoro_engine():
    """speak()'s new Supertonic branch must be a true no-op when
    live_engine is the default "kokoro" — never touches the package."""
    from core.voice.tts import VoiceTTS

    tts = VoiceTTS.__new__(VoiceTTS)
    tts._speed = 1.0
    assert tts._speak_supertonic("hello", "en") is False


def test_speak_supertonic_falls_through_when_enabled_but_package_missing(monkeypatch):
    """Mocked explicitly so this doesn't depend on the real environment's
    package/weight state -- supertonic is genuinely installed with weights
    downloaded as of this session, so without mocking this would attempt
    real synthesis + audio playback, not test the "missing" fallback path
    this test is named for."""
    import core.config as config_module
    import core.voice.supertonic_tts as st_module
    from core.voice.tts import VoiceTTS

    class _UnavailableEngine:
        def available(self):
            return False

    monkeypatch.setitem(config_module.CONFIG["voice"], "live_engine", "supertonic")
    monkeypatch.setattr(st_module, "get_live_tts", lambda *a, **kw: ("supertonic", _UnavailableEngine()))
    tts = VoiceTTS.__new__(VoiceTTS)
    tts._speed = 1.0
    assert tts._speak_supertonic("hello", "en") is False


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
