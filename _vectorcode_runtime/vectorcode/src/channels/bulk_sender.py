"""
VECTOR Bulk Message Sender — inspired by OpenWA's batch send service.

Sends a list of messages across any BaseChannel with per-provider rate limiting.
Use cases: research broadcast, interview reminders, daily briefings, alert fan-out.

Usage:
    sender = BulkSender(channel)
    result = sender.send_bulk([
        BulkMessage("919876543210", "Hello!"),
        BulkMessage("919876543211", "Update ready"),
    ])
    print(result.sent, result.failed)
"""
from __future__ import annotations

__all__ = ["BulkSender", "BulkMessage", "BulkResult"]

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from vectorcode.src.channels._abc import BaseChannel


# Per-provider default message-per-second limits (conservative, cloud-safe)
_RATE_LIMITS: dict[str, float] = {
    "whatsapp":          80.0,   # Meta Cloud API: ~80 msg/s
    "whatsapp_business": 80.0,
    "telegram":          30.0,   # Telegram: 30 msg/s per bot
    "slack":              1.0,   # Slack: 1 msg/s per channel
    "discord":            5.0,   # Discord: ~5 msg/s
    "sms":                1.0,   # SMS (Twilio): 1 msg/s segment
    "email":              0.5,   # Email: 0.5 msg/s (2s gap)
    "webhook":           10.0,
    "default":            2.0,
}


class _SentRegistry:
    """Short-lived dedup registry — prevents the same (channel, recipient, content)
    from being sent twice within a TTL window. Shared across BulkSender instances
    so overlapping send_bulk calls don't duplicate messages."""

    _entries: dict[str, float] = {}
    _ttl_seconds = 3600  # 1 hour

    @classmethod
    def _key(cls, channel_id: str, recipient: str, content: str) -> str:
        body_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"{channel_id}:{recipient}:{body_hash}"

    @classmethod
    def was_sent(cls, channel_id: str, recipient: str, content: str) -> bool:
        key = cls._key(channel_id, recipient, content)
        sent_at = cls._entries.get(key)
        if sent_at is None:
            return False
        if (time.monotonic() - sent_at) > cls._ttl_seconds:
            del cls._entries[key]
            return False
        return True

    @classmethod
    def mark_sent(cls, channel_id: str, recipient: str, content: str) -> None:
        key = cls._key(channel_id, recipient, content)
        cls._entries[key] = time.monotonic()
        # Periodic cleanup: remove entries older than TTL
        if len(cls._entries) > 1000:
            cutoff = time.monotonic() - cls._ttl_seconds
            expired = [k for k, v in cls._entries.items() if v < cutoff]
            for k in expired:
                del cls._entries[k]


@dataclass
class BulkMessage:
    recipient: str                        # channel/phone/username to send to
    content: str                          # message text
    metadata: dict[str, Any] = field(default_factory=dict)
    conversation_id: str = ""


@dataclass
class BulkResult:
    sent: list[str] = field(default_factory=list)       # recipients that succeeded
    failed: list[str] = field(default_factory=list)     # recipients that failed
    skipped: list[str] = field(default_factory=list)    # skipped (dry_run)
    total: int = 0
    elapsed_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        if not self.total:
            return 0.0
        return len(self.sent) / self.total


class BulkSender:
    """
    Rate-limited batch sender that works with any BaseChannel adapter.

    Computes the inter-message delay from the channel's provider rate limit
    and sleeps between sends to avoid API throttling.
    """

    def __init__(
        self,
        channel: BaseChannel,
        *,
        rate_limit_override: float | None = None,
        fail_fast: bool = False,
    ) -> None:
        self._channel = channel
        self._channel_id = getattr(channel, "channel_id", "default")
        # messages per second → delay between sends
        mps = (rate_limit_override if rate_limit_override is not None else
               _RATE_LIMITS.get(self._channel_id, _RATE_LIMITS["default"]))
        self._delay = 1.0 / max(mps, 0.01)
        self._fail_fast = fail_fast

    def send_bulk(
        self,
        messages: list[BulkMessage],
        *,
        dry_run: bool = False,
        dedup: bool = True,
    ) -> BulkResult:
        """
        Send all messages respecting rate limits.

        Args:
            messages: List of BulkMessage to send.
            dry_run:  If True, log but do not send. Returns all as skipped.
            dedup:    If True (default), skip messages already sent within the
                      last hour (same channel + recipient + content). Prevents
                      duplicates when send_bulk is called with overlapping
                      recipient lists.
        """
        result = BulkResult(total=len(messages))
        start = time.monotonic()

        for i, msg in enumerate(messages):
            if dry_run:
                logger.info("[VECTOR][bulk] DRY RUN [{}/{}] {} → {}",
                            i + 1, len(messages), self._channel_id, msg.recipient[:20])
                result.skipped.append(msg.recipient)
                continue

            # Dedup: skip if this exact message was recently sent
            if dedup and _SentRegistry.was_sent(self._channel_id, msg.recipient, msg.content):
                result.skipped.append(msg.recipient)
                logger.debug("[VECTOR][bulk] dedup skip [{}/{}] → {}",
                             i + 1, len(messages), msg.recipient[:20])
                continue

            try:
                ok = self._channel.send(
                    msg.recipient,
                    msg.content,
                    conversation_id=msg.conversation_id,
                    metadata=msg.metadata or None,
                )
                if ok:
                    result.sent.append(msg.recipient)
                    if dedup:
                        _SentRegistry.mark_sent(self._channel_id, msg.recipient, msg.content)
                    logger.debug("[VECTOR][bulk] sent [{}/{}] → {}",
                                 i + 1, len(messages), msg.recipient[:20])
                else:
                    result.failed.append(msg.recipient)
                    logger.warning("[VECTOR][bulk] failed [{}/{}] → {}",
                                   i + 1, len(messages), msg.recipient[:20])
                    if self._fail_fast:
                        break
            except Exception as e:
                result.failed.append(msg.recipient)
                logger.error("[VECTOR][bulk] error [{}/{}] → {}: {}",
                             i + 1, len(messages), msg.recipient[:20], e)
                if self._fail_fast:
                    break

            # Rate limit: sleep between sends (skip after last message)
            if i < len(messages) - 1 and not dry_run:
                time.sleep(self._delay)

        result.elapsed_seconds = time.monotonic() - start
        logger.info("[VECTOR][bulk] done — {}/{} sent, {} failed, {:.1f}s",
                    len(result.sent), result.total, len(result.failed), result.elapsed_seconds)
        return result

    @staticmethod
    def rate_limit_for(channel_id: str) -> float:
        """Return messages-per-second limit for a channel type."""
        return _RATE_LIMITS.get(channel_id, _RATE_LIMITS["default"])


if __name__ == "__main__":
    # Smoke test with a mock channel
    from unittest.mock import MagicMock
    from vectorcode.src.channels._abc import ChannelStatus

    mock_ch = MagicMock(spec=BaseChannel)
    mock_ch.channel_id = "telegram"
    mock_ch.send.return_value = True

    sender = BulkSender(mock_ch)
    msgs = [BulkMessage(f"user_{i}", f"hello {i}") for i in range(5)]

    result = sender.send_bulk(msgs, dry_run=True)
    assert len(result.skipped) == 5

    result2 = sender.send_bulk(msgs[:2])
    assert len(result2.sent) == 2
    print(f"OK bulk_sender.py — sent={result2.sent}, rate={sender.rate_limit_for('telegram')} msg/s")
