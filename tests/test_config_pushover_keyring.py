"""Regression for core/config.py:

PUSHOVER_TOKEN/PUSHOVER_USER are plain pydantic SecretStr/str fields on
VectorSettings, populated only from os.environ/.env by pydantic-settings
BaseSettings -- unlike SMTP_PASS/IMAP_PASS, which are correctly routed
through core.security.secrets_manager.get_secret()'s keyring-first lookup.

scripts/migrate_secrets_to_keyring.py explicitly lists PUSHOVER_TOKEN and
PUSHOVER_USER as migration targets and documents "After migration, secrets
are read from keyring as fallback when .env doesn't have them. The .env
file can be deleted once all secrets are in keyring." Before this fix, that
promise was false for Pushover specifically: CONFIG["api_keys"]
["pushover_token"]/CONFIG["pushover_token"] (and the mirrored *_user keys)
never checked keyring, so every real call site -- core/loop/
permission_gateway.py's RED-tier owner-approval flow, districts/emergency/
escalation.py's CRITICAL-severity alerts, districts/health/*, districts/
security/alert_manager.py -- would silently stop sending Pushover
notifications the moment the owner followed that script's own documented
workflow and removed the token from .env.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import core.security.secrets_manager as secrets_manager
from core.config import VectorSettings, _get_secret


def _settings_with_no_env_file(monkeypatch):
    monkeypatch.delenv("PUSHOVER_TOKEN", raising=False)
    monkeypatch.delenv("PUSHOVER_USER", raising=False)
    return VectorSettings(_env_file=None)


def test_pushover_token_falls_back_to_keyring(monkeypatch):
    s = _settings_with_no_env_file(monkeypatch)
    assert s.PUSHOVER_TOKEN.get_secret_value() == ""  # no env, no .env -> pydantic field is empty

    with patch.object(secrets_manager, "_keyring_get", return_value="keyring-pushover-token"):
        resolved = _get_secret("PUSHOVER_TOKEN", s.PUSHOVER_TOKEN.get_secret_value())
    assert resolved == "keyring-pushover-token"


def test_pushover_user_falls_back_to_keyring(monkeypatch):
    s = _settings_with_no_env_file(monkeypatch)
    assert s.PUSHOVER_USER == ""

    with patch.object(secrets_manager, "_keyring_get", return_value="keyring-pushover-user"):
        resolved = _get_secret("PUSHOVER_USER", s.PUSHOVER_USER)
    assert resolved == "keyring-pushover-user"


def test_pushover_env_var_still_takes_precedence_over_keyring(monkeypatch):
    monkeypatch.setenv("PUSHOVER_TOKEN", "env-pushover-token")
    s = VectorSettings(_env_file=None)

    with patch.object(secrets_manager, "_keyring_get", return_value="keyring-pushover-token"):
        resolved = _get_secret("PUSHOVER_TOKEN", s.PUSHOVER_TOKEN.get_secret_value())
    assert resolved == "env-pushover-token"


def test_config_source_routes_pushover_through_get_secret():
    """Guard against silently reverting to the bare .get_secret_value()/plain
    attribute access that has no keyring fallback at all."""
    src = Path(__file__).parent.parent.joinpath("core", "config.py").read_text(encoding="utf-8")
    pushover_lines = [
        ln for ln in src.splitlines()
        if ('"pushover_token":' in ln or '"pushover_user":' in ln) and not ln.strip().startswith("#")
    ]
    assert pushover_lines, "no pushover_token/pushover_user lines found in core/config.py"
    for ln in pushover_lines:
        assert "_get_secret(" in ln, f"pushover line lost its keyring fallback: {ln.strip()!r}"
