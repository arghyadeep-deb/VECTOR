"""Regression for 4 files whose `import requests` was indented inside a
function body, invisible to a plain `grep "^import requests"` scan but
caught by scripts/bug_class_lint.py's AST walker (which traverses nested
scopes, unlike a line-anchored grep). Migrated to httpx per CLAUDE.md's
banned-library policy.

Uses the linter itself (AST-based, so it correctly ignores "requests" as an
English word in a comment) as the authoritative "no banned import remains"
check, plus source-text checks that the equivalent httpx call is present.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from bug_class_lint import run  # noqa: E402

FILES = [
    ROOT / "vectorcode" / "src" / "vector_cli" / "runtime_provider.py",
    ROOT / "vectorcode" / "src" / "scripts" / "discord-voice-doctor.py",
    ROOT / "vectorcode" / "src" / "tools" / "transcription_tools.py",
    ROOT / "vectorcode" / "src" / "tools" / "tts_tool.py",
]


def test_none_of_the_four_files_have_a_requests_import():
    result = run(FILES, check=True, report=False)
    offenders = [f for f in result.blocking if any(f.path == p for p in FILES)]
    assert not offenders, f"banned import still present: {offenders}"


def test_runtime_provider_auto_detect_uses_httpx():
    source = FILES[0].read_text(encoding="utf-8")
    assert "httpx.get(" in source
    assert "resp.is_success" in source


def test_discord_voice_doctor_uses_httpx():
    source = FILES[1].read_text(encoding="utf-8")
    assert "httpx.get(" in source
    assert "httpx.TimeoutException" in source
    assert "httpx.ConnectError" in source


def test_transcription_tools_xai_stt_uses_httpx():
    source = FILES[2].read_text(encoding="utf-8")
    assert "httpx.post(" in source


def test_tts_tool_uses_httpx():
    source = FILES[3].read_text(encoding="utf-8")
    assert source.count("httpx.post(") == 3
