"""Slack bot adapter using slack-bolt Socket Mode."""

from typing import Optional, Callable, Any

from loguru import logger

try:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    _SLACK_AVAILABLE = True
except ImportError:
    _SLACK_AVAILABLE = False

class SlackBot:
    def __init__(self, bot_token: str = "", app_token: str = ""):
        self.bot_token = bot_token
        self.app_token = app_token
        self._app: Any = None
        self._handler: Any = None
        self._message_callback: Optional[Callable] = None

    def on_message(self, callback: Callable):
        self._message_callback = callback

    async def start(self):
        if not _SLACK_AVAILABLE:
            logger.warning("slack-bolt not installed. Run: pip install slack-bolt")
            return
        self._app = App(token=self.bot_token)

        @self._app.event("message")
        def handle_message(event, say):
            if self._message_callback:
                self._message_callback(event)

        self._handler = SocketModeHandler(self._app, self.app_token)
        self._handler.start()

    async def send(self, channel: str, text: str):
        if self._app:
            self._app.client.chat_postMessage(channel=channel, text=text)

    async def stop(self):
        if self._handler:
            self._handler.close()
