"""Send message tool — send messages across all configured comms platforms."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def send_message(platform: str, recipient: str, text: str) -> dict:
    """Send a message via a configured communications platform."""
    try:
        bots = {
            "telegram": ("comms.telegram_bot", "TelegramBot"),
            "discord": ("comms.discord_bot", "DiscordBot"),
            "slack": ("comms.slack_bot", "SlackBot"),
            "signal": ("comms.signal_bot", "SignalBot"),
            "whatsapp": ("comms.whatsapp_bot", "WhatsAppBot"),
            "email": ("comms.email_client", "EmailClient"),
        }
        if platform not in bots:
            return {"error": f"Unknown platform: {platform}. Available: {list(bots.keys())}"}
        mod_path, cls_name = bots[platform]
        mod = __import__(mod_path, fromlist=[cls_name])
        cls = getattr(mod, cls_name)
        bot = cls()
        await bot.send(recipient, text)
        return {"status": "sent", "platform": platform, "recipient": recipient}
    except Exception as e:
        return {"error": str(e)}
