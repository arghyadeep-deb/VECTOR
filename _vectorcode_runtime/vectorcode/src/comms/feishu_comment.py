"""Feishu comment handler — Drive doc comment threads with AI reply."""

import json
from typing import Any, Callable, Optional

from loguru import logger

try:
    import aiohttp
    _AIOHTTP = True
except ImportError:
    _AIOHTTP = False

class FeishuCommentHandler:
    def __init__(self, app_id: str = "", app_secret: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: Optional[str] = None
        self._comment_callback: Optional[Callable] = None

    def on_comment(self, callback: Callable):
        self._comment_callback = callback

    async def _get_token(self) -> Optional[str]:
        async with aiohttp.ClientSession() as s:
            r = await s.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                            json={"app_id": self.app_id, "app_secret": self.app_secret})
            data = await r.json()
            return data.get("tenant_access_token")

    async def handle_event(self, event: dict):
        if not self._comment_callback: return
        try:
            event_type = event.get("header", {}).get("event_type", "")
            if event_type == "drive.notice.comment_add_v1":
                await self._comment_callback(event)
        except Exception as e:
            logger.warning(f"Feishu comment event failed: {e}")

    async def reply_to_comment(self, doc_token: str, comment_id: str, text: str):
        if not _AIOHTTP or not self._token: return
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://open.feishu.cn/open-apis/drive/v1/files/{doc_token}/comments/{comment_id}/reply",
                headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
                json={"content": json.dumps({"text": text})},
            )
