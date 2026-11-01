"""Disabled-by-default WhatsApp provider boundary for VECTOR comms."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from enum import Enum

__all__ = ["WhatsAppMode", "WhatsAppProviderConfig", "WhatsAppProvider"]


class WhatsAppMode(str, Enum):
    OFFICIAL_CLOUD = "official_cloud"
    EVOLUTION_EXTERNAL = "evolution_external"


@dataclass(frozen=True)
class WhatsAppProviderConfig:
    enabled: bool = False
    mode: WhatsAppMode = WhatsAppMode.OFFICIAL_CLOUD
    endpoint: str = ""
    token: str = ""
    webhook_secret: str = ""


class WhatsAppProvider:
    def __init__(self, config: WhatsAppProviderConfig | None = None):
        self.config = config or WhatsAppProviderConfig()

    def available(self) -> bool:
        return bool(self.config.enabled and self.config.endpoint and self.config.token)

    def normalize_inbound(self, payload: dict) -> dict:
        message = payload.get("message") or payload.get("text") or payload.get("body") or ""
        sender = payload.get("from") or payload.get("sender") or payload.get("phone") or "unknown"
        return {
            "channel": "whatsapp",
            "sender": str(sender),
            "text": str(message),
            "raw_type": payload.get("type", "message"),
            "authenticated": False,
        }

    def sign_webhook(self, body: bytes) -> str:
        if not self.config.webhook_secret:
            return ""
        return hmac.new(self.config.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    def send_text(self, to: str, text: str) -> dict:
        if not self.available():
            return {"status": "unavailable", "reason": "WhatsApp provider disabled or not configured"}
        if not to or not text:
            return {"status": "error", "error": "to and text are required"}
        return {
            "status": "queued_for_permission",
            "channel": "whatsapp",
            "mode": self.config.mode.value,
            "to": to,
            "text_preview": text[:160],
        }
