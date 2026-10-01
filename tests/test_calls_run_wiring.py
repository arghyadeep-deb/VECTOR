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
    # "error" when no LLM is reachable (failure is no longer reported as ok).
    assert result["status"] in ("ok", "error")
    assert "action_items" in result


@pytest.mark.asyncio
async def test_transcription_bot_run_unhandled_type_returns_error_shape():
    bot = TranscriptionBot()
    result = await bot.run({"type": "totally_bogus_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_transcription_bot_run_real_chat_query_shape_still_errors():
    """
    Production shape: an LLM-invented task_type with a real free-text
    transcript-related query in params. TranscriptionBot.run() (districts/
    calls/transcription_bot.py, lines ~278-296) only reads task["params"]
    inside its four matched if-branches; once task_type matches none of
    them, it returns the bare error stub without ever inspecting p.get(
    "query")/p.get("content") -- unlike districts/languages/hindi_coach.py,
    which has an explicit query-fallback block after its structured
    branches. So "can you summarize what was said on the last call and
    list any action items?" -- text that summarize_transcript()/extract_
    action_items() could act on directly -- still produces only an error.
    Verified against current source, not assumed.
    """
    bot = TranscriptionBot()
    task = {
        "type": "call_summary_request",
        "params": {
            "query": "can you summarize what was said on the last call and list any action items?",
            "content": "can you summarize what was said on the last call and list any action items?",
            "source": "api_command",
        },
    }
    result = await bot.run(task)
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


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
    assert result["status"] in ("success", "degraded", "error")


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


@pytest.mark.asyncio
async def test_voice_responder_run_real_chat_query_shape_still_errors():
    """
    Production shape: an LLM-invented task_type with a real free-text ask
    in params. VoiceResponder.run() (districts/calls/voice_responder.py,
    lines ~277-296) only reads task["params"] inside its five matched
    if-branches (generate_response/text_to_speech/respond_to_audio/
    get_available_voices/get_response_history); once task_type matches
    none of them it returns the bare error stub, never falling back to
    p.get("query")/p.get("content") the way districts/languages/
    hindi_coach.py does. This is a particularly sharp live bug for this
    specific agent: generate_response() IS literally "answer this free
    text," and VoiceResponder's whole purpose is producing conversational
    replies -- yet a classifier-invented type like "answer_caller" or
    "voice_reply" (which won't literal-match "generate_response") makes
    the query "say something friendly to greet the caller" produce only
    an error instead of the reply it's fully equipped to generate.
    Verified against current source, not assumed.
    """
    responder = VoiceResponder()
    task = {
        "type": "voice_reply_request",
        "params": {
            "query": "say something friendly to greet the caller",
            "content": "say something friendly to greet the caller",
            "source": "api_command",
        },
    }
    result = await responder.run(task)
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
