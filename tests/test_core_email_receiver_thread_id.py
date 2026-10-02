"""Regression: core/email/receiver.py's fetch_new_emails() computed thread_id
with `msg.get("In-Reply-To") or msg.get("References", "").split()[-1] if
msg.get("References") else None` -- Python's ternary binds LOOSER than `or`,
so this parsed as `(In-Reply-To or last-reference) if References else None`,
silently discarding a genuinely present In-Reply-To whenever References was
simply absent (common: not every client sets References on a first reply).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.email.receiver as receiver_mod


def _fake_raw_message(headers: dict[str, str], body: str = "hello") -> bytes:
    lines = [f"{k}: {v}" for k, v in headers.items()]
    lines.append("")
    lines.append(body)
    return ("\r\n".join(lines)).encode("utf-8")


def _run_fetch_with_one_message(headers: dict[str, str]):
    fake_imap = MagicMock()
    fake_imap.search.return_value = ("OK", [b"1"])
    fake_imap.fetch.return_value = ("OK", [(b"1 (RFC822 {100}", _fake_raw_message(headers))])

    with patch.object(receiver_mod, "CONFIG", {
        "IMAP_HOST": "imap.example.com",
        "IMAP_USER": "me@example.com",
        "IMAP_PASS": "secret",
    }), patch.object(receiver_mod.imaplib, "IMAP4_SSL", return_value=fake_imap):
        result = receiver_mod.fetch_new_emails()
    assert len(result) == 1, f"expected exactly 1 fetched email, got {result}"
    return result[0]


def test_in_reply_to_used_even_without_references_header():
    email = _run_fetch_with_one_message({
        "Message-ID": "<new@example.com>",
        "From": "sender@example.com",
        "Subject": "Re: hi",
        "In-Reply-To": "<original@example.com>",
        # No References header at all.
    })
    assert email.thread_id == "<original@example.com>"


def test_falls_back_to_last_reference_when_no_in_reply_to():
    email = _run_fetch_with_one_message({
        "Message-ID": "<new2@example.com>",
        "From": "sender@example.com",
        "Subject": "Re: hi",
        "References": "<a@example.com> <b@example.com>",
    })
    assert email.thread_id == "<b@example.com>"


def test_none_when_neither_header_present():
    email = _run_fetch_with_one_message({
        "Message-ID": "<new3@example.com>",
        "From": "sender@example.com",
        "Subject": "hi",
    })
    assert email.thread_id is None


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
