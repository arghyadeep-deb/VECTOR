"""
Shared platform registry for VectorCode.

Single source of truth for platform metadata consumed by both
skills_config (label display) and tools_config (default toolset
resolution).  Import ``PLATFORMS`` from here instead of maintaining
duplicate dicts in each module.
"""

from collections import OrderedDict
from typing import NamedTuple


class PlatformInfo(NamedTuple):
    """Metadata for a single platform entry."""
    label: str
    default_toolset: str


# Ordered so that TUI menus are deterministic.
PLATFORMS: OrderedDict[str, PlatformInfo] = OrderedDict([
    ("cli",            PlatformInfo(label="🖥️  CLI",            default_toolset="vector-cli")),
    ("telegram",       PlatformInfo(label="📱 Telegram",        default_toolset="vector-telegram")),
    ("discord",        PlatformInfo(label="💬 Discord",         default_toolset="vector-discord")),
    ("slack",          PlatformInfo(label="💼 Slack",           default_toolset="vector-slack")),
    ("whatsapp",       PlatformInfo(label="📱 WhatsApp",        default_toolset="vector-whatsapp")),
    ("signal",         PlatformInfo(label="📡 Signal",          default_toolset="vector-signal")),
    ("bluebubbles",    PlatformInfo(label="💙 BlueBubbles",     default_toolset="vector-bluebubbles")),
    ("email",          PlatformInfo(label="📧 Email",           default_toolset="vector-email")),
    ("homeassistant",  PlatformInfo(label="🏠 Home Assistant",  default_toolset="vector-homeassistant")),
    ("mattermost",     PlatformInfo(label="💬 Mattermost",      default_toolset="vector-mattermost")),
    ("matrix",         PlatformInfo(label="💬 Matrix",          default_toolset="vector-matrix")),
    ("dingtalk",       PlatformInfo(label="💬 DingTalk",        default_toolset="vector-dingtalk")),
    ("feishu",         PlatformInfo(label="🪽 Feishu",          default_toolset="vector-feishu")),
    ("wecom",          PlatformInfo(label="💬 WeCom",           default_toolset="vector-wecom")),
    ("wecom_callback", PlatformInfo(label="💬 WeCom Callback",  default_toolset="vector-wecom-callback")),
    ("weixin",         PlatformInfo(label="💬 Weixin",          default_toolset="vector-weixin")),
    ("qqbot",          PlatformInfo(label="💬 QQBot",           default_toolset="vector-qqbot")),
    ("yuanbao",        PlatformInfo(label="🤖 Yuanbao",         default_toolset="vector-yuanbao")),
    ("webhook",        PlatformInfo(label="🔗 Webhook",         default_toolset="vector-webhook")),
    ("api_server",     PlatformInfo(label="🌐 API Server",      default_toolset="vector-api-server")),
    ("cron",           PlatformInfo(label="⏰ Cron",            default_toolset="vector-cron")),
])


def platform_label(key: str, default: str = "") -> str:
    """Return the display label for a platform key, or *default*."""
    info = PLATFORMS.get(key)
    return info.label if info is not None else default
