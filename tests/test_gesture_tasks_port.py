"""The gesture handler runs on the MediaPipe Tasks API (the legacy `mp.solutions` no longer exists in mediapipe 0.10.35) and off the
event loop. Real detection needs a hand in front of the camera (owner-only); what is verified here is everything else: the model
bundle loads through the real Tasks API, a hand-less frame yields no hands, the gesture/swipe payloads are built correctly from
landmarks, and streaming never blocks the loop."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import WebSocketDisconnect

from core.api.routers import gesture


def _hand(fingers_up, wrist=(0.5, 0.9), thumb_index_gap=0.3):
    """21 landmarks; fingers_up is 5 booleans (thumb..pinky)."""
    lm = [SimpleNamespace(x=wrist[0], y=wrist[1]) for _ in range(21)]
    tips, mcps = [4, 8, 12, 16, 20], [2, 5, 9, 13, 17]
    for i, up in enumerate(fingers_up):
        lm[mcps[i]] = SimpleNamespace(x=0.5, y=0.5)
        lm[tips[i]] = SimpleNamespace(x=0.5 + (0.3 if i == 0 else 0.0), y=0.3 if up else 0.7)
    lm[8] = SimpleNamespace(x=lm[8].x if not fingers_up[1] else lm[8].x, y=lm[8].y)
    return lm


def _tracker():
    return gesture._HandTracker(None, None, None, None)


@pytest.mark.parametrize("fingers,expected", [
    ([0, 0, 0, 0, 0], "fist"), ([1, 1, 1, 1, 1], "open_palm"), ([0, 1, 0, 0, 0], "point"),
])
def test_gestures_are_classified_from_landmarks(fingers, expected):
    payload = _tracker().payload_from([_hand([bool(f) for f in fingers])])
    assert payload["hand_visible"] and payload["hand_count"] == 1
    assert payload["gesture"] == expected == payload["hands"][0]["gesture"]


def test_no_hands_gives_the_empty_payload_and_resets_the_swipe_history():
    tr = _tracker()
    tr.swipe_x, tr.swipe_y = [0.1, 0.2], [0.1, 0.2]
    payload = tr.payload_from([])
    assert payload["hand_visible"] is False and payload["hands"] == [] and tr.swipe_x == [] and tr.swipe_y == []


def test_a_horizontal_wrist_movement_is_a_swipe():
    tr = _tracker()
    seen = [tr.payload_from([_hand([True] * 5, wrist=(x, 0.5))])["gesture"] for x in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3)]
    assert "swipe_left" in seen and seen[0] == "open_palm"      # the swipe fires once, then the history restarts


def test_two_hands_report_their_distance():
    payload = _tracker().payload_from([_hand([True] * 5, wrist=(0.2, 0.5)), _hand([True] * 5, wrist=(0.8, 0.5))])
    assert payload["hand_count"] == 2 and payload["hand_distance"] == pytest.approx(0.6, abs=1e-3)


def test_the_real_tasks_api_loads_the_model_and_sees_no_hand_in_a_blank_frame():
    np = pytest.importorskip("numpy")
    mp = pytest.importorskip("mediapipe")
    from core.sensing.mediapipe_tasks import ModelUnavailable, create_hand_landmarker

    try:
        landmarker = create_hand_landmarker(2)
    except ModelUnavailable as e:
        pytest.skip(f"hand model not available offline: {e}")
    try:
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((240, 320, 3), dtype=np.uint8))
        assert landmarker.detect_for_video(image, 67).hand_landmarks == []
    finally:
        landmarker.close()


@pytest.mark.asyncio
async def test_streaming_does_not_block_the_event_loop(monkeypatch):
    monkeypatch.setattr(gesture, "_gesture_active", True)
    class Fake:
        cap = object()

        def next_payload(self):
            time.sleep(0.4)
            return {"hand_visible": False}

        def close(self):
            Fake.closed = True

    monkeypatch.setattr(gesture._HandTracker, "open", classmethod(lambda cls, idx=0: (time.sleep(0.5), Fake())[1]))

    class WS:
        def __init__(self):
            self.sent = []

        async def accept(self):
            pass

        async def send_text(self, text):
            if len(self.sent) >= 2:
                raise WebSocketDisconnect()
            self.sent.append(text)

    lag = 0.0
    stop = asyncio.Event()

    async def beat():
        nonlocal lag
        while not stop.is_set():
            t = time.monotonic()
            await asyncio.sleep(0.02)
            lag = max(lag, time.monotonic() - t - 0.02)

    hb = asyncio.create_task(beat())
    ws = WS()
    try:
        await gesture.gesture_ws(ws)
    finally:
        stop.set()
        await hb
    assert len(ws.sent) == 2 and Fake.closed
    assert lag < 0.25, f"the event loop stalled {lag:.2f}s while the gesture stream ran"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
