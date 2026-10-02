"""Regression: core/runtime/world_model.py's _voice_section() hardcoded
"tts": "available" / "stt": "available" as literal strings regardless of
real state -- phantom success, inconsistent with every other section in
this file (sensing/agents/memory all query real state with a safe
fallback). Fixed to reuse the existing cached TTS-engine check and report
STT honestly as "unknown" (no cheap live check exists for it)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.runtime.world_model import _voice_section


def test_voice_section_does_not_hardcode_available():
    result = _voice_section()
    assert result["tts"] != "available"
    assert result["stt"] != "available"


def test_voice_section_tts_reflects_real_cached_status():
    result = _voice_section()
    # Whatever the real environment's kokoro model files look like, the
    # value must come from the real check, not a fabricated literal.
    from core.api.routers.status import _get_tts_status_cached
    expected = _get_tts_status_cached().get("tts_engine", "unknown")
    assert result["tts"] == expected


def test_voice_section_stt_is_honestly_unknown():
    result = _voice_section()
    assert result["stt"] == "unknown"


def test_voice_section_survives_tts_status_import_failure(monkeypatch):
    import core.runtime.world_model as wm

    def _boom():
        raise RuntimeError("status module unavailable")

    monkeypatch.setattr(
        "core.api.routers.status._get_tts_status_cached", _boom, raising=False
    )
    result = wm._voice_section()
    assert result["tts"] == "unknown"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
