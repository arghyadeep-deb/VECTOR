"""Regression for core/sensing/sound_classifier.py SoundClassifier._emit_emergency_signal():

classify_frame() (called directly, or via the sync sample_and_classify()/
is_speech_active() wrappers) runs with no guarantee of a running asyncio event
loop. _emit_emergency_signal() used to call `asyncio.create_task(...)`
unconditionally -- which raises RuntimeError with no running loop -- caught by
a bare `except Exception` that just logged "suppressed exception (degraded
mode)" and did nothing else. Any loud-sound ("alert") classification reached
from a sync call path therefore silently never emitted the emergency signal.

Fixed: falls back to asyncio.run() when no loop is running, so the coroutine
always actually executes.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from core.sensing.sound_classifier import SoundClassifier


def test_emergency_signal_fires_from_sync_context_with_no_running_loop():
    classifier = SoundClassifier()
    mock_emit = AsyncMock(return_value=None)

    with patch("districts.emergency.main._emit", mock_emit):
        # Called directly from a plain sync function -- no event loop running,
        # matching classify_frame()'s real call shape.
        classifier._emit_emergency_signal()

    # Constructing the coroutine alone calls the mock without ever running
    # it -- the real bug left the coroutine created-but-never-awaited when
    # asyncio.create_task() raised RuntimeError. await_count (not call_count)
    # is the only way to tell the coroutine was actually driven to completion.
    mock_emit.assert_awaited_once_with("environment", "alert_sound", True, "sound_classifier")


def test_classify_frame_alert_path_actually_emits():
    import numpy as np

    classifier = SoundClassifier()
    mock_emit = AsyncMock(return_value=None)

    with patch("districts.emergency.main._emit", mock_emit):
        loud = np.ones(8000, dtype=np.float32) * 0.5
        label = classifier.classify_frame(loud)

    assert label == "alert"
    mock_emit.assert_awaited_once()


if __name__ == "__main__":
    test_emergency_signal_fires_from_sync_context_with_no_running_loop()
    test_classify_frame_alert_path_actually_emits()
    print("OK - test_sound_classifier_emergency_signal.py")
