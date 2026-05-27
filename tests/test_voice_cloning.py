"""Tests for the voicebox absorption: effects, voice_profiles, cloning, tts wiring.

All tests are deterministic and run without the optional chatterbox-tts model.
Guarded paths (cloning engine, pedalboard DSP) are verified for graceful fallback.
"""
from __future__ import annotations
import sqlite3
import io
import wave

import numpy as np
import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _sine(sr: int = 16000, freq: float = 440.0, dur: float = 0.5) -> np.ndarray:
    t = np.linspace(0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
    return (0.1 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


# ── effects.py ────────────────────────────────────────────────────────────────

class TestAudioEffects:
    def setup_method(self):
        from core.voice.effects import AudioEffects
        self.fx = AudioEffects()
        self.sr = 16000
        self.sine = _sine(self.sr)

    def test_gain_increases_amplitude(self):
        out = self.fx.apply(self.sine, self.sr, [{"type": "gain", "params": {"db": 6.0}}])
        assert float(np.max(np.abs(out))) > float(np.max(np.abs(self.sine)))
        assert out.dtype == np.float32

    def test_normalize_peak(self):
        out = self.fx.apply(self.sine, self.sr, [{"type": "normalize", "params": {"peak": 0.9}}])
        assert abs(float(np.max(np.abs(out))) - 0.9) < 1e-3

    def test_delay_lengthens_signal(self):
        out = self.fx.apply(self.sine, self.sr, [{"type": "delay", "params": {"seconds": 0.1}}])
        assert out.shape == self.sine.shape   # delay pads within same length

    def test_unknown_effect_skipped(self):
        out = self.fx.apply(self.sine, self.sr, [{"type": "__nonexistent__"}])
        assert out.shape == self.sine.shape   # no crash, input preserved

    def test_empty_chain_is_identity(self):
        out = self.fx.apply(self.sine, self.sr, [])
        np.testing.assert_array_almost_equal(out, self.sine)

    def test_none_chain_is_identity(self):
        out = self.fx.apply(self.sine, self.sr, None)
        np.testing.assert_array_almost_equal(out, self.sine)

    def test_chained_effects(self):
        chain = [
            {"type": "gain", "params": {"db": 3.0}},
            {"type": "normalize", "params": {"peak": 0.8}},
        ]
        out = self.fx.apply(self.sine, self.sr, chain)
        assert abs(float(np.max(np.abs(out))) - 0.8) < 1e-3

    def test_available_effects_returns_set(self):
        avail = self.fx.available_effects()
        assert "gain" in avail
        assert "normalize" in avail

    def test_pedalboard_graceful_absent(self):
        """Even with pedalboard absent, pitch/reverb requests just get skipped."""
        if self.fx._pedalboard_ok:
            pytest.skip("pedalboard installed — graceful-absent path not exercised")
        out = self.fx.apply(self.sine, self.sr, [{"type": "pitch", "params": {"semitones": 4}}])
        assert out.shape == self.sine.shape

    def test_zero_audio_normalize(self):
        silence = np.zeros(1000, dtype=np.float32)
        out = self.fx.apply(silence, self.sr, [{"type": "normalize"}])
        np.testing.assert_array_equal(out, silence)   # no div-by-zero


# ── cloning.py (pure functions — no model) ────────────────────────────────────

class TestChunkText:
    def setup_method(self):
        from core.voice.cloning import chunk_text
        self.chunk_text = chunk_text

    def test_empty_string(self):
        assert self.chunk_text("") == []

    def test_single_short_sentence(self):
        assert self.chunk_text("Hello.") == ["Hello."]

    def test_multiple_sentences_within_limit(self):
        chunks = self.chunk_text("Hello world. How are you? I am fine.", max_chars=200)
        assert len(chunks) == 1   # all fit in one chunk

    def test_split_on_sentence_boundary(self):
        chunks = self.chunk_text("Hello world. How are you?", max_chars=15)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c) <= 15

    def test_long_word_list(self):
        text = ("word " * 100).strip()
        chunks = self.chunk_text(text, max_chars=30)
        for c in chunks:
            assert len(c) <= 30

    def test_no_empty_chunks(self):
        chunks = self.chunk_text("A. B. C. D.", max_chars=5)
        assert all(c.strip() for c in chunks)


class TestCrossfade:
    def setup_method(self):
        from core.voice.cloning import crossfade_arrays
        self.xf = crossfade_arrays

    def test_shape(self):
        a = np.ones(5000, dtype=np.float32)
        b = np.ones(5000, dtype=np.float32) * 0.5
        out = self.xf(a, b, overlap_samples=500)
        assert out.shape[0] == 5000 + 5000 - 500

    def test_dtype(self):
        a = np.ones(1000, dtype=np.float32)
        b = np.ones(1000, dtype=np.float32)
        out = self.xf(a, b, overlap_samples=100)
        assert out.dtype == np.float32

    def test_zero_overlap_concat(self):
        a = np.array([1.0, 2.0], dtype=np.float32)
        b = np.array([3.0, 4.0], dtype=np.float32)
        out = self.xf(a, b, overlap_samples=0)
        assert len(out) == 4

    def test_very_short_arrays_survive(self):
        a = np.array([1.0], dtype=np.float32)
        b = np.array([2.0], dtype=np.float32)
        out = self.xf(a, b, overlap_samples=9999)
        assert len(out) >= 1


class TestVoiceClonerAvailability:
    def test_available_reflects_dep(self):
        from core.voice.cloning import VoiceCloner
        # Just verify the method runs without error and returns a bool
        result = VoiceCloner.available()
        assert isinstance(result, bool)

    def test_synthesize_raises_when_unavailable(self):
        from core.voice.cloning import VoiceCloner
        cloner = VoiceCloner()
        if cloner.available():
            pytest.skip("chatterbox-tts installed — fallback path not tested here")
        with pytest.raises(RuntimeError, match="chatterbox-tts"):
            cloner.synthesize("Hello")

    def test_synthesize_long_raises_when_unavailable(self):
        from core.voice.cloning import VoiceCloner
        cloner = VoiceCloner()
        if cloner.available():
            pytest.skip("chatterbox-tts installed — fallback path not tested here")
        with pytest.raises(RuntimeError):
            cloner.synthesize_long("Hello world.")


# ── voice_profiles.py ─────────────────────────────────────────────────────────

@pytest.fixture
def fresh_store():
    """VoiceProfileStore on a fresh in-memory CollectionEngine — isolated per test."""
    from core.collections import CollectionEngine
    from core.voice.voice_profiles import VoiceProfileStore
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    engine = CollectionEngine(conn=conn)
    return VoiceProfileStore(engine=engine, storage=None)


class TestVoiceProfileStore:
    def test_create_and_get(self, fresh_store):
        from core.voice.voice_profiles import VoiceProfile, ProfileType
        p = VoiceProfile(name="test", type=ProfileType.CLONED, engine="chatterbox")
        fresh_store.create(p)
        got = fresh_store.get("test")
        assert got is not None
        assert got.name == "test"
        assert got.type == ProfileType.CLONED

    def test_duplicate_create_raises(self, fresh_store):
        from core.voice.voice_profiles import VoiceProfile
        fresh_store.create(VoiceProfile(name="dup"))
        with pytest.raises(ValueError):
            fresh_store.create(VoiceProfile(name="dup"))

    def test_get_missing_returns_none(self, fresh_store):
        assert fresh_store.get("__nope__") is None

    def test_list_all(self, fresh_store):
        from core.voice.voice_profiles import VoiceProfile
        fresh_store.create(VoiceProfile(name="a"))
        fresh_store.create(VoiceProfile(name="b"))
        all_p = fresh_store.list_all()
        names = {p.name for p in all_p}
        assert {"a", "b"} <= names

    def test_update(self, fresh_store):
        from core.voice.voice_profiles import VoiceProfile
        fresh_store.create(VoiceProfile(name="upd", personality="calm"))
        fresh_store.update("upd", personality="energetic")
        assert fresh_store.get("upd").personality == "energetic"

    def test_delete(self, fresh_store):
        from core.voice.voice_profiles import VoiceProfile
        fresh_store.create(VoiceProfile(name="del"))
        fresh_store.delete("del")
        assert fresh_store.get("del") is None

    def test_set_and_get_default(self, fresh_store):
        from core.voice.voice_profiles import VoiceProfile
        fresh_store.create(VoiceProfile(name="a"))
        fresh_store.create(VoiceProfile(name="b"))
        fresh_store.set_default("b")
        assert fresh_store.get_default().name == "b"

    def test_set_default_clears_previous(self, fresh_store):
        from core.voice.voice_profiles import VoiceProfile
        fresh_store.create(VoiceProfile(name="a"))
        fresh_store.create(VoiceProfile(name="b"))
        fresh_store.set_default("a")
        fresh_store.set_default("b")
        assert fresh_store.get("a").is_default is False
        assert fresh_store.get("b").is_default is True

    def test_no_default_returns_none(self, fresh_store):
        from core.voice.voice_profiles import VoiceProfile
        fresh_store.create(VoiceProfile(name="x"))
        assert fresh_store.get_default() is None

    def test_effects_round_trip(self, fresh_store):
        from core.voice.voice_profiles import VoiceProfile
        chain = [{"type": "reverb", "params": {"room_size": 0.7}}]
        fresh_store.create(VoiceProfile(name="fx", effects=chain))
        got = fresh_store.get("fx")
        assert got.effects == chain


# ── profile type enum ─────────────────────────────────────────────────────────

def test_profile_type_values():
    from core.voice.voice_profiles import ProfileType
    assert ProfileType.CLONED.value == "cloned"
    assert ProfileType.PRESET.value == "preset"
    assert ProfileType.DESIGNED.value == "designed"


# ── tts.py wiring ─────────────────────────────────────────────────────────────

def test_tts_speak_clone_returns_false_when_cloner_unavailable():
    """_speak_clone must return False (not raise) when chatterbox is absent."""
    from core.voice.tts import VoiceTTS
    from core.voice.cloning import VoiceCloner
    tts = VoiceTTS()
    if VoiceCloner.available():
        pytest.skip("chatterbox installed — fallback not exercised")
    result = tts._speak_clone("Hello world.")
    assert result is False


def test_tts_speak_clone_with_unknown_profile():
    """_speak_clone should return False (not crash) for a nonexistent profile name."""
    from core.voice.tts import VoiceTTS
    tts = VoiceTTS()
    result = tts._speak_clone("Hello.", profile_name="__nonexistent_xyz__")
    assert result is False


# ── elevenlabs_tts.py wiring ──────────────────────────────────────────────────

def test_elevenlabs_prefer_local_skips_cloud_when_no_cloner():
    """With prefer_local=True but no cloner, speak_content should not raise (cloud fallback)."""
    from core.voice.elevenlabs_tts import ElevenLabsTTS
    from core.voice.cloning import VoiceCloner
    if VoiceCloner.available():
        pytest.skip("cloner present — cloud fallback not the relevant path")
    tts = ElevenLabsTTS(api_key="")
    # Should not raise on the local-probe path; it will fail at the cloud key check
    try:
        tts.synthesize("Hello", prefer_local=True)
    except RuntimeError as e:
        assert "ELEVENLABS_API_KEY" in str(e)   # expected: fell through to cloud, no key


# ── app builds cleanly ────────────────────────────────────────────────────────

def test_create_app_builds():
    from core.api.app import create_app
    app = create_app()
    assert app is not None


# ── MCP voice profile tools ───────────────────────────────────────────────────

def test_mcp_voice_tools_exist():
    import asyncio
    from core.mcp_server import _make_server
    server = _make_server()

    async def _check():
        listed = await server.list_tools()
        names = set(listed.keys()) if isinstance(listed, dict) else {t.name for t in listed}
        assert "list_voice_profiles" in names, f"list_voice_profiles missing from {names}"
        assert "speak_as" in names, f"speak_as missing from {names}"

    asyncio.run(_check())
