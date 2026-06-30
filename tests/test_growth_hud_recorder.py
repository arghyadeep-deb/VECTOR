"""Task 2 — HUD recorder: 9:16 viewport, fires a live task during capture,
degrades gracefully without Playwright."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_recorder_9x16_and_triggers_live_task(monkeypatch, tmp_path):
    from districts.growth import hud_recorder as hr
    calls = {}
    monkeypatch.setattr(hr, "_PLAYWRIGHT_OK", True)
    monkeypatch.setattr(hr, "_playwright_capture",
        lambda url, vp, dur, on_ready: (calls.update(vp=vp, ready=on_ready()) or str(tmp_path / "hud.webm")))
    monkeypatch.setattr(hr, "_ffmpeg_mux", lambda v, a, out, captions=None: str(tmp_path / "reel.mp4"))
    rec = hr.HUDRecorder()
    out = rec.record(narration_wav=str(tmp_path / "n.wav"), duration_s=12.0,
                     trigger_task=lambda: calls.setdefault("task", True))
    assert out.endswith(".mp4")
    assert calls["vp"] == (1080, 1920)   # vertical 9:16
    assert calls.get("task") is True      # live task fired during capture window


def test_recorder_degrades_without_playwright(monkeypatch):
    from districts.growth import hud_recorder as hr
    monkeypatch.setattr(hr, "_PLAYWRIGHT_OK", False)
    assert hr.HUDRecorder().record("n.wav", 5.0, lambda: None) is None  # never crashes


if __name__ == "__main__":
    print("run via pytest")
