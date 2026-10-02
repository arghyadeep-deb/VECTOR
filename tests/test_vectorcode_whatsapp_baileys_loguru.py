"""Regression: vectorcode/src/comms/whatsapp_baileys.py used stdlib
logging.getLogger() instead of loguru (CLAUDE.md rule 6), with 5 %s-style
placeholders and 6 exc_info=True/.exception() calls -- same systemic bug
fixed repeatedly this cycle across sibling vectorcode files.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_module_uses_loguru_not_stdlib_logging():
    import inspect
    from vectorcode.src.comms import whatsapp_baileys
    src = inspect.getsource(whatsapp_baileys)
    assert "from loguru import logger" in src
    assert "import logging" not in src
    assert "logging.getLogger" not in src


def test_no_printf_placeholders_or_bare_exception_calls_remain():
    import inspect
    from vectorcode.src.comms import whatsapp_baileys
    src = inspect.getsource(whatsapp_baileys)
    assert "%s" not in src
    assert "exc_info=True" not in src
    assert "logger.exception(" not in src
    assert src.count("logger.opt(exception=True)") == 6


def test_channel_connect_without_node_fails_cleanly():
    from vectorcode.src.comms.whatsapp_baileys import WhatsAppBaileysChannel
    from vectorcode.src.comms._abc import ChannelStatus
    import vectorcode.src.comms.whatsapp_baileys as mod

    ch = WhatsAppBaileysChannel()
    orig_which = mod.shutil.which
    mod.shutil.which = lambda name: None
    try:
        ch.connect()
    finally:
        mod.shutil.which = orig_which
    assert ch.status() == ChannelStatus.ERROR


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
