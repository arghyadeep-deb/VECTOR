"""Regression for vectorcode/src/vc_security/credential_stripper.py:

CredentialStripper (wired into vector_cli/log_config.py's SanitizingFormatter
for live log output) only covered 6 narrow patterns -- a Stripe key, a DB
connection string, a PEM private key block, and a plain password=/api_key=
assignment could all reach log output unredacted, even though
scanner.py's SecretScanner (used for outbound-content scanning) has always
covered all of them. Also only matched 2 of GitHub's 5 real token prefixes
and only the "xoxb-" (bot) Slack token prefix.
"""
from __future__ import annotations

from vectorcode.src.vc_security.credential_stripper import CredentialStripper


def test_strips_stripe_key():
    stripper = CredentialStripper()
    result = stripper.strip("key=sk_live_abcdefghijklmnopqrstuvwxyz")
    assert "sk_live_abcdefghijklmnopqrstuvwxyz" not in result
    assert "[REDACTED:stripe_key]" in result


def test_strips_db_connection_string():
    stripper = CredentialStripper()
    result = stripper.strip("db=postgres://user:pass@host:5432/db")
    assert "user:pass@host" not in result


def test_strips_private_key_header():
    stripper = CredentialStripper()
    result = stripper.strip("-----BEGIN PRIVATE KEY-----\nMIIB...")
    assert "[REDACTED:private_key]" in result


def test_strips_password_assignment():
    stripper = CredentialStripper()
    result = stripper.strip('password="supersecret123"')
    assert "supersecret123" not in result


def test_strips_github_ghs_and_pat_tokens():
    stripper = CredentialStripper()
    assert "ghs_" not in stripper.strip(
        "ghs_abcdefghijklmnopqrstuvwxyz0123456789"
    ).replace("[REDACTED:github_token]", "")
    assert "github_pat_" not in stripper.strip(
        "github_pat_" + "a" * 40
    ).replace("[REDACTED:github_token]", "")


def test_strips_non_bot_slack_tokens():
    stripper = CredentialStripper()
    result = stripper.strip("xoxp-1234567890-abcdefghijklmnop")
    assert "[REDACTED:slack_token]" in result
