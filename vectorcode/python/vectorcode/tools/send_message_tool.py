# Ported from GitHub/NousResearch_hermes-agent/repo/tools/send_message_tool.py
"""Send message tool — route messages to configured communication platforms."""
import json
from typing import Any, Optional

from loguru import logger
from .registry import registry


def send_message(
    message: str,
    platform: Optional[str] = None,
    recipient: Optional[str] = None,
    context: Any = None,
) -> str:
    """Send a message via the configured communication platform."""
    try:
        from vectorcode.comms.messenger import Messenger
        messenger = Messenger.global_instance()
        result = messenger.send(message, platform=platform, recipient=recipient)
        return json.dumps({"success": True, "platform": platform or "default"})
    except ImportError:
        return json.dumps({"error": "Messenger not available"})
    except Exception as e:
        logger.error(f"send_message failed: {e}")
        return json.dumps({"error": str(e)})


registry.register(
    name="send_message",
    handler=send_message,
    schema={
        "description": "Send a message via Telegram, Discord, email, or other configured platform.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message content"},
                "platform": {"type": "string", "description": "Platform: telegram, discord, email, slack (default: auto)"},
                "recipient": {"type": "string", "description": "Recipient ID or channel"},
            },
            "required": ["message"],
        },
    },
    toolset="communication",
    risk_level="medium",
    emoji="📨",
)
