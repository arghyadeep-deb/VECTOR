"""CaptionGenerator must time captions from real audio timing, never from an LLM.

Root causes (found 2026-09-25 while testing the reel pipeline):
  1. `_parse_caption_blocks` dropped any text written on the same line as the
     `HH:MM:SS --> HH:MM:SS` marker, so the first caption's text vanished.
  2. Timestamps were invented by an LLM that never heard the audio, while
     `generate_subtitles` discarded Whisper's real per-segment start/end.
  3. SRT/VTT output had no milliseconds (`00:00:01 --> 00:00:03`), which is not
     valid SRT (needs `,mmm`) or WebVTT (needs `.mmm`).
Also: the "karaoke" style key had a leading space and could never be selected.
"""
import re

import pytest

from districts.content import caption_generator as cg
from districts.content.caption_generator import CaptionGenerator

SPOKEN = "I am VECTOR. I govern a city of agents, and nothing happens without your approval."
SEGMENTS = [
    {"start": 0.0, "end": 2.5, "text": "I am VECTOR."},
    {"start": 2.5, "end": 6.3, "text": "I govern a city of agents, and nothing happens without your approval."},
]
SRT_TS = r"\d{2}:\d{2}:\d{2},\d{3}"


def _seconds(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _no_llm(*_a, **_k):
    raise AssertionError("timing/splitting must not call an LLM")


@pytest.fixture
def gen(monkeypatch):
    monkeypatch.setattr(cg, "_llm", _no_llm)
    return CaptionGenerator()


def test_real_segment_times_are_kept(gen):
    result = gen.generate_captions(SPOKEN, "standard", segments=SEGMENTS)
    blocks = result["blocks"]
    assert result["status"] == "success"
    assert result["timing"] == "whisper"
    assert blocks[0]["start"] == "00:00:00,000"
    assert blocks[-1]["end"] == "00:00:06,300"


def test_no_spoken_word_is_dropped(gen):
    """Regression for root cause 1: the first caption's text used to vanish."""
    blocks = gen.generate_captions(SPOKEN, "standard", segments=SEGMENTS)["blocks"]
    said = " ".join(b["text"].replace("\n", " ") for b in blocks).split()
    assert said == SPOKEN.split()


def test_blocks_are_ordered_and_do_not_overlap(gen):
    blocks = gen.generate_captions(SPOKEN, "standard", segments=SEGMENTS)["blocks"]
    for b in blocks:
        assert _seconds(b["end"]) > _seconds(b["start"])
    for prev, nxt in zip(blocks, blocks[1:]):
        assert _seconds(nxt["start"]) >= _seconds(prev["end"]) - 1e-6


def test_long_segment_is_split_within_its_own_time_window(gen):
    text = " ".join(["word%02d" % i for i in range(40)])  # ~280 chars
    segs = [{"start": 4.0, "end": 14.0, "text": text}]
    blocks = gen.generate_captions(text, "standard", segments=segs)["blocks"]
    assert len(blocks) > 1
    assert blocks[0]["start"] == "00:00:04,000"
    assert blocks[-1]["end"] == "00:00:14,000"
    cfg = CaptionGenerator.CAPTION_STYLES["standard"]
    for b in blocks:
        lines = b["text"].split("\n")
        assert len(lines) <= cfg["max_lines"]
        assert all(len(line) <= cfg["max_chars_per_line"] for line in lines)


def test_transcript_only_gets_estimated_timing_without_an_llm(gen):
    result = gen.generate_captions(SPOKEN, "standard")
    assert result["status"] == "success"
    assert result["timing"] == "estimated"
    said = " ".join(b["text"].replace("\n", " ") for b in result["blocks"]).split()
    assert said == SPOKEN.split()
    assert result["blocks"][0]["start"] == "00:00:00,000"


def test_known_duration_is_used_when_no_segments(gen):
    result = gen.generate_captions(SPOKEN, "standard", duration=6.3)
    assert result["blocks"][-1]["end"] == "00:00:06,300"


def test_srt_is_valid(gen):
    captions = gen.generate_captions(SPOKEN, "standard", segments=SEGMENTS)
    srt = gen._format_captions(captions["blocks"], "srt")
    assert re.match(rf"^1\n{SRT_TS} --> {SRT_TS}\n", srt)
    assert "00:00:06,300" in srt


def test_vtt_uses_dot_milliseconds(gen):
    captions = gen.generate_captions(SPOKEN, "standard", segments=SEGMENTS)
    vtt = gen._format_captions(captions["blocks"], "vtt")
    assert vtt.startswith("WEBVTT")
    assert re.search(r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}", vtt)
    assert "," not in vtt.split("\n\n", 1)[0].replace("WEBVTT", "")


def test_generate_subtitles_uses_whisper_timing_not_an_llm(gen, tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")

    class FakeBot:
        def transcribe_audio(self, path, language=None):
            return {"status": "success", "text": SPOKEN, "language": "en", "duration": 0,
                    "segments": SEGMENTS}

    import districts.calls.transcription_bot as tb
    monkeypatch.setattr(tb, "TranscriptionBot", FakeBot)

    result = gen.generate_subtitles(str(video), "standard", "srt")
    assert result["status"] == "success"
    assert "00:00:02,500" in result["content"]      # real segment boundary survived
    assert "00:00:06,300" in result["content"]


def test_karaoke_style_is_selectable():
    assert "karaoke" in CaptionGenerator.CAPTION_STYLES
    assert not any(k != k.strip() for k in CaptionGenerator.CAPTION_STYLES)
