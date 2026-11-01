"""
VECTOR Webhook HMAC Signer — inspired by OpenWA's signed webhook delivery.

Signs outbound webhook payloads with HMAC-SHA256 so receivers can verify
authenticity without knowing the secret. Pattern used by GitHub, Stripe, Shopify.

Usage:
    signer = WebhookSigner()
    headers = signer.signed_headers(body_bytes, secret="my_secret")
    # → {"X-Signature-256": "sha256=abc...", "X-Delivery-Id": "...", "X-Timestamp": "..."}

    ok = signer.verify(body_bytes, headers["X-Signature-256"], secret="my_secret")
"""
from __future__ import annotations

__all__ = ["WebhookSigner", "WebhookDelivery", "get_signer"]

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

_SIGNATURE_HEADER = "X-Signature-256"
_DELIVERY_HEADER = "X-Delivery-Id"
_TIMESTAMP_HEADER = "X-Timestamp"


class WebhookSigner:
    """HMAC-SHA256 signer and verifier for webhook payloads."""

    def sign(self, body: bytes, secret: str) -> str:
        """Return 'sha256=<hex>' signature for body using secret."""
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return f"sha256={sig}"

    def verify(self, body: bytes, signature: str, secret: str) -> bool:
        """
        Constant-time verification of an incoming X-Signature-256 header.
        signature should be the raw header value, e.g. 'sha256=abc123...'.
        """
        expected = self.sign(body, secret)
        try:
            return hmac.compare_digest(expected.encode(), signature.encode())
        except (TypeError, ValueError):
            return False

    def signed_headers(
        self,
        body: bytes,
        secret: str,
        *,
        delivery_id: str = "",
        content_type: str = "application/json",
    ) -> dict[str, str]:
        """
        Return HTTP headers dict for a signed outbound webhook delivery.

        Headers produced:
          X-Signature-256: sha256=<hex>   — HMAC-SHA256 of body
          X-Delivery-Id:   <uuid4>        — unique per-delivery ID for idempotency
          X-Timestamp:     <unix_seconds> — delivery timestamp
          Content-Type:    application/json
        """
        return {
            _SIGNATURE_HEADER: self.sign(body, secret),
            _DELIVERY_HEADER: delivery_id or str(uuid.uuid4()),
            _TIMESTAMP_HEADER: str(int(time.time())),
            "Content-Type": content_type,
        }


@dataclass
class DeliveryResult:
    url: str
    success: bool
    status_code: int = 0
    attempt: int = 1
    error: str = ""


class WebhookDelivery:
    """
    Delivers HMAC-signed JSON payloads to webhook URLs with retry logic.

    Inspired by OpenWA's webhook event dispatch module.
    Retries on 5xx or network failure with exponential backoff.
    """

    def __init__(
        self,
        signer: WebhookSigner | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
    ) -> None:
        self._signer = signer or WebhookSigner()
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff = backoff_base

    def deliver(
        self,
        url: str,
        payload: dict[str, Any],
        secret: str = "",
        *,
        extra_headers: dict[str, str] | None = None,
        delivery_id: str = "",
    ) -> DeliveryResult:
        """
        POST a JSON payload to url, HMAC-signed if secret is provided.
        Retries on network failure or 5xx responses.
        """
        if not _HTTPX_AVAILABLE:
            logger.warning("[VECTOR][webhook] httpx not available — cannot deliver webhooks")
            return DeliveryResult(url=url, success=False, error="httpx not installed")

        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        did = delivery_id or str(uuid.uuid4())

        if secret:
            headers = self._signer.signed_headers(body, secret, delivery_id=did)
        else:
            headers = {"Content-Type": "application/json", _DELIVERY_HEADER: did}

        if extra_headers:
            headers.update(extra_headers)

        last_error = ""
        for attempt in range(1, self._max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.post(url, content=body, headers=headers)
                if resp.status_code < 500:
                    success = resp.status_code < 300
                    if not success:
                        logger.warning("[VECTOR][webhook] {} → {} ({})", url[:60], resp.status_code, did)
                    return DeliveryResult(url=url, success=success,
                                         status_code=resp.status_code, attempt=attempt)
                last_error = f"HTTP {resp.status_code}"
                logger.warning("[VECTOR][webhook] attempt {}/{} failed: {}", attempt, self._max_retries, last_error)
            except Exception as e:
                last_error = str(e)
                logger.warning("[VECTOR][webhook] attempt {}/{} error: {}", attempt, self._max_retries, e)

            if attempt < self._max_retries:
                time.sleep(self._backoff * (2 ** (attempt - 1)))

        logger.error("[VECTOR][webhook] all {} attempts failed for {}", self._max_retries, url[:60])
        return DeliveryResult(url=url, success=False, error=last_error,
                              attempt=self._max_retries)

    def deliver_to_many(
        self,
        urls: list[str],
        payload: dict[str, Any],
        secret: str = "",
    ) -> list[DeliveryResult]:
        """Fan out a single payload to multiple webhook URLs."""
        return [self.deliver(url, payload, secret) for url in urls]


_global_signer: WebhookSigner | None = None


def get_signer() -> WebhookSigner:
    global _global_signer
    if _global_signer is None:
        _global_signer = WebhookSigner()
    return _global_signer


if __name__ == "__main__":
    s = WebhookSigner()
    body = b'{"event":"test","data":"hello"}'
    sig = s.sign(body, "my_secret")
    assert sig.startswith("sha256=")
    assert s.verify(body, sig, "my_secret")
    assert not s.verify(body, sig, "wrong_secret")
    assert not s.verify(b"tampered", sig, "my_secret")

    headers = s.signed_headers(body, "my_secret")
    assert _SIGNATURE_HEADER in headers
    assert _DELIVERY_HEADER in headers
    assert _TIMESTAMP_HEADER in headers
    print("OK core/engine/webhook/hmac_signer.py — signing + verification verified")
