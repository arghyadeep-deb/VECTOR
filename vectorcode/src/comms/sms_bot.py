"""SMS adapter — Twilio-based SMS send/receive."""

from typing import Callable, Optional

from loguru import logger

try:
    from twilio.rest import Client
    _TWILIO = True
except ImportError:
    _TWILIO = False

class SMSBot:
    def __init__(self, account_sid: str = "", auth_token: str = "", from_number: str = ""):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self._client = None
        self._callback: Optional[Callable] = None

    def on_message(self, callback: Callable):
        self._callback = callback

    async def start(self):
        if not _TWILIO:
            logger.warning("twilio not installed. Run: pip install twilio")
            return
        self._client = Client(self.account_sid, self.auth_token)
        logger.info(f"SMS ready from {self.from_number}")

    async def send(self, to: str, text: str):
        if not self._client: return
        self._client.messages.create(body=text, from_=self.from_number, to=to)

    async def stop(self):
                logger.debug("[VECTOR][sms_bot] stop called (no-op)")
