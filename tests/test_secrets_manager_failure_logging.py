"""Regression tests for observable secret-backend failures.

Secret lookup and metadata auditing deliberately degrade instead of crashing,
but they previously swallowed every backend exception without a log.  That
made a broken keyring or audit sink indistinguishable from a missing secret.
The tests keep the fallback behavior while requiring value-free warnings.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.security import secrets_manager


def _captured_messages() -> tuple[list[str], int]:
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(str(message)), level="WARNING")
    return messages, sink_id


def test_keyring_lookup_failure_is_logged_without_secret_value() -> None:
    messages, sink_id = _captured_messages()
    fake_keyring = SimpleNamespace(
        get_password=lambda *_args: (_ for _ in ()).throw(RuntimeError("backend offline")),
    )
    try:
        with patch.dict(sys.modules, {"keyring": fake_keyring}):
            assert secrets_manager._keyring_get("TOP_SECRET_NAME") == ""
    finally:
        logger.remove(sink_id)

    output = "".join(messages)
    assert "keyring lookup failed" in output
    assert "TOP_SECRET_NAME" in output
    assert "backend offline" in output


def test_audit_sink_failure_is_logged() -> None:
    messages, sink_id = _captured_messages()
    with tempfile.TemporaryDirectory() as td:
        # Opening a directory in append mode produces a real filesystem error.
        broken_path = Path(td)
        try:
            with patch.object(secrets_manager, "_audit_path", return_value=broken_path):
                secrets_manager.record_secret_event("read", "API_KEY", "env", True)
        finally:
            logger.remove(sink_id)

    assert "secret audit write failed" in "".join(messages)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
