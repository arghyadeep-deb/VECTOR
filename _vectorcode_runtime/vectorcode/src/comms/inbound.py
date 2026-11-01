"""
InboundMessageRouter — routes incoming messages from all platforms to VectorCode.

VECTOR inbound routing layer.
  - Platform-neutral InboundMessage schema
  - Routes by platform, command prefix, or keyword
  - Conversation threading via correlation_id
  - VECTOR REPL integration: forwards to active VectorCode session
  - Rate limiting per sender (avoid spam)
  - Message deduplication (Telegram re-delivery, webhook retries)
"""
import time
import uuid
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from loguru import logger

# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class InboundMessage:
    """Platform-neutral normalized inbound message."""
    id:           str   = field(default_factory=lambda: str(uuid.uuid4())[:12])
    platform:     str   = ""          # telegram, whatsapp, discord, sms, ...
    sender_id:    str   = ""          # platform-specific sender identifier
    sender_name:  str   = ""
    chat_id:      str   = ""          # platform channel / chat / room
    text:         str   = ""
    raw:          dict  = field(default_factory=dict)
    ts:           float = field(default_factory=time.time)
    correlation_id: str = ""          # links reply to originating message
    thread_id:    str   = ""          # conversation thread

@dataclass
class RouteResult:
    """Result of routing an InboundMessage."""
    handled:    bool
    handler:    str   = ""    # which handler processed it
    reply:      str   = ""    # reply text if any
    latency_ms: float = 0.0

# ── InboundMessageRouter ──────────────────────────────────────────────────────

class InboundMessageRouter:
    """
    Routes incoming messages from any platform to the correct handler.

    Usage:
        router = InboundMessageRouter()
        router.on_command("/ask",   ask_handler)
        router.on_platform("sms",  sms_handler)
        router.on_keyword("urgent", urgent_handler)
        router.set_default(default_handler)

        # When a message arrives from Telegram:
        result = router.route(InboundMessage(
            platform="telegram", sender_id="12345", text="/ask what is 2+2"
        ))
    """

    # Rate limit: max N messages per sender per window
    RATE_LIMIT_COUNT  = 20
    RATE_LIMIT_WINDOW = 60.0   # seconds
    DEDUP_WINDOW      = 30.0   # seconds — discard duplicate message IDs

    def __init__(self):
        self._cmd_handlers:      dict[str, Callable] = {}   # "/cmd" -> fn
        self._platform_handlers: dict[str, Callable] = {}   # "telegram" -> fn
        self._keyword_handlers:  list[tuple]          = []  # [(keyword, fn)]
        self._default_handler:   Optional[Callable]   = None

        # Rate limiting: sender_id -> deque of timestamps
        self._rate_buckets: dict[str, deque] = defaultdict(lambda: deque())
        self._lock = threading.Lock()

        # Deduplication: seen message IDs
        self._seen_ids: deque = deque(maxlen=2000)

        # Conversation threads: correlation_id -> [InboundMessage]
        self._threads: dict[str, list] = defaultdict(list)

        # Stats
        self._stats = {
            "received": 0, "handled": 0, "rejected_rate": 0,
            "rejected_dedup": 0, "unhandled": 0,
        }

        self._register_builtins()

    def _register_builtins(self) -> None:
        self.on_command("/ping", lambda msg, r: RouteResult(handled=True, handler="builtin", reply="pong"))

    # ── Handler registration ───────────────────────────────────────────────────

    def on_command(self, command: str, fn: Callable) -> None:
        """Route messages starting with /command to fn(msg, router) -> RouteResult."""
        cmd = command if command.startswith("/") else f"/{command}"
        self._cmd_handlers[cmd] = fn

    def on_platform(self, platform: str, fn: Callable) -> None:
        """Route all messages from a platform to fn(msg, router) -> RouteResult."""
        self._platform_handlers[platform.lower()] = fn

    def on_keyword(self, keyword: str, fn: Callable) -> None:
        """Route messages containing a keyword to fn. Lower priority than command/platform."""
        self._keyword_handlers.append((keyword.lower(), fn))

    def set_default(self, fn: Callable) -> None:
        """Default handler when nothing else matches."""
        self._default_handler = fn

    # ── Core routing ───────────────────────────────────────────────────────────

    def route(self, msg: InboundMessage) -> RouteResult:
        """
        Route an InboundMessage.
        Priority: dedup -> rate-limit -> command -> platform -> keyword -> default
        """
        start = time.time()
        self._stats["received"] += 1

        # Deduplicate
        if msg.id in self._seen_ids:
            self._stats["rejected_dedup"] += 1
            return RouteResult(handled=False, handler="dedup")
        self._seen_ids.append(msg.id)

        # Rate limit
        if not self._check_rate(msg.sender_id):
            self._stats["rejected_rate"] += 1
            logger.warning(f"[VECTOR][inbound] rate limit: {msg.sender_id} on {msg.platform}")
            return RouteResult(handled=False, handler="rate_limit",
                               reply="Too many messages. Please wait.")

        # Thread tracking
        tid = msg.thread_id or msg.correlation_id or msg.chat_id
        with self._lock:
            self._threads[tid].append(msg)
            # Trim thread to 50 messages
            if len(self._threads[tid]) > 50:
                self._threads[tid] = self._threads[tid][-50:]

        result = self._dispatch(msg)
        result.latency_ms = round((time.time() - start) * 1000, 2)

        if result.handled:
            self._stats["handled"] += 1
        else:
            self._stats["unhandled"] += 1

        return result

    def _dispatch(self, msg: InboundMessage) -> RouteResult:
        text = msg.text.strip()
        cmd  = text.split()[0] if text.startswith("/") else None

        # 1. Command handler
        if cmd and cmd in self._cmd_handlers:
            try:
                return self._cmd_handlers[cmd](msg, self) or RouteResult(handled=True, handler=cmd)
            except Exception as e:
                logger.error(f"[VECTOR][inbound] command handler '{cmd}' error: {e}")
                return RouteResult(handled=True, handler=cmd, reply=f"Error: {e}")

        # 2. Platform handler
        plat_fn = self._platform_handlers.get(msg.platform.lower())
        if plat_fn:
            try:
                return plat_fn(msg, self) or RouteResult(handled=True, handler=msg.platform)
            except Exception as e:
                logger.error(f"[VECTOR][inbound] platform handler '{msg.platform}' error: {e}")
                return RouteResult(handled=True, handler=msg.platform, reply=f"Error: {e}")

        # 3. Keyword handler (first match wins)
        text_lower = text.lower()
        for keyword, fn in self._keyword_handlers:
            if keyword in text_lower:
                try:
                    return fn(msg, self) or RouteResult(handled=True, handler=f"keyword:{keyword}")
                except Exception as e:
                    logger.error(f"[VECTOR][inbound] keyword handler '{keyword}' error: {e}")

        # 4. Default
        if self._default_handler:
            try:
                return self._default_handler(msg, self) or RouteResult(handled=True, handler="default")
            except Exception as e:
                logger.error(f"[VECTOR][inbound] default handler error: {e}")

        return RouteResult(handled=False, handler="none")

    # ── REPL bridge ───────────────────────────────────────────────────────────

    def bridge_to_repl(self, repl_fn: Callable) -> None:
        """
        Connect the default handler to a VectorCode REPL function.
        repl_fn(text: str) -> str
        """
        def _handler(msg: InboundMessage, router: "InboundMessageRouter") -> RouteResult:
            try:
                reply = repl_fn(msg.text)
                return RouteResult(handled=True, handler="repl", reply=reply or "")
            except Exception as e:
                logger.error(f"[VECTOR][inbound] repl bridge error: {e}")
                return RouteResult(handled=True, handler="repl", reply=f"VECTOR error: {e}")
        self.set_default(_handler)

    # ── Rate limiting ──────────────────────────────────────────────────────────

    def _check_rate(self, sender_id: str) -> bool:
        now = time.time()
        bucket = self._rate_buckets[sender_id]
        # Remove timestamps outside the window
        while bucket and now - bucket[0] > self.RATE_LIMIT_WINDOW:
            bucket.popleft()
        if len(bucket) >= self.RATE_LIMIT_COUNT:
            return False
        bucket.append(now)
        return True

    # ── Thread / conversation retrieval ───────────────────────────────────────

    def get_thread(self, thread_id: str, limit: int = 10) -> list[InboundMessage]:
        return self._threads.get(thread_id, [])[-limit:]

    # ── Stats ──────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        return dict(self._stats) | {
            "active_threads":  len(self._threads),
            "commands":        list(self._cmd_handlers.keys()),
            "platforms":       list(self._platform_handlers.keys()),
            "keywords":        [kw for kw, _ in self._keyword_handlers],
        }

if __name__ == "__main__":
    router = InboundMessageRouter()

    # Register handlers
    results_log = []

    def ask_handler(msg, r):
        results_log.append(("ask", msg.args if hasattr(msg, "args") else msg.text))
        return RouteResult(handled=True, handler="ask", reply="42")

    router.on_command("/ask", ask_handler)
    router.on_keyword("urgent", lambda m, r: RouteResult(handled=True, handler="urgent"))

    fallback_received = []
    router.set_default(lambda m, r: (fallback_received.append(m.text), RouteResult(handled=True, handler="default"))[1])

    # /ask command routing
    msg1 = InboundMessage(platform="telegram", sender_id="user1", text="/ask what is 2+2")
    res1 = router.route(msg1)
    assert res1.handled
    assert res1.handler == "ask"
    assert res1.reply == "42"

    # Deduplication — same id
    msg1_dup = InboundMessage(
        id=msg1.id, platform="telegram", sender_id="user1", text="/ask duplicate"
    )
    res_dup = router.route(msg1_dup)
    assert not res_dup.handled
    assert res_dup.handler == "dedup"

    # Keyword routing
    msg2 = InboundMessage(platform="sms", sender_id="user2", text="URGENT: server down!")
    res2 = router.route(msg2)
    assert res2.handled and res2.handler == "urgent"

    # Default handler fallback
    msg3 = InboundMessage(platform="discord", sender_id="user3", text="hello vector")
    res3 = router.route(msg3)
    assert res3.handled and res3.handler == "default"
    assert "hello vector" in fallback_received

    # Rate limiting — flood from same sender
    for i in range(25):
        router.route(InboundMessage(platform="telegram", sender_id="spammer", text=f"msg {i}"))
    stats = router.get_stats()
    assert stats["rejected_rate"] > 0

    # Thread tracking
    thread_msgs = router.get_thread("user1")
    assert len(thread_msgs) > 0

    # REPL bridge
    router2 = InboundMessageRouter()
    router2.bridge_to_repl(lambda text: f"echo: {text}")
    res_repl = router2.route(InboundMessage(platform="telegram", sender_id="u1", text="hello"))
    assert res_repl.handled and "echo: hello" in res_repl.reply

    # Stats structure
    stats = router.get_stats()
    assert "received" in stats and "active_threads" in stats
    assert "/ask" in stats["commands"]
    assert "urgent" in stats["keywords"]

    print(f"inbound.py OK — {stats['received']} received, {stats['handled']} handled, "
          f"{stats['rejected_rate']} rate-limited, {stats['rejected_dedup']} deduped")

