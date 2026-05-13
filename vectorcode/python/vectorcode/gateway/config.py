"""Gateway configuration — platform config, home channels, reset policies."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Platform(str, Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    SIGNAL = "signal"
    WHATSAPP = "whatsapp"
    MATRIX = "matrix"
    FEISHU = "feishu"
    WECOM = "wecom"
    WECHAT = "wechat"
    DINGTALK = "dingtalk"
    EMAIL = "email"
    WEBHOOK = "webhook"


@dataclass
class PlatformConfig:
    enabled: bool = True
    api_key: str = ""
    bot_token: str = ""
    app_id: str = ""
    app_secret: str = ""
    webhook_url: str = ""
    allowed_users: list[str] = field(default_factory=list)
    home_channel: str = ""


@dataclass
class GatewayConfig:
    platforms: dict[str, PlatformConfig] = field(default_factory=dict)
    session_ttl_minutes: int = 60
    max_sessions: int = 100
    debug: bool = False


_defaults = GatewayConfig()


def load_gateway_config(path: Optional[str] = None) -> GatewayConfig:
    """Load gateway configuration. Returns defaults if no config file exists."""
    if not path:
        return _defaults
    try:
        import json
        with open(path) as f:
            data = json.load(f)
        cfg = GatewayConfig()
        for p, pc in data.get("platforms", {}).items():
            cfg.platforms[p] = PlatformConfig(**pc)
        cfg.session_ttl_minutes = data.get("session_ttl_minutes", 60)
        cfg.max_sessions = data.get("max_sessions", 100)
        return cfg
    except Exception:
        return _defaults
