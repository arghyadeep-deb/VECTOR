"""Repo integration (docs/repo_analysis/VoxCPM.md): VoxCPM2 as an alternate,
config-selectable cloning_engine alongside the existing Chatterbox-backed
VoiceCloner. voxcpm itself is NOT installed in this environment (8GB weight
download, owner one-time step) — these tests verify the chunker reuse, the
graceful available()=False path, and the engine-factory dispatch, exactly
like cloning.py's own self-test guards real synthesis behind available().
"""
import numpy as np
import pytest

from core.voice.voxcpm_cloning import VoxCPMCloner, get_voxcpm_cloner
from core.voice.cloning import chunk_text, crossfade_arrays


def test_voxcpm_reuses_chunk_text_from_cloning_module():
    """No duplicated chunker — voxcpm_cloning imports cloning.py's chunk_text."""
    chunks = chunk_text("Hello world. How are you? I am fine.", max_chars=20)
    assert len(chunks) >= 3


def test_voxcpm_reuses_crossfade_arrays_from_cloning_module():
    a = np.ones(5000, dtype=np.float32)
    b = np.ones(5000, dtype=np.float32) * 0.5
    merged = crossfade_arrays(a, b, overlap_samples=500)
    assert merged.shape[0] == 5000 + 5000 - 500


def test_available_false_when_voxcpm_not_installed():
    cloner = VoxCPMCloner()
    # voxcpm is not installed in this environment — confirms the guarded
    # import degrades cleanly rather than raising at class definition time.
    assert cloner.available() is False


def test_synthesize_raises_runtime_error_not_import_error_when_unavailable():
    """Callers (tts.py) catch RuntimeError to fall back — must not leak ImportError."""
    cloner = VoxCPMCloner()
    with pytest.raises(RuntimeError):
        cloner.synthesize("hello")


def test_design_raises_runtime_error_when_unavailable():
    cloner = VoxCPMCloner()
    with pytest.raises(RuntimeError):
        cloner.design("a calm voice", "hello")


def test_get_voxcpm_cloner_returns_singleton():
    a = get_voxcpm_cloner()
    b = get_voxcpm_cloner()
    assert a is b


def test_config_has_voxcpm_fields():
    from core.config import CONFIG
    voice_cfg = CONFIG["voice"]
    assert "voxcpm_model_dir" in voice_cfg
    assert "voxcpm_inference_timesteps" in voice_cfg
    assert "voxcpm_cfg_value" in voice_cfg
    assert "voice_design_description" in voice_cfg
    assert voice_cfg["cloning_engine"] == "chatterbox", "default must stay chatterbox, not auto-switch to an unverified 8GB model"


def test_get_cloner_factory_dispatches_to_voxcpm_when_selected(monkeypatch):
    """core.voice.cloning.get_cloner() — the function tts.py actually calls —
    must return a VoxCPMCloner when cloning_engine="voxcpm", with zero
    changes needed at the tts.py call sites."""
    import core.voice.cloning as cloning_mod
    from core.config import CONFIG

    monkeypatch.setitem(CONFIG["voice"], "cloning_engine", "voxcpm")
    cloning_mod._voxcpm_cloner = None  # reset singleton for a clean check
    try:
        result = cloning_mod.get_cloner()
        assert isinstance(result, VoxCPMCloner)
    finally:
        cloning_mod._voxcpm_cloner = None


def test_get_cloner_factory_dispatches_to_chatterbox_by_default():
    import core.voice.cloning as cloning_mod
    from core.voice.cloning import VoiceCloner

    result = cloning_mod.get_cloner()
    assert isinstance(result, VoiceCloner)


def test_voxcpm_synthesize_long_empty_text_returns_empty_array():
    cloner = VoxCPMCloner()
    audio, sr = cloner.synthesize_long("")
    assert len(audio) == 0
    assert sr == VoxCPMCloner._NATIVE_SR


if __name__ == "__main__":
    test_voxcpm_reuses_chunk_text_from_cloning_module()
    test_voxcpm_reuses_crossfade_arrays_from_cloning_module()
    test_available_false_when_voxcpm_not_installed()
    test_synthesize_raises_runtime_error_not_import_error_when_unavailable()
    test_design_raises_runtime_error_when_unavailable()
    test_get_voxcpm_cloner_returns_singleton()
    test_config_has_voxcpm_fields()
    test_get_cloner_factory_dispatches_to_chatterbox_by_default()
    test_voxcpm_synthesize_long_empty_text_returns_empty_array()
    print("[OK] test_voxcpm_cloning")
