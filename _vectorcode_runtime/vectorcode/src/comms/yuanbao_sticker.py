"""Yuanbao sticker handler — sticker send/receive for Yuanbao platform."""

from typing import Optional

from loguru import logger

class StickerInfo:
    def __init__(self, sticker_id: str = "", pack_id: str = "", url: str = ""):
        self.sticker_id = sticker_id
        self.pack_id = pack_id
        self.url = url

async def send_sticker(bot, user_id: str, sticker: StickerInfo) -> bool:
    """Send a sticker to a Yuanbao user."""
    try:
        payload = {"to": user_id, "type": "sticker",
                   "sticker_id": sticker.sticker_id, "pack_id": sticker.pack_id}
        if not bot._ws:
            return False
        from .yuanbao_proto import encode_message
        msg = encode_message(6, payload)
        await bot._ws.send_bytes(msg)
        return True
    except Exception as e:
        logger.warning(f"Sticker send failed: {e}")
        return False
