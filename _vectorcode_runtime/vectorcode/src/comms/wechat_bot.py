"""WeChat adapter — Tencent iLink Bot API integration (WxWork/iLink REST API)."""

from typing import Callable, Optional

try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False

from loguru import logger

_WECHAT_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"

class WeChatBot:
    def __init__(self, bot_id: str = "", token: str = "", corp_id: str = "", agent_id: str = ""):
        self.bot_id = bot_id
        self.token = token
        self.corp_id = corp_id
        self.agent_id = agent_id
        self._access_token: Optional[str] = None
        self._callback: Optional[Callable] = None
        self._running = False

    def on_message(self, callback: Callable) -> None:
        self._callback = callback

    async def _refresh_token(self) -> None:
        if not _HTTPX or not self.corp_id or not self.token:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{_WECHAT_API_BASE}/gettoken",
                    params={"corpid": self.corp_id, "corpsecret": self.token},
                )
                data = r.json()
                if data.get("errcode", 0) == 0:
                    self._access_token = data["access_token"]
        except Exception as e:
            logger.warning(f"[VECTOR][wechat] token refresh failed: {e}")

    async def start(self) -> None:
        self._running = True
        await self._refresh_token()
        logger.info(f"[VECTOR][wechat] bot {self.bot_id or self.corp_id} ready")

    async def send(self, user_id: str, text: str) -> None:
        if not _HTTPX:
            logger.warning("[VECTOR][wechat] httpx not installed — cannot send")
            return
        if not self._access_token:
            await self._refresh_token()
        if not self._access_token:
            logger.warning("[VECTOR][wechat] no access_token — cannot send")
            return
        try:
            payload = {
                "touser": user_id,
                "msgtype": "text",
                "agentid": self.agent_id,
                "text": {"content": text},
            }
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{_WECHAT_API_BASE}/message/send",
                    params={"access_token": self._access_token},
                    json=payload,
                )
                result = r.json()
                if result.get("errcode", 0) != 0:
                    logger.warning(f"[VECTOR][wechat] send error: {result}")
        except Exception as e:
            logger.error(f"[VECTOR][wechat] send failed: {e}")

    async def stop(self) -> None:
        self._running = False
        self._access_token = None
        logger.info("[VECTOR][wechat] stopped")
