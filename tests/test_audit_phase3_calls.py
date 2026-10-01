"""Audit phase 3 — districts/calls: call-content leakage, fail-open and gating fixes.

No real network/audio: ProviderClient and whisper are faked.
"""
import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.agent_base import AgentBase  # noqa: E402
from districts.calls.call_screener import CallScreener  # noqa: E402
from districts.calls.transcription_bot import TranscriptionBot  # noqa: E402
from districts.calls.voice_responder import VoiceResponder  # noqa: E402

SECRET = "my-account-number-4417-secret-words"
PHONE = "+919876543210"


@pytest.fixture
def logs():
    buf: list[str] = []
    hid = logger.add(lambda m: buf.append(str(m)), level="DEBUG", format="{level} {message}")
    yield buf
    logger.remove(hid)


@pytest.fixture
def fake_whisper(monkeypatch):
    """Make `import whisper` succeed so the PRE-fix code reaches its real logic
    (it imported whisper needlessly and errored in environments without it,
    which masked the bugs these tests target)."""
    import sys
    monkeypatch.setitem(sys.modules, "whisper", MagicMock())


@pytest.fixture
def fake_tts_libs(monkeypatch):
    """Fake kokoro_onnx / numpy-backed scipy.io.wavfile so text_to_speech really
    'writes' a file: an unconfined output_path then becomes observable."""
    import sys, types
    import numpy as np
    model = MagicMock()
    model.create_audio.return_value = (np.zeros(8, dtype="float32"), 24000)
    ko = MagicMock()
    ko.load_model.return_value = model
    wav = types.ModuleType("scipy.io.wavfile")
    wav.write = lambda path, sr, data: Path(path).write_bytes(b"RIFFfake")
    io = types.ModuleType("scipy.io"); io.wavfile = wav
    sp = types.ModuleType("scipy"); sp.io = io
    monkeypatch.setitem(sys.modules, "kokoro_onnx", ko)
    monkeypatch.setitem(sys.modules, "scipy", sp)
    monkeypatch.setitem(sys.modules, "scipy.io", io)
    monkeypatch.setitem(sys.modules, "scipy.io.wavfile", wav)


def _screener(tmp_path):
    with patch.object(CallScreener, "_load_contacts", return_value=None):
        sc = CallScreener.__new__(CallScreener)
        AgentBase.__init__(sc, str(uuid.uuid4()), "CallScreener", "calls")
    sc._known_contacts = {}
    sc._call_history = []
    sc._spam_threshold = 0.7
    sc._auto_reject_enabled = True
    sc._contacts_file = tmp_path / "c.json"
    return sc


def _bot():
    bot = TranscriptionBot.__new__(TranscriptionBot)
    AgentBase.__init__(bot, str(uuid.uuid4()), "TranscriptionBot", "calls")
    bot._whisper_model = "base"
    bot._sample_rate = 16000
    bot._whisper = None
    bot._whisper_init_attempted = True
    return bot


def _responder():
    r = VoiceResponder.__new__(VoiceResponder)
    AgentBase.__init__(r, str(uuid.uuid4()), "VoiceResponder", "calls")
    r._voice_config = {}
    r._kokoro_dir = Path("./models/kokoro")
    r._tts_available = True
    r._response_history = []
    return r


class _FakePC:
    """Records chat kwargs; returns .content or raises."""
    calls: list[dict] = []
    content = "ok"
    exc: Exception | None = None

    async def chat(self, **kw):
        _FakePC.calls.append(kw)
        if _FakePC.exc:
            raise _FakePC.exc
        return MagicMock(content=_FakePC.content)


@pytest.fixture
def fakepc():
    _FakePC.calls = []
    _FakePC.content = "ok"
    _FakePC.exc = None
    with patch("core.inference.provider_client.ProviderClient", _FakePC):
        yield _FakePC


# ── cloud routing: call content must be local-only ──────────────────────────
def test_summarize_is_sensitive_local_only(fakepc):
    _bot().summarize_transcript(SECRET)
    assert fakepc.calls and fakepc.calls[0].get("sensitive") is True


def test_action_items_is_sensitive_local_only(fakepc):
    _bot().extract_action_items(SECRET)
    assert fakepc.calls and fakepc.calls[0].get("sensitive") is True


def test_voice_response_is_sensitive_local_only(fakepc):
    _responder().generate_response(SECRET)
    assert fakepc.calls and fakepc.calls[0].get("sensitive") is True


def test_spam_llm_is_sensitive_local_only(tmp_path, fakepc):
    fakepc.content = "NOT_SPAM"
    _screener(tmp_path)._analyze_spam_with_llm(PHONE)
    assert fakepc.calls and fakepc.calls[0].get("sensitive") is True


def test_route_policy_goes_local_for_these_kwargs():
    from core.inference.route_policy import decide_route
    assert decide_route("x", district="calls", sensitive=True).local_only


# ── transcript/exception leakage in logs and results ────────────────────────
def test_summarize_exception_does_not_leak_transcript(fakepc, logs):
    fakepc.exc = RuntimeError(f"400 bad request: prompt was {SECRET}")
    res = _bot().summarize_transcript(SECRET)
    assert res["status"] == "error"
    assert SECRET not in "".join(logs)
    assert SECRET not in str(res)


def test_extract_exception_does_not_leak_transcript(fakepc, logs):
    fakepc.exc = RuntimeError(f"echo {SECRET}")
    _bot().extract_action_items(SECRET)
    assert SECRET not in "".join(logs)


def test_generate_response_does_not_log_or_echo_text(fakepc, logs):
    fakepc.content = f"The reply mentions {SECRET} in full"
    _responder().generate_response("hello")
    assert SECRET not in "".join(logs)
    fakepc.exc = RuntimeError(f"echo {SECRET}")
    res = _responder().generate_response(SECRET)
    assert SECRET not in "".join(logs)
    assert SECRET not in str(res)


def test_screener_logs_mask_phone_numbers(tmp_path, logs):
    sc = _screener(tmp_path)
    with patch.object(sc, "_analyze_spam_with_llm", return_value={"is_spam": False, "ok": True}):
        sc.add_contact(PHONE, "Alice Wonderland", priority="vip")
        sc.screen_call(PHONE)
        sc.screen_call("+15551234567")
        sc.auto_reject("+15551234567")
    out = "".join(logs)
    assert "9876543210" not in out and "5551234567" not in out
    assert "Alice Wonderland" not in out


def test_award_reason_has_no_pii(tmp_path):
    sc = _screener(tmp_path)
    reasons = []
    sc.award_points = lambda pts, reason="": reasons.append(reason)
    sc.add_contact(PHONE, "Alice Wonderland")
    assert all("Alice" not in r for r in reasons)


def test_transcribe_log_and_reason_omit_filename_and_text(tmp_path, logs):
    f = tmp_path / "call_from_919876543210.wav"
    f.write_bytes(b"x")
    bot = _bot()
    bot._whisper = MagicMock()
    bot._whisper.transcribe.return_value = {"text": f" {SECRET} ", "language": "en", "duration": 3.0, "segments": []}
    reasons = []
    bot.award_points = lambda pts, reason="": reasons.append(reason)
    res = bot.transcribe_audio(str(f))
    assert res["status"] == "success" and res["text"] == SECRET
    assert "919876543210" not in "".join(logs) + "".join(reasons)
    assert SECRET not in "".join(logs)


# ── failure reported as success ─────────────────────────────────────────────
def test_empty_transcription_is_not_success(tmp_path, fake_whisper):
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    bot = _bot()
    bot._whisper = MagicMock()
    bot._whisper.transcribe.return_value = {"text": "   ", "segments": []}
    reasons = []
    bot.award_points = lambda pts, reason="": reasons.append(reason)
    res = bot.transcribe_audio(str(f))
    assert res["status"] == "error"
    assert reasons == []


def test_blank_audio_path_is_not_found(fake_whisper):
    bot = _bot()
    bot._whisper = MagicMock()
    assert bot.transcribe_audio("")["status"] == "error"
    bot._whisper.transcribe.assert_not_called()


def test_action_item_failure_not_reported_ok(fakepc):
    fakepc.exc = RuntimeError("down")
    res = asyncio.run(_bot().run({"type": "extract_action_items", "params": {"text": "t"}}))
    assert res["status"] == "error"


def test_canned_fallback_is_degraded_and_does_not_echo(fakepc):
    fakepc.exc = RuntimeError("down")
    res = _responder().generate_response(SECRET)
    assert res["status"] == "degraded" and res["degraded"] is True
    assert SECRET not in res["text"]


def test_respond_to_audio_does_not_speak_canned_fallback(fakepc, tmp_path):
    fakepc.exc = RuntimeError("down")
    r = _responder()
    r.text_to_speech = MagicMock()
    with patch.object(TranscriptionBot, "transcribe_audio",
                      return_value={"status": "success", "text": "hi"}):
        res = asyncio.run(r.respond_to_audio("x.wav"))
    assert res["status"] == "error"
    r.text_to_speech.assert_not_called()


# ── screener fail-safe ──────────────────────────────────────────────────────
@pytest.mark.parametrize("resp,spam,ok", [
    ("NOT_SPAM", False, True), ("not spam", False, True),
    ("SPAM", True, True), ("I am not sure", False, False),
])
def test_spam_verdict_parsing(tmp_path, fakepc, resp, spam, ok):
    fakepc.content = resp
    out = _screener(tmp_path)._analyze_spam_with_llm("+15551234567")
    assert out["is_spam"] is spam and out["ok"] is ok


def test_llm_failure_marks_degraded_never_allow(tmp_path, fakepc):
    fakepc.exc = RuntimeError("down")
    sc = _screener(tmp_path)
    res = sc.screen_call("+15551234567")
    assert res["decision"] != "allow"
    assert res.get("degraded") is True
    res = sc.screen_call("unknown")
    assert res["decision"] != "allow" and res.get("degraded") is True


@pytest.mark.parametrize("cid", ["", "unknown", "private"])
def test_cannot_whitelist_hidden_caller(tmp_path, cid):
    sc = _screener(tmp_path)
    res = sc.add_contact(cid, "Scam", priority="vip")
    assert res["status"] == "error"
    with patch.object(sc, "_analyze_spam_with_llm", return_value={"is_spam": True, "ok": True}):
        assert sc.screen_call("unknown")["decision"] != "allow"


def test_invalid_priority_rejected(tmp_path):
    assert _screener(tmp_path).add_contact(PHONE, "x", priority="godmode")["status"] == "error"


def test_screener_run_none_params(tmp_path):
    sc = _screener(tmp_path)
    with patch.object(sc, "_analyze_spam_with_llm", return_value={"is_spam": False, "ok": True}):
        res = asyncio.run(sc.run({"type": "screen", "params": None}))
    assert res["status"] == "ok"


# ── CWE-22 on TTS output path ───────────────────────────────────────────────
def test_tts_output_path_confined(tmp_path, fake_tts_libs):
    r = _responder()
    res = asyncio.run(r.text_to_speech("hi", output_path=str(tmp_path / "evil.wav")))
    assert res["status"] == "error"
    assert not (tmp_path / "evil.wav").exists()
    from core.runtime_paths import data_path
    sneaky = str(data_path("voice_output") / ".." / "escape.wav")
    assert asyncio.run(r.text_to_speech("hi", output_path=sneaky))["status"] == "error"
    # sibling dir sharing the prefix (startswith bypass)
    sibling = str(data_path("voice_output_evil") / "x.wav")
    assert asyncio.run(r.text_to_speech("hi", output_path=sibling))["status"] == "error"


# ── temp audio cleanup ──────────────────────────────────────────────────────
def test_live_temp_wav_removed_even_on_failure(tmp_path):
    import numpy as np
    bot = _bot()
    bot._whisper = MagicMock()
    created = []
    real_ntf = __import__("tempfile").NamedTemporaryFile

    def ntf(*a, **kw):
        f = real_ntf(*a, dir=str(tmp_path), **kw)
        created.append(Path(f.name))
        return f

    class FakeStream:
        def __init__(self, **kw): self.cb = kw["callback"]
        def __enter__(self):
            self.cb(np.zeros((160, 1), dtype="float32"), 160, None, None)
            return self
        def __exit__(self, *a): return False

    fake_sd = MagicMock(InputStream=FakeStream)
    with patch.dict(sys.modules, {"sounddevice": fake_sd}), \
         patch("districts.calls.transcription_bot.tempfile.NamedTemporaryFile", ntf), \
         patch.object(TranscriptionBot, "transcribe_audio", side_effect=RuntimeError("boom")):
        res = asyncio.run(bot.transcribe_live(0.01))
    assert res["status"] == "error"
    assert created and not created[0].exists()


def test_no_silent_swallow_literal_in_district():
    for f in Path("districts/calls").glob("*.py"):
        assert "[VECTOR] suppressed exception" not in f.read_text(encoding="utf-8")
