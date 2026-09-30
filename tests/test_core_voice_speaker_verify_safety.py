"""Regression tests for fail-closed enrolled speaker verification.

An enrolled verifier previously returned ``(True, 0.0)`` when embedding raised,
allowing an unverifiable speaker through the owner-only action gate.
"""

import numpy as np

from core.voice.speaker_verify import SpeakerVerifier


def _active_verifier() -> SpeakerVerifier:
    verifier = SpeakerVerifier.__new__(SpeakerVerifier)
    verifier._enabled_cfg = True
    verifier._encoder = None
    verifier._engine = "fallback"
    verifier._owner_emb = np.ones(64, dtype=np.float64)
    verifier._threshold_cfg = 0.85
    return verifier


def test_enrolled_verification_failure_does_not_authenticate_speaker(monkeypatch):
    """An embedding failure must deny identity after verification is active."""
    verifier = _active_verifier()

    def broken_embed(audio, sr=16000):
        raise RuntimeError("encoder failed")

    monkeypatch.setattr(verifier, "embed", broken_embed)

    is_owner, similarity = verifier.verify(np.ones(16000, dtype=np.float32))

    assert is_owner is False
    assert similarity == 0.0


def test_stale_voiceprint_shape_does_not_authenticate_speaker(monkeypatch):
    """An incompatible enrolled voiceprint cannot prove owner identity."""
    verifier = _active_verifier()
    monkeypatch.setattr(
        verifier,
        "embed",
        lambda audio, sr=16000: np.ones(32, dtype=np.float64),
    )

    is_owner, similarity = verifier.verify(np.ones(16000, dtype=np.float32))

    assert is_owner is False
    assert similarity == 0.0
