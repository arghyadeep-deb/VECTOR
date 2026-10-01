"""Phase 3 whole-repo audit -- core/video/audio_mixer.py.

Regression for the core bug found 2026-10-02: AudioMixer._mix_multi() built
per-track volume/delay filter chains into `mix_inputs`, then discarded that
and rebuilt the amix input string from the raw, unprocessed [i:a] streams --
silently ignoring every track's volume and start_time for any 2+ track mix.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.video.audio_mixer import AudioMixer, AudioTrack


def _fake_run(returncode=0, stderr=b""):
    result = MagicMock()
    result.returncode = returncode
    result.stderr = stderr
    return result


def test_mix_multi_amix_uses_processed_labels_not_raw_streams():
    """The exact regression: a volume-adjusted track's amix input must be
    its processed filter-chain label, not the raw [i:a] stream."""
    mixer = AudioMixer()
    tracks = [
        AudioTrack(path="a.wav", volume=0.5),
        AudioTrack(path="b.wav", volume=1.0),
    ]
    with patch("core.video.audio_mixer.find_ffmpeg", return_value="ffmpeg"), \
         patch("core.video.audio_mixer.subprocess.run", return_value=_fake_run()) as run_mock:
        mixer._mix_multi(tracks, "/tmp/out.aac", target_duration=5.0, sample_rate=44100)
        cmd = run_mock.call_args[0][0]
        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        # Track 0 was volume-adjusted -> its amix input must be the
        # processed label ([v0v]), never the raw [0:a].
        amix_line = [part for part in filter_complex.split(";") if "amix" in part][0]
        assert "[v0v]" in amix_line, f"expected processed label in amix line, got: {amix_line}"
        assert "[0:a]amix" not in amix_line.replace("[v0v]", ""), (
            "raw [0:a] stream leaked into amix instead of the volume-adjusted label"
        )


def test_mix_multi_delay_label_reaches_amix():
    mixer = AudioMixer()
    tracks = [
        AudioTrack(path="a.wav", start_time=2.0),
        AudioTrack(path="b.wav"),
    ]
    with patch("core.video.audio_mixer.find_ffmpeg", return_value="ffmpeg"), \
         patch("core.video.audio_mixer.subprocess.run", return_value=_fake_run()) as run_mock:
        mixer._mix_multi(tracks, "/tmp/out.aac", target_duration=5.0, sample_rate=44100)
        cmd = run_mock.call_args[0][0]
        filter_complex = cmd[cmd.index("-filter_complex") + 1]
        amix_line = [part for part in filter_complex.split(";") if "amix" in part][0]
        assert "[d0]" in amix_line, f"expected delayed label [d0] in amix line, got: {amix_line}"


def test_generate_silence_logs_on_ffmpeg_failure():
    mixer = AudioMixer()
    with patch("core.video.audio_mixer.find_ffmpeg", return_value="ffmpeg"), \
         patch("core.video.audio_mixer.subprocess.run",
               return_value=_fake_run(returncode=1, stderr=b"boom")), \
         patch("core.video.audio_mixer.logger") as mock_logger:
        mixer._generate_silence("/tmp/out.aac", 1.0, 44100)
        assert mock_logger.warning.called


def test_pad_trim_logs_on_ffmpeg_failure():
    mixer = AudioMixer()
    with patch("core.video.audio_mixer.find_ffmpeg", return_value="ffmpeg"), \
         patch("core.video.audio_mixer.subprocess.run",
               return_value=_fake_run(returncode=1, stderr=b"boom")), \
         patch("core.video.audio_mixer.logger") as mock_logger:
        mixer.pad_trim("/in.wav", "/out.wav", 3.0)
        assert mock_logger.warning.called


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
