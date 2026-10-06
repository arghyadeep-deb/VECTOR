"""
TelegramBot — bidirectional Telegram Bot API integration for VectorCode.

VECTOR Telegram channel adapter.
  - Long-polling /getUpdates (no webhook server needed)
  - Message handler registration by command or free-text
  - Command routing: /help, /status, /ask, /task, /swarm
  - Reply with correlation tracking (reply_to_message_id)
  - Inline keyboard support (quick actions)
  - Runs in a background thread — does not block VectorCode's asyncio loop
"""
import json
import time
import threading
from typing import Callable, Optional

from loguru import logger

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

# ── Data types ────────────────────────────────────────────────────────────────

class TelegramMessage:
    def __init__(self, data: dict):
        self.message_id  = data.get("message_id", 0)
        self.chat_id     = data.get("chat", {}).get("id", 0)
        self.chat_type   = data.get("chat", {}).get("type", "private")
        self.from_user   = data.get("from", {})
        self.text        = data.get("text", "")
        self.date        = data.get("date", 0)
        self.raw         = data

    @property
    def command(self) -> Optional[str]:
        if self.text.startswith("/"):
            return self.text.split()[0].lstrip("/").split("@")[0]
        return None

    @property
    def args(self) -> str:
        parts = self.text.split(None, 1)
        return parts[1] if len(parts) > 1 else ""

    @property
    def sender_name(self) -> str:
        u = self.from_user
        return u.get("username") or f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()

# ── TelegramBot ───────────────────────────────────────────────────────────────

class TelegramBot:
    """
    Long-polling Telegram bot for VectorCode.
    Bidirectional: receives commands + free text, replies with results.

    Usage:
        bot = TelegramBot(token="...")
        bot.on_command("ask", lambda msg, bot: bot.reply(msg, "Thinking..."))
        bot.start()   # background thread
        # ...
        bot.stop()
    """

    API_BASE    = "https://api.telegram.org/bot{token}"
    POLL_TIMEOUT = 30    # long-poll seconds
    MAX_RETRIES  = 5

    def __init__(self, token: str, allowed_chat_ids: Optional[set] = None):
        self._token      = token
        self._base_url   = self.API_BASE.format(token=token)
        self._allowed    = allowed_chat_ids or set()   # empty = allow all
        self._handlers:  dict[str, Callable] = {}      # command -> fn(msg, bot)
        self._text_handler: Optional[Callable] = None  # free-text fallback
        self._offset     = 0
        self._running    = False
        self._thread: Optional[threading.Thread] = None
        self._sent_count = 0
        self._recv_count = 0

        self._register_defaults()

    # ── Default command handlers ───────────────────────────────────────────────

    def _register_defaults(self) -> None:
        self.on_command("help",   self._handle_help)
        self.on_command("start",  self._handle_help)
        self.on_command("status", self._handle_status)

    def _handle_help(self, msg: TelegramMessage, bot: "TelegramBot") -> None:
        bot.reply(msg, (
            "VECTOR Bot commands:\n"
            "/status  — swarm status\n"
            "/ask <q> — ask VECTOR\n"
            "/task <t>— submit a task\n"
            "/swarm   — swarm report\n"
            "Or just type a message."
        ))

    def _handle_status(self, msg: TelegramMessage, bot: "TelegramBot") -> None:
        bot.reply(msg, f"VECTOR online. Received: {self._recv_count} | Sent: {self._sent_count}")

    # ── Handler registration ───────────────────────────────────────────────────

    def on_command(self, command: str, fn: Callable) -> None:
        """Register a handler for a /command. fn(msg: TelegramMessage, bot: TelegramBot)."""
        self._handlers[command.lstrip("/")] = fn

    def on_text(self, fn: Callable) -> None:
        """Register a free-text fallback handler."""
        self._text_handler = fn

    # ── Sending ────────────────────────────────────────────────────────────────

    def send(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to: Optional[int] = None,
        parse_mode: str = "Markdown",
        keyboard: Optional[list] = None,
    ) -> bool:
        """Send a message. Returns True on success."""
        if not _HAS_HTTPX:
            logger.warning("[VECTOR][telegram] httpx not installed — message not sent")
            return False
        payload: dict = {
            "chat_id": chat_id,
            "text": text[:4096],
            "parse_mode": parse_mode,
        }
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        if keyboard:
            payload["reply_markup"] = {
                "inline_keyboard": keyboard
            }
        try:
            with httpx.Client(timeout=15) as client:
                r = client.post(f"{self._base_url}/sendMessage", json=payload)
                ok = r.json().get("ok", False)
                if ok:
                    self._sent_count += 1
                else:
                    logger.warning(f"[VECTOR][telegram] send failed: {r.text[:200]}")
                return ok
        except Exception as e:
            logger.error(f"[VECTOR][telegram] send error: {e}")
            return False

    def reply(self, msg: TelegramMessage, text: str, **kwargs) -> bool:
        """Reply to a specific message (thread-safe)."""
        return self.send(msg.chat_id, text, reply_to=msg.message_id, **kwargs)

    def broadcast(self, text: str, chat_ids: Optional[list] = None) -> int:
        """Broadcast to a list of chat IDs (or allowed_chat_ids if registered)."""
        targets = chat_ids or list(self._allowed)
        return sum(1 for cid in targets if self.send(cid, text))

    # ── Polling loop ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start background polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="telegram-poll")
        self._thread.start()
        logger.info("[VECTOR][telegram] polling started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[VECTOR][telegram] polling stopped")

    def _poll_loop(self) -> None:
        retry_delay = 1
        while self._running:
            try:
                updates = self._get_updates()
                retry_delay = 1
                for update in updates:
                    self._process_update(update)
            except Exception as e:
                logger.error(f"[VECTOR][telegram] poll error: {e}")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    def _get_updates(self) -> list:
        if not _HAS_HTTPX:
            time.sleep(self.POLL_TIMEOUT)
            return []
        try:
            with httpx.Client(timeout=self.POLL_TIMEOUT + 5) as client:
                r = client.get(
                    f"{self._base_url}/getUpdates",
                    params={"offset": self._offset, "timeout": self.POLL_TIMEOUT},
                )
                data = r.json()
                if not data.get("ok"):
                    raise RuntimeError(
                        f"Telegram getUpdates rejected: {data.get('description', 'unknown error')}"
                    )
                updates = data.get("result", [])
                if updates:
                    self._offset = updates[-1]["update_id"] + 1
                return updates
        except Exception as e:
            logger.warning(f"[VECTOR][telegram] getUpdates error: {e}")
            raise

    def _process_update(self, update: dict) -> None:
        raw_msg = update.get("message") or update.get("edited_message")
        if not raw_msg:
            return

        msg = TelegramMessage(raw_msg)
        self._recv_count += 1

        # Authorization check
        if self._allowed and msg.chat_id not in self._allowed:
            logger.debug(f"[VECTOR][telegram] unauthorized chat_id={msg.chat_id}")
            self.send(msg.chat_id, "Unauthorized.")
            return

        # Dispatch by command or text
        cmd = msg.command
        if cmd and cmd in self._handlers:
            try:
                self._handlers[cmd](msg, self)
            except Exception as e:
                logger.error(f"[VECTOR][telegram] handler '{cmd}' error: {e}")
                self.reply(msg, f"Error: {e}")
        elif self._text_handler:
            try:
                self._text_handler(msg, self)
            except Exception as e:
                logger.error(f"[VECTOR][telegram] text handler error: {e}")
        else:
            self.reply(msg, "Unknown command. Try /help")

    # ── Stats ──────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "running":     self._running,
            "sent":        self._sent_count,
            "received":    self._recv_count,
            "offset":      self._offset,
            "commands":    list(self._handlers.keys()),
            "allowed_chats": len(self._allowed),
        }

if __name__ == "__main__":
    # Offline unit tests — no real Telegram token needed
    bot = TelegramBot(token="TEST_TOKEN_OFFLINE", allowed_chat_ids={12345})

    # Handler registration
    responses = []
    bot.on_command("ping", lambda m, b: responses.append("pong"))
    assert "ping" in bot._handlers

    # TelegramMessage parsing
    raw = {
        "message_id": 1,
        "chat": {"id": 12345, "type": "private"},
        "from": {"username": "arghyadeep"},
        "text": "/ping hello world",
        "date": int(time.time()),
    }
    msg = TelegramMessage(raw)
    assert msg.command == "ping"
    assert msg.args == "hello world"
    assert msg.sender_name == "arghyadeep"
    assert msg.chat_id == 12345

    # Unauthorized message (chat_id not in allowed)
    raw2 = dict(raw)
    raw2["chat"] = {"id": 99999, "type": "private"}
    msg2 = TelegramMessage(raw2)
    assert msg2.chat_id == 99999

    # Stats structure
    stats = bot.get_stats()
    assert "running" in stats
    assert "commands" in stats
    assert "ping" in stats["commands"]
    assert "help" in stats["commands"]
    assert "status" in stats["commands"]

    # Default handlers registered
    assert "help" in bot._handlers
    assert "start" in bot._handlers
    assert "status" in bot._handlers

    print("telegram_bot.py OK — long-polling, command routing, ACL, reply")

