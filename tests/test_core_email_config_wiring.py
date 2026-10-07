"""Regression for the 2026-10-07 core/email audit.

core/email/sender.py (SMTP) and core/email/receiver.py (IMAP) read
CONFIG.get("SMTP_HOST"/"SMTP_PORT"/"SMTP_USER"/"SMTP_PASS") and
CONFIG.get("IMAP_HOST"/"IMAP_USER"/"IMAP_PASS"/"EMAIL_ADDRESS") directly off
the top-level CONFIG dict -- but core/config.py never defined any of those
keys anywhere, under any name. Every CONFIG.get(...) call therefore always
fell through to its "" default regardless of what was set in .env, so
districts/communications/email_agent.py's poll_inbox() (which calls
fetch_new_emails() unconditionally) silently no-op'd forever: the IMAP/SMTP
transport could never be configured on, only ever "not configured".
"""
from __future__ import annotations

import importlib
import os

import pytest


_KEYS = (
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS",
    "IMAP_HOST", "IMAP_USER", "IMAP_PASS", "EMAIL_ADDRESS",
)


def test_config_defines_smtp_and_imap_keys():
    from core.config import CONFIG

    for key in _KEYS:
        assert key in CONFIG, f"CONFIG never defines {key!r} -- email transport can never be configured"


def test_config_picks_up_smtp_and_imap_env_vars(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.regression-test.example")
    monkeypatch.setenv("SMTP_USER", "bot@regression-test.example")
    monkeypatch.setenv("IMAP_HOST", "imap.regression-test.example")
    monkeypatch.setenv("IMAP_USER", "bot@regression-test.example")

    import core.config as config_module
    importlib.reload(config_module)
    try:
        assert config_module.CONFIG.get("SMTP_HOST") == "smtp.regression-test.example"
        assert config_module.CONFIG.get("SMTP_USER") == "bot@regression-test.example"
        assert config_module.CONFIG.get("IMAP_HOST") == "imap.regression-test.example"
        assert config_module.CONFIG.get("IMAP_USER") == "bot@regression-test.example"
    finally:
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("IMAP_HOST", raising=False)
        monkeypatch.delenv("IMAP_USER", raising=False)
        importlib.reload(config_module)  # restore process-wide CONFIG for later tests


if __name__ == "__main__":
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"])
    print("✅ test_core_email_config_wiring OK" if result.returncode == 0 else "❌ FAILED")
