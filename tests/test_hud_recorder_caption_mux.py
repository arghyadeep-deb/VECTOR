"""HUDRecorder._ffmpeg_mux must burn captions given an absolute Windows path (it failed on every call: the drive colon and
backslashes broke ffmpeg's filter-graph parser). Uses a real ffmpeg; skips when it is not installed."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from districts.growth import hud_recorder as hr

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def media(tmp_path):
    vid, aud, srt = tmp_path / "v.webm", tmp_path / "a.wav", tmp_path / "c.srt"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=270x480:d=2", "-c:v", "libvpx", str(vid)],
                   capture_output=True, check=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(aud)],
                   capture_output=True, check=True)
    srt.write_text("1\n00:00:00,000 --> 00:00:01,500\nhello caption\n", encoding="utf-8")
    return vid, aud, srt


def test_mux_without_captions(media, tmp_path):
    vid, aud, _ = media
    out = tmp_path / "o1.mp4"
    assert hr._ffmpeg_mux(str(vid), str(aud), str(out)) == str(out) and out.stat().st_size > 1000


def test_mux_burns_captions_from_an_absolute_path(media, tmp_path):
    vid, aud, srt = media
    out = tmp_path / "o2.mp4"
    assert hr._ffmpeg_mux(str(vid), str(aud), str(out), captions=str(srt)) == str(out)
    assert out.stat().st_size > 1000


def test_mux_failure_returns_none_and_never_raises(tmp_path):
    assert hr._ffmpeg_mux(str(tmp_path / "missing.webm"), str(tmp_path / "missing.wav"), str(tmp_path / "o.mp4")) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
