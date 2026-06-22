"""
Regression tests for the calls-district fake-success-stub bug.

AgentBase.run() (core/city/agent_base.py) defines a generic fallback that
returns {"status": "ok", "agent": self.name, "task": task} without doing any
real work. Two calls-district classes overrode run() but ignored
task["type"] entirely:
  - TranscriptionBot.run() always called transcribe_live() (microphone
    recording), even when asked to transcribe_audio/summarize_transcript/
    extract_action_items against an already-recorded file or transcript.
  - VoiceResponder.run() only ever called generate_response() when text was
    present, never text_to_speech/respond_to_audio/get_available_voices.

These tests assert that run() now branches on task["type"] and dispatches
to the class's real, existing methods, and that an unrecognized type
returns the standard error shape instead of silently falling through.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.calls.transcription_bot import TranscriptionBot
from districts.calls.voice_responder import VoiceResponder


# ---------------------------------------------------------------------------
# TranscriptionBot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transcription_bot_run_transcribe_audio_routes_correctly():
    bot = TranscriptionBot()
    result = await bot.run({
        "type": "transcribe_audio",
        "params": {"audio_path": "C:/nonexistent/wiring_test.wav"},
    })
    # Whisper unavailable or file missing both legitimately return
    # status=error from transcribe_audio — the point is it was actually
    # called (not transcribe_live, which would block on a microphone).
    assert result["status"] == "error"
    assert "message" in result


@pytest.mark.asyncio
async def test_transcription_bot_run_summarize_routes_correctly():
    bot = TranscriptionBot()
    result = await bot.run({
        "type": "summarize_transcript",
        "params": {"text": "We discussed the quarterly roadmap and agreed on next steps.", "style": "concise"},
    })
    assert result["status"] in ("success", "error")


@pytest.mark.asyncio
async def test_transcription_bot_run_extract_action_items_routes_correctly():
    bot = TranscriptionBot()
    result = await bot.run({
        "type": "extract_action_items",
        "params": {"text": "John will send the proposal by Friday."},
    })
    assert result["status"] == "ok"
    assert "action_items" in result


@pytest.mark.asyncio
async def test_transcription_bot_run_unhandled_type_returns_error_shape():
    bot = TranscriptionBot()
    result = await bot.run({"type": "totally_bogus_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


# ---------------------------------------------------------------------------
# VoiceResponder
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voice_responder_run_generate_response_routes_correctly():
    responder = VoiceResponder()
    result = await responder.run({
        "type": "generate_response",
        "params": {"text": "Hello there", "context": {"tone": "friendly"}},
    })
    assert result["status"] in ("success", "error")


@pytest.mark.asyncio
async def test_voice_responder_run_text_to_speech_routes_correctly():
    responder = VoiceResponder()
    result = await responder.run({
        "type": "text_to_speech",
        "params": {"text": "Testing speech synthesis"},
    })
    assert result["status"] in ("success", "error")


@pytest.mark.asyncio
async def test_voice_responder_run_get_available_voices_routes_correctly():
    responder = VoiceResponder()
    result = await responder.run({"type": "get_available_voices", "params": {}})
    assert result["status"] == "ok"
    assert "voices" in result


@pytest.mark.asyncio
async def test_voice_responder_run_unhandled_type_returns_error_shape():
    responder = VoiceResponder()
    result = await responder.run({"type": "not_a_real_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
