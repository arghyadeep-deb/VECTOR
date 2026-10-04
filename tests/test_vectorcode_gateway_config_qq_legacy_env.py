"""Regression for vectorcode/src/gateway/config.py's _apply_env_overrides():

the legacy QQ_HOME_CHANNEL back-compat branch called
`logging.getLogger(__name__).warning(...)`, but this module only imports
`from loguru import logger` -- `logging` is never imported anywhere in the
file. Any user still setting the legacy QQ_HOME_CHANNEL env var (instead of
the renamed QQBOT_HOME_CHANNEL) would hit a NameError inside
load_gateway_config(), crashing gateway startup, instead of getting the
intended one-time deprecation warning.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from gateway.config import GatewayConfig, Platform, _apply_env_overrides


def test_legacy_qq_home_channel_env_var_does_not_crash():
    config = GatewayConfig()
    env = {
        "QQ_APP_ID": "app123",
        "QQ_CLIENT_SECRET": "secret123",
        "QQ_HOME_CHANNEL": "legacy-chat-id",
    }
    with patch.dict(os.environ, env, clear=True):
        # Must not raise NameError: name 'logging' is not defined
        _apply_env_overrides(config)

    home = config.platforms[Platform.QQBOT].home_channel
    assert home is not None
    assert home.chat_id == "legacy-chat-id"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
