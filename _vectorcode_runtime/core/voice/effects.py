"""Audio effects / DSP chain for the VECTOR voice pipeline.

Python reimplementation of voicebox's effects service (backend/services/effects.py):
a small pluggable post-processing chain applied to synthesized audio. gain / normalize /
delay are pure-numpy (always available); pitch / reverb / chorus / compressor / highpass /
lowpass route through Spotify's `pedalboard` when installed, and are skipped with a warning
if it isn't (guarded — never crash). A chain is a list of {"type": ..., "params": {...}}.
"""

from __future__ import annotations

import sys

__all__ = [
    "AudioEffects",
    "EFFECT_TYPES",
]


from loguru import logger
from core.config import CONFIG  # noqa: F401

import numpy as np

# numpy-native effects work everywhere; the rest need pedalboard.
_NUMPY_EFFECTS = {"gain", "normalize", "delay", "echo"}
_PEDALBOARD_EFFECTS = {"pitch", "reverb", "chorus", "compressor", "highpass", "lowpass"}
EFFECT_TYPES = _NUMPY_EFFECTS | _PEDALBOARD_EFFECTS


class AudioEffects:
    """Apply an ordered chain of effects to a float32 mono audio array."""

    def __init__(self):
        self._pedalboard_ok = self._probe_pedalboard()

    @staticmethod
    def _probe_pedalboard() -> bool:
        try:
            import pedalboard  # noqa: F401
            return True
        except ImportError:
            logger.debug("[VECTOR][voice] pedalboard not installed - only gain/normalize/delay available")
            return False

    def available_effects(self) -> set[str]:
        return EFFECT_TYPES if self._pedalboard_ok else _NUMPY_EFFECTS

    def apply(self, audio, sr: int, chain: list[dict] | None) -> "np.ndarray":
        """Apply the chain in order. Returns a float32 array. Unknown/unavailable effects
        are skipped with a warning rather than raising."""
        out = np.asarray(audio, dtype=np.float32)
        if not chain:
            return out
        for item in chain:
            etype = (item or {}).get("type", "")
            params = (item or {}).get("params", {}) or {}
            try:
                out = self._apply_one(out, sr, etype, params)
            except Exception as e:
                logger.warning(f"[VECTOR][voice] effect {etype!r} failed, skipping: {e}")
        return out.astype(np.float32)

    # ── per-effect dispatch ───────────────────────────────────────────────────
    def _apply_one(self, audio, sr, etype, params):
        if etype == "gain":
            return audio * float(10.0 ** (float(params.get("db", 0.0)) / 20.0))
        if etype == "normalize":
            peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            if peak <= 1e-9:
                return audio
            return audio / peak * float(params.get("peak", 0.99))
        if etype in ("delay", "echo"):
            return self._delay(audio, sr, params)
        if etype in _PEDALBOARD_EFFECTS:
            plugin = self._make_plugin(etype, params)
            if plugin is None:
                logger.warning(f"[VECTOR][voice] effect {etype!r} needs pedalboard - skipped")
                return audio
            from pedalboard import Pedalboard
            return Pedalboard([plugin])(audio, sr)
        logger.warning(f"[VECTOR][voice] unknown effect type {etype!r} - skipped")
        return audio

    @staticmethod
    def _delay(audio, sr, params):
        delay_s = float(params.get("seconds", 0.25))
        decay = float(params.get("decay", 0.4))
        n = int(sr * max(0.0, delay_s))
        if n <= 0 or n >= audio.size:
            return audio
        out = audio.copy()
        out[n:] += decay * audio[:-n]
        m = float(np.max(np.abs(out))) or 1.0
        if m > 1.0:
            out = out / m
        return out

    def _make_plugin(self, etype, params):
        if not self._pedalboard_ok:
            return None
        import pedalboard as pb
        if etype == "pitch":
            return pb.PitchShift(semitones=float(params.get("semitones", 0.0)))
        if etype == "reverb":
            return pb.Reverb(room_size=float(params.get("room_size", 0.5)),
                             wet_level=float(params.get("wet", 0.3)))
        if etype == "chorus":
            return pb.Chorus(rate_hz=float(params.get("rate_hz", 1.0)))
        if etype == "compressor":
            return pb.Compressor(threshold_db=float(params.get("threshold_db", -16.0)),
                                 ratio=float(params.get("ratio", 4.0)))
        if etype == "highpass":
            return pb.HighpassFilter(cutoff_frequency_hz=float(params.get("hz", 80.0)))
        if etype == "lowpass":
            return pb.LowpassFilter(cutoff_frequency_hz=float(params.get("hz", 8000.0)))
        return None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True
    fx = AudioEffects()
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False, dtype=np.float32)
    sine = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

    # numpy-native path (always available): gain then delay
    out = fx.apply(sine, sr, [
        {"type": "gain", "params": {"db": 6.0}},
        {"type": "delay", "params": {"seconds": 0.1, "decay": 0.5}},
    ])
    assert out.shape == sine.shape, out.shape
    assert out.dtype == np.float32
    # +6 dB ~ x2 before the delay normalization; peak should have grown vs input
    assert float(np.max(np.abs(out))) > float(np.max(np.abs(sine)))

    # normalize brings peak to target
    norm = fx.apply(sine, sr, [{"type": "normalize", "params": {"peak": 0.9}}])
    assert abs(float(np.max(np.abs(norm))) - 0.9) < 1e-3

    # unknown effect is skipped, not fatal
    same = fx.apply(sine, sr, [{"type": "does_not_exist"}])
    assert same.shape == sine.shape

    # pedalboard path only if installed
    if fx._pedalboard_ok:
        shifted = fx.apply(sine, sr, [{"type": "pitch", "params": {"semitones": 4}}])
        assert shifted.shape[0] == sine.shape[0]
        print("✅ effects.py OK (with pedalboard)" if ok else "❌ FAILED")
    else:
        print("✅ effects.py OK (pedalboard absent — numpy effects only)" if ok else "❌ FAILED")
