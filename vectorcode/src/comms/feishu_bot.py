"""Feishu/Lark adapter — WebSocket + Webhook + Comment + Card interaction."""

import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

try:
    import aiohttp
    _AIOHTTP = True
except ImportError:
    _AIOHTTP = False

class FeishuBot:
    def __init__(self, app_id: str = "", app_secret: str = "", verification_token: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token
        self._ws = None
        self._token: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._message_callback: Optional[Callable] = None
        self._comment_handler: Optional[Any] = None

    def on_message(self, callback: Callable):
        self._message_callback = callback

    def set_comment_handler(self, handler):
        self._comment_handler = handler

    async def _ensure_token(self):
        if not _AIOHTTP: return
        async with aiohttp.ClientSession() as s:
            r = await s.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                            json={"app_id": self.app_id, "app_secret": self.app_secret})
            data = await r.json()
            self._token = data.get("tenant_access_token")

    async def start(self):
        if not _AIOHTTP: return
        self._session = aiohttp.ClientSession()
        await self._ensure_token()
        logger.info("Feishu bot ready")

    async def send_text(self, chat_id: str, text: str):
        if not self._token: return
        async with aiohttp.ClientSession() as s:
            await s.post("https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
                        headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
                        json={"receive_id": chat_id, "msg_type": "text", "content": json.dumps({"text": text})})

    async def send_card(self, chat_id: str, title: str, body: str):
        if not self._token: return
        card = {"config": {"wide_screen_mode": True}, "header": {"title": {"tag": "plain_text", "content": title}, "template": "blue"},
                "elements": [{"tag": "markdown", "content": body}]}
        async with aiohttp.ClientSession() as s:
            await s.post("https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
                        headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
                        json={"receive_id": chat_id, "msg_type": "interactive", "content": json.dumps(card)})

    async def upload_image(self, image_path: str) -> Optional[str]:
        if not self._token: return None
        async with aiohttp.ClientSession() as s:
            with open(image_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("image_type", "message")
                data.add_field("image", f, filename="image.png", content_type="image/png")
                r = await s.post("https://open.feishu.cn/open-apis/im/v1/images",
                               headers={"Authorization": f"Bearer {self._token}"}, data=data)
                return (await r.json()).get("data", {}).get("image_key")

    async def handle_webhook(self, body: dict) -> dict:
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge")}
        if body.get("header", {}).get("event_type") == "im.message.receive_v1" and self._message_callback:
            await self._message_callback(body)
        if self._comment_handler:
            await self._comment_handler.handle_event(body)
        return {}

    async def stop(self):
        if self._session: await self._session.close()
