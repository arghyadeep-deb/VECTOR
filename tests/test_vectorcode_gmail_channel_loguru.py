"""Regression: vectorcode/src/comms/gmail.py used stdlib logging.getLogger()
instead of loguru (CLAUDE.md rule 6), same systemic bug fixed 23+ times
this cycle across sibling vectorcode files.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_module_uses_loguru_not_stdlib_logging():
    import inspect
    from vectorcode.src.channels import gmail
    src = inspect.getsource(gmail)
    assert "from loguru import logger" in src
    assert "import logging" not in src
    assert "logging.getLogger" not in src


def test_no_bare_exc_info_or_exception_calls_remain():
    """``exc_info=True`` is a silent no-op under loguru."""
    import inspect
    from vectorcode.src.channels import gmail
    src = inspect.getsource(gmail)
    assert "exc_info=True" not in src


def test_gmail_channel_connect_without_credentials_does_not_crash():
    from vectorcode.src.comms.gmail import GmailChannel
    from vectorcode.src.comms._abc import ChannelStatus
    ch = GmailChannel(credentials_path="", token_path="")
    ch.connect()
    assert ch.status() == ChannelStatus.ERROR


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
