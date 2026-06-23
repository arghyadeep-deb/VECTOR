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


def test_load_calls_from_pretrained_without_device_or_dtype_kwargs(monkeypatch):
    """Real bug found 2026-06-24 (model weights downloaded for real this
    session, live verification run): _load() called
    OmniVoice.from_pretrained(model, device=..., dtype=...), but the real
    HF from_pretrained() forwards unrecognized kwargs straight to
    OmniVoice.__init__(), which doesn't accept either -- confirmed live:
    TypeError: OmniVoice.__init__() got an unexpected keyword argument
    'device'. The real, working pattern (also confirmed live) is to call
    from_pretrained() with no device/dtype kwargs, then call
    model.to(device=..., dtype=...) afterward."""
    from core.voice.engines.omnivoice_engine import OmniVoiceConfig, OmniVoiceEngine
    import core.voice.engines.omnivoice_engine as ov_module

    captured = {}

    class _FakeModel:
        def to(self, device=None, dtype=None):
            captured["to_device"] = device
            captured["to_dtype"] = dtype
            return self

    class _FakeOmniVoice:
        @staticmethod
        def from_pretrained(model_name, *args, **kwargs):
            captured["from_pretrained_kwargs"] = kwargs
            return _FakeModel()

    monkeypatch.setattr(ov_module, "OmniVoice", _FakeOmniVoice, raising=False)
    monkeypatch.setitem(
        __import__("sys").modules, "omnivoice",
        type("M", (), {"OmniVoice": _FakeOmniVoice})(),
    )

    config = OmniVoiceConfig(enabled=True, device="cpu", dtype="float32")
    engine = OmniVoiceEngine(config)
    engine._load()

    assert captured["from_pretrained_kwargs"] == {}, (
        "from_pretrained() must not receive device/dtype kwargs -- "
        f"got {captured['from_pretrained_kwargs']}"
    )
    assert captured["to_device"] == "cpu"
    assert str(captured["to_dtype"]).endswith("float32")


def test_omnivoice_generate_path_is_mockable_without_real_model(monkeypatch, tmp_path):
    """synthesize_to_file must be reachable via a mocked _load() — proves
    the adapter's control flow doesn't require the real omnivoice package
    to be tested.

    Root-caused real bug (omnivoice installed this pass, API verified
    directly): generate() doesn't accept profile/num_step/output_path
    kwargs (none exist on the real method) and returns list[numpy.ndarray]
    -- it never writes a file itself. Fixed synthesize_to_file() to call
    only real parameters and save the result via soundfile using the
    model's own model.sampling_rate attribute (the package's own docstring
    documents this exact pattern)."""
    import numpy as np
    from core.voice.engines.omnivoice_engine import OmniVoiceConfig, OmniVoiceEngine

    engine = OmniVoiceEngine(OmniVoiceConfig(enabled=True))

    class _FakeModel:
        sampling_rate = 24000

        def generate(self, **kwargs):
            assert "profile" not in kwargs
            assert "num_step" not in kwargs
            assert "output_path" not in kwargs
            return [np.zeros(100, dtype=np.float32)]

    monkeypatch.setattr(engine, "_load", lambda: _FakeModel())

    out_path = str(tmp_path / "test_omnivoice.wav")
    result = engine.synthesize_to_file("hello world", output_path=out_path)
    assert Path(result) == Path(out_path)
    assert Path(out_path).exists()


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
    assert "omnivoice" in result.get("fallback_reason", "").lower()


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
