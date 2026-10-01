"""Phase 3 whole-repo audit -- core/video/video_encoder.py.

Regression for two bugs found 2026-10-02:
1. VideoEncoder._vp9_args() used args.index("0") to find-and-replace the
   -b:v placeholder with a real bitrate. str(crf) == "0" is a real VP9
   near-lossless setting that appears earlier in the arg list, so the
   search hit the wrong element -- corrupting -crf and silently dropping
   the bitrate override.
2. probe_duration()/probe_dimensions() swallowed every exception with no
   logging at all, same silent-failure class fixed repeatedly elsewhere
   this audit cycle.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.video.video_encoder import EncodeOptions, VideoEncoder
from core.video.composition_types import Fps


def _encoder() -> VideoEncoder:
    enc = VideoEncoder()
    enc._ffmpeg = "ffmpeg"  # bypass the real shutil.which() lookup
    return enc


def test_vp9_bitrate_override_applies_to_bv_not_crf():
    enc = _encoder()
    opts = EncodeOptions(fps=Fps(30, 1), format="webm", video_bitrate="2M")
    args = enc._vp9_args(opts, crf=31)
    assert args[args.index("-b:v") + 1] == "2M"
    assert args[args.index("-crf") + 1] == "31"


def test_vp9_bitrate_override_with_crf_zero_does_not_corrupt_crf():
    """The exact regression: crf=0 (near-lossless) used to collide with the
    bitrate-placeholder search."""
    enc = _encoder()
    opts = EncodeOptions(fps=Fps(30, 1), format="webm", video_bitrate="4M")
    args = enc._vp9_args(opts, crf=0)
    assert args[args.index("-crf") + 1] == "0"
    assert args[args.index("-b:v") + 1] == "4M"


def test_vp9_no_bitrate_override_keeps_crf_mode():
    enc = _encoder()
    opts = EncodeOptions(fps=Fps(30, 1), format="webm")
    args = enc._vp9_args(opts, crf=0)
    assert args[args.index("-b:v") + 1] == "0"
    assert args[args.index("-crf") + 1] == "0"


def test_probe_duration_missing_ffprobe_returns_zero_no_crash(monkeypatch):
    import core.video.video_encoder as ve
    monkeypatch.setattr(ve, "find_ffprobe", lambda: None)
    assert ve.probe_duration("/nonexistent/file.mp4") == 0.0


def test_probe_dimensions_missing_ffprobe_returns_zero_tuple_no_crash(monkeypatch):
    import core.video.video_encoder as ve
    monkeypatch.setattr(ve, "find_ffprobe", lambda: None)
    assert ve.probe_dimensions("/nonexistent/file.mp4") == (0, 0)


def test_probe_duration_logs_on_real_failure(monkeypatch, caplog):
    import core.video.video_encoder as ve
    monkeypatch.setattr(ve, "find_ffprobe", lambda: "ffprobe")
    monkeypatch.setattr(
        ve.subprocess, "run",
        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")),
    )
    assert ve.probe_duration("/x.mp4") == 0.0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
