"""Regression tests for 2 real bugs found in core/api/routers/voice.py and
core/api/routers/websocket.py during the final batch of the Phase 3
core/api/routers/ deep-verify (Claude self-fork, 2026-09-30).

1. voice.py's POST /voice/studio/generate took a caller-supplied "filename"
   directly into out_dir / fname with zero confinement, while the sibling
   GET /voice/studio/audio/{filename} read endpoint 3 lines away already
   correctly sanitized to a bare basename via Path(filename).name. A
   "../../whatever" filename could write the synthesized WAV anywhere the
   process has write access (arbitrary file write via path traversal).

2. websocket.py's require_auth_handshake() compared the caller-supplied
   token to WS_API_KEY with a plain `!=` instead of a constant-time
   comparison -- a timing side-channel on the same token this cycle already
   protected with secrets.compare_digest()/hmac.compare_digest() everywhere
   else (core/api/tasks.py, core/api/routers/tasks.py,
   core/security/token_blacklist.py).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers.voice import studio_generate
from core.api.routers.websocket import require_auth_handshake


@pytest.mark.asyncio
async def test_studio_generate_rejects_path_traversal_filename():
    out_dir = Path(__file__).resolve().parent.parent / "data" / "voice_output"
    captured_path = {}

    def fake_synthesize_to_file(self, text, out_path, profile):
        captured_path["path"] = out_path
        return {"status": "ok"}

    with patch("core.voice.tts.VoiceTTS.synthesize_to_file", fake_synthesize_to_file):
        result = await studio_generate({
            "text": "hello",
            "filename": "../../../../windows/system32/evil.wav",
        })

    assert result["status"] == "ok"
    written_path = Path(captured_path["path"]).resolve()
    assert written_path.parent == out_dir.resolve(), (
        f"traversal filename escaped voice_output dir: {written_path}"
    )
    assert written_path.name == "evil.wav"


@pytest.mark.asyncio
async def test_studio_generate_accepts_normal_filename():
    captured_path = {}

    def fake_synthesize_to_file(self, text, out_path, profile):
        captured_path["path"] = out_path
        return {"status": "ok"}

    with patch("core.voice.tts.VoiceTTS.synthesize_to_file", fake_synthesize_to_file):
        result = await studio_generate({"text": "hello", "filename": "my_script.wav"})

    assert result["status"] == "ok"
    assert Path(captured_path["path"]).name == "my_script.wav"


@pytest.mark.asyncio
async def test_studio_generate_defaults_when_traversal_strips_to_empty():
    captured_path = {}

    def fake_synthesize_to_file(self, text, out_path, profile):
        captured_path["path"] = out_path
        return {"status": "ok"}

    with patch("core.voice.tts.VoiceTTS.synthesize_to_file", fake_synthesize_to_file):
        result = await studio_generate({"text": "hello", "filename": ".."})

    assert result["status"] == "ok"
    name = Path(captured_path["path"]).name
    assert name.startswith("studio_") and name.endswith(".wav")


def test_require_auth_handshake_uses_constant_time_comparison():
    import core.api.routers.websocket as ws_mod
    assert "secrets" in dir(ws_mod), "websocket.py must import secrets for compare_digest"
    import inspect
    src = inspect.getsource(require_auth_handshake)
    assert "secrets.compare_digest" in src, (
        "require_auth_handshake() must use a timing-safe comparison, not `!=`"
    )
    assert "token != WS_API_KEY" not in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
