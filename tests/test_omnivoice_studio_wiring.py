"""
Closes the remaining test gaps from docs/repo_analysis/omnivoice.md's own
"Add tests" list (item 6) that don't require the real omnivoice package:
  - config defaults are safe
  - generate path is mockable without loading model
  - Voice Studio fallback works when OmniVoice raises
  - live conversation path does not use OmniVoice unless explicitly enabled

"adapter skips when disabled" was already covered before this pass
(tests/backend/test_repo_analysis_voice_sensing_gateway.py).

Also closes the "never wired anywhere" gap (confirmed via grep before this
pass — zero callers of OmniVoiceEngine outside test files): wires it into
districts/content/voice_generator.py as an optional, falls-back-to-Kokoro
content-generation path — the "Voice Studio" caller the doc's plan assumed
would exist.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_omnivoice_config_defaults_are_safe():
    from core.voice.engines.omnivoice_engine import OmniVoiceConfig

    config = OmniVoiceConfig()
    assert config.enabled is False
    assert config.live_allowed is False
    assert config.unload_after_seconds > 0


def test_omnivoice_generate_path_is_mockable_without_real_model(monkeypatch):
    """synthesize_to_file must be reachable via a mocked _load() — proves
    the adapter's control flow doesn't require the real omnivoice package
    to be tested."""
    from core.voice.engines.omnivoice_engine import OmniVoiceConfig, OmniVoiceEngine

    engine = OmniVoiceEngine(OmniVoiceConfig(enabled=True))

    class _FakeModel:
        def generate(self, **kwargs):
            # Real model writes the file as a side effect and returns nothing
            # meaningful — synthesize_to_file falls through to its own
            # `target` path in that case (`return str(result or target)`).
            return None

    monkeypatch.setattr(engine, "_load", lambda: _FakeModel())

    result = engine.synthesize_to_file("hello world", output_path="/tmp/test_omnivoice.wav")
    assert result == "/tmp/test_omnivoice.wav"


def test_live_conversation_tts_never_references_omnivoice():
    """Static invariant check: core/voice/tts.py (the always-on live
    conversation engine) must have zero references to omnivoice. This is
    the doc's "live conversation path does not use OmniVoice unless
    explicitly enabled" requirement — enforced by the live engine simply
    never importing it at all, the strongest form of that guarantee."""
    import core.voice.tts as tts_module
    src = Path(tts_module.__file__).read_text(encoding="utf-8")
    assert "omnivoice" not in src.lower()


def test_voice_studio_falls_back_to_kokoro_when_omnivoice_raises(monkeypatch):
    from districts.content.voice_generator import VoiceGenerator
    from core.voice.engines.omnivoice_engine import OmniVoiceConfig

    gen = VoiceGenerator()
    gen._omnivoice_config = OmniVoiceConfig(enabled=True)

    class _BrokenEngine:
        def synthesize_to_file(self, *a, **kw):
            raise RuntimeError("omnivoice package not installed")

    monkeypatch.setattr(gen, "_get_omnivoice_engine", lambda: _BrokenEngine())
    monkeypatch.setattr(gen, "generate_voice", lambda text, voice_name="af_heart", output_path=None: {
        "status": "success", "engine": "kokoro", "fallback_reason": None,
    })

    result = gen.generate_voice_studio("hello", language="en")
    assert result["status"] == "success"
    assert result["engine"] == "kokoro"
    assert "fallback" in result.get("fallback_reason", "") or result.get("fallback_used") is True


def test_voice_studio_uses_omnivoice_when_enabled_and_succeeds(monkeypatch):
    from districts.content.voice_generator import VoiceGenerator
    from core.voice.engines.omnivoice_engine import OmniVoiceConfig

    gen = VoiceGenerator()
    gen._omnivoice_config = OmniVoiceConfig(enabled=True)

    class _WorkingEngine:
        def synthesize_to_file(self, text, language="en", output_path=None, **kw):
            return output_path or "/tmp/out.wav"

    monkeypatch.setattr(gen, "_get_omnivoice_engine", lambda: _WorkingEngine())

    result = gen.generate_voice_studio("hello", language="hi", output_path="/tmp/out.wav")
    assert result["status"] == "success"
    assert result["engine"] == "omnivoice"


def test_voice_studio_uses_kokoro_directly_when_omnivoice_disabled(monkeypatch):
    from districts.content.voice_generator import VoiceGenerator
    from core.voice.engines.omnivoice_engine import OmniVoiceConfig

    gen = VoiceGenerator()
    gen._omnivoice_config = OmniVoiceConfig(enabled=False)

    called = {"omnivoice": False}
    monkeypatch.setattr(gen, "_get_omnivoice_engine", lambda: called.__setitem__("omnivoice", True))
    monkeypatch.setattr(gen, "generate_voice", lambda text, voice_name="af_heart", output_path=None: {
        "status": "success", "engine": "kokoro",
    })

    result = gen.generate_voice_studio("hello")
    assert result["engine"] == "kokoro"
    assert called["omnivoice"] is False


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
