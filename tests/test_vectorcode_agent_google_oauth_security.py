"""Regression tests for Google OAuth security invariants."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlencode


SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent import google_oauth


def test_callback_state_uses_constant_time_comparison(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def compare_digest(candidate: str, expected: str) -> bool:
        calls.append((candidate, expected))
        return candidate == expected

    monkeypatch.setattr(google_oauth.secrets, "compare_digest", compare_digest)
    handler = object.__new__(google_oauth._OAuthCallbackHandler)
    handler.path = google_oauth.CALLBACK_PATH + "?" + urlencode(
        {"state": "attacker-state", "code": "authorization-code"}
    )
    responses: list[tuple[int, str]] = []
    handler._respond_html = lambda status, body: responses.append((status, body))
    google_oauth._OAuthCallbackHandler.expected_state = "expected-state"
    google_oauth._OAuthCallbackHandler.captured_code = None
    google_oauth._OAuthCallbackHandler.captured_error = None
    google_oauth._OAuthCallbackHandler.ready = None

    handler.do_GET()

    assert calls == [("attacker-state", "expected-state")]
    assert google_oauth._OAuthCallbackHandler.captured_code is None
    assert google_oauth._OAuthCallbackHandler.captured_error == "state_mismatch"
    assert responses and responses[0][0] == 400
