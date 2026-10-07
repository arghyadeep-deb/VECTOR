"""Regression for districts/governance/credential_manager.py:

scan_available_providers()/validate_key() read API keys with a bare
os.getenv(env_var) instead of core.security.secrets_manager.get_secret(),
which checks the OS keyring as a fallback. A key stored only in the keyring
(not an env var or CONFIG["api_keys"]) was therefore reported "not_set" /
unavailable by this district agent, even though every other VECTOR call
site using get_secret() would have found it fine -- the same
secret-storage-abstraction-mismatch bug class fixed elsewhere this cycle.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from districts.governance.credential_manager import CredentialManager, _ENV_KEYS


def _agent():
    return object.__new__(CredentialManager)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for env_var in _ENV_KEYS.values():
        monkeypatch.delenv(env_var, raising=False)


def test_scan_finds_keyring_only_key():
    agent = _agent()
    with patch("core.security.secrets_manager._keyring_get") as mock_keyring:
        mock_keyring.side_effect = lambda name: (
            "sk-ant-keyringkeyringkeyringkeyring1234567890" if name == "ANTHROPIC_API_KEY" else ""
        )
        result = agent.scan_available_providers()
    assert result["providers"]["anthropic"]["available"] is True
    assert result["providers"]["anthropic"]["key_source"] == "keyring"


def test_validate_key_finds_keyring_only_key():
    agent = _agent()
    with patch("core.security.secrets_manager._keyring_get") as mock_keyring:
        mock_keyring.side_effect = lambda name: (
            "sk-ant-keyringkeyringkeyringkeyring1234567890" if name == "ANTHROPIC_API_KEY" else ""
        )
        result = agent.validate_key("anthropic")
    assert result["valid"] is True


def test_scan_reports_env_source_when_env_var_set(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AItestenvkey1234567890")
    agent = _agent()
    with patch("core.security.secrets_manager._keyring_get", return_value=""):
        result = agent.scan_available_providers()
    assert result["providers"]["gemini"]["key_source"] == "env"


def test_scan_reports_none_with_no_key_anywhere():
    agent = _agent()
    with patch("core.security.secrets_manager._keyring_get", return_value=""):
        result = agent.scan_available_providers()
    assert result["providers"]["anthropic"]["key_source"] == "none"
    assert result["providers"]["anthropic"]["available"] is False
