"""VoiceGenerator.generate_voice used a kokoro_onnx API that does not exist (load_model / create_audio) and the video
pipeline awaited the synchronous method, so no narration was ever produced (loop watch, 2026-09-26).

The real-synthesis test uses the local Kokoro model files and skips when they are absent.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "kokoro"
HAVE_MODEL = (MODEL_DIR / "voices-v1.0.bin").exists() and (
    (MODEL_DIR / "kokoro-v1.0.fp16-gpu.onnx").exists() or (MODEL_DIR / "kokoro-v1.0.onnx").exists())


def _generator(monkeypatch):
    from districts.content.voice_generator import VoiceGenerator
    g = VoiceGenerator()
    g._kokoro_dir = MODEL_DIR
    g._available = True
    return g


@pytest.mark.skipif(not HAVE_MODEL, reason="local Kokoro model files not present")
def test_generate_voice_writes_a_real_wav(isolated_vector_db, tmp_path, monkeypatch):
    out = tmp_path / "hello.wav"
    r = _generator(monkeypatch).generate_voice("Hello, this is VECTOR.", output_path=str(out))
    assert r["status"] == "success", r
    assert out.exists() and out.stat().st_size > 2000
    with wave.open(str(out), "rb") as w:
        assert w.getnframes() / w.getframerate() > 0.5, "narration should be at least half a second long"
    assert r["duration_sec"] > 0.5


def test_no_model_files_is_a_clear_error_not_a_crash(isolated_vector_db, tmp_path, monkeypatch):
    g = _generator(monkeypatch)
    g._kokoro_dir = tmp_path  # empty
    r = g.generate_voice("hi", output_path=str(tmp_path / "x.wav"))
    assert r["status"] == "error" and "Kokoro" in r["message"]


def test_video_pipeline_does_not_await_the_synchronous_generator():
    from districts.content import video_pipeline
    from districts.content.voice_generator import VoiceGenerator
    assert not inspect.iscoroutinefunction(VoiceGenerator.generate_voice)
    src = inspect.getsource(video_pipeline.VideoPipelineAgent._generate_narration)
    assert "await vg.generate_voice" not in src and "to_thread" in src


@pytest.mark.skipif(not HAVE_MODEL, reason="local Kokoro model files not present")
def test_video_pipeline_narration_produces_a_file(isolated_vector_db, tmp_path):
    from districts.content.video_pipeline import VideoPipelineAgent
    agent = VideoPipelineAgent.__new__(VideoPipelineAgent)
    out = tmp_path / "narration.wav"
    got = asyncio.run(agent._generate_narration("Testing the narration path.", str(out)))
    assert got == str(out) and out.exists() and out.stat().st_size > 2000


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
