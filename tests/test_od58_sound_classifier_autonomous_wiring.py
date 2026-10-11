"""OD-58 regressions for autonomous ambient-sound classification."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.mark.asyncio
async def test_observe_tick_samples_with_real_classifier_each_tick(monkeypatch):
    """The observe hook must execute the classifier, not stop at a mocked hook."""
    from core.config import CONFIG
    from core.loop.autonomous_loop import AutonomousLoop
    from core.voice import ambient_listener

    calls: list[int] = []

    def _rec(samples: int, **_kwargs):
        calls.append(samples)
        return np.zeros((samples, 1), dtype=np.float32)

    monkeypatch.setitem(CONFIG["voice"], "ambient_enabled", True)
    monkeypatch.setitem(CONFIG["sensing"], "sound_enabled", True)
    monkeypatch.setattr(ambient_listener, "_load_consent", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(rec=_rec),
    )

    loop = AutonomousLoop()
    loop._ambient = SimpleNamespace(
        _consent_given=True,
        listen_tick=lambda: asyncio.sleep(0, result=None),
    )

    await loop._observe_tick()
    await loop._observe_tick()

    assert len(calls) == 2
    assert loop._sound_classifier.last_label == "silence"


@pytest.mark.asyncio
async def test_observe_tick_does_not_capture_without_ambient_consent(monkeypatch):
    """The autonomous observer must honor the same consent gate as launcher startup."""
    from core.config import CONFIG
    from core.loop.autonomous_loop import AutonomousLoop
    from core.voice import ambient_listener

    ambient_calls: list[str] = []
    sound_calls: list[str] = []

    class _Ambient:
        _consent_given = False

        async def listen_tick(self):
            ambient_calls.append("listen")
            return None

    class _Sound:
        def sample_and_classify(self):
            sound_calls.append("sample")

    monkeypatch.setitem(CONFIG["voice"], "ambient_enabled", True)
    monkeypatch.setitem(CONFIG["sensing"], "sound_enabled", True)
    monkeypatch.setattr(ambient_listener, "_load_consent", lambda: False)

    loop = AutonomousLoop()
    loop._ambient = _Ambient()
    loop._sound_classifier = _Sound()

    await loop._observe_tick()

    assert ambient_calls == []
    assert sound_calls == []


@pytest.mark.asyncio
async def test_alert_frame_reaches_real_emergency_dispatch_and_is_debounced(monkeypatch):
    """A rapid duplicate uses real emergency._emit but reaches its receiver once."""
    from core.config import CONFIG
    from core.sensing.sound_classifier import SoundClassifier
    from districts.emergency import main as emergency_main

    received: list[tuple] = []

    class _EmergencyReceiver:
        async def emit_signal(self, domain, signal_name, value, source, context=None):
            received.append((domain, signal_name, value, source, context))
            return None

    monkeypatch.setitem(CONFIG["sensing"], "sound_alert_cooldown_sec", 60.0)
    emergency_main.set_instance(_EmergencyReceiver())
    try:
        classifier = SoundClassifier()
        alert = np.full(8000, 0.5, dtype=np.float32)

        assert classifier.classify_frame(alert) == "alert"
        assert classifier.classify_frame(alert) == "alert"
        await asyncio.sleep(0)

        assert received == [
            ("environment", "alert_sound", True, "sound_classifier", None)
        ]
    finally:
        emergency_main.set_instance(None)


def test_missing_microphone_and_model_degrade_without_raising(monkeypatch, tmp_path):
    from core.config import CONFIG
    from core.sensing.sound_classifier import SoundClassifier

    missing_model = tmp_path / "missing-yamnet.onnx"
    monkeypatch.setitem(CONFIG, "sound_model_path", str(missing_model))

    classifier = SoundClassifier()
    classifier._sd = SimpleNamespace(rec=lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("no default input device")
    ))

    assert classifier._onnx_session is None
    assert classifier.sample_and_classify() == "unknown"
    assert classifier.sample_and_classify() == "unknown"
    assert classifier.is_active is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
