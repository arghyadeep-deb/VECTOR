"""Email-bridge ingress handler: cloud inbox -> VECTOR brain.

The `vector-email` Cloudflare Worker, on receiving a mail, enqueues a signed
`email_received` event into the brain command queue. `autonomous_loop`'s
`command_poll_loop` drains it and routes it here. This handler:

  1. is OFF by default (only runs when ``VECTOR_EMAIL_BRIDGE=1``),
  2. verifies an HMAC over the canonical payload (fail-closed),
  3. prompt-injection scans the attacker-controlled fields (quarantine on hit),
  4. writes the event into episodic memory so it enters VECTOR's mind,
  5. attaches a lightweight rule-based priority (NO LLM call in this hot path —
     deep triage is left to the governor / async, deliberately).

See ``plans/cloud-inbox-brain-bridge.md`` (Phase 1).
"""
from __future__ import annotations

import os
import json
from loguru import logger


# Fields covered by the HMAC signature, in a fixed order, so the Worker and this
# handler compute the exact same canonical bytes regardless of dict ordering or
# any re-serialization by the command queue in between.
_SIGNED_FIELDS = ("message_id", "from", "subject", "snippet", "mailbox")

_PRIORITY_KEYWORDS = (
    "urgent", "asap", "immediately", "invoice", "payment", "overdue",
    "deadline", "interview", "offer", "security", "verify your", "suspended",
)


def email_bridge_enabled() -> bool:
    """Bridge is opt-in. Default OFF = entire feature is a no-op."""
    return os.getenv("VECTOR_EMAIL_BRIDGE", "").lower() in {"1", "true", "yes"}


def canonical_body(params: dict) -> bytes:
    """The exact bytes the HMAC is computed over (sorted, compact, fixed subset)."""
    subset = {k: ("" if params.get(k) is None else str(params.get(k))) for k in _SIGNED_FIELDS}
    return json.dumps(subset, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verify_signature(params: dict, signature: str) -> bool:
    secret = os.environ.get("EMAIL_BRIDGE_SECRET", "")
    if not secret or not signature:
        return False
    try:
        from core.engine.webhook.hmac_signer import WebhookSigner
        return WebhookSigner().verify(canonical_body(params), signature, secret)
    except Exception as e:  # signer import/use failure -> reject (fail-closed)
        logger.warning("[VECTOR][email_bridge] signer unavailable, rejecting: {}", e)
        return False


def _is_clean(text: str) -> bool:
    """True if the text passes the prompt-injection scan (or scanner absent)."""
    if not text:
        return True
    try:
        from core.security.prompt_injection import scan_text
        return bool(scan_text(text, "email_bridge").clean)
    except Exception as e:
        logger.warning("[VECTOR][email_bridge] injection scan failed (allowing): {}", e)
        return True


def _priority(subject: str, snippet: str) -> str:
    blob = f"{subject}\n{snippet}".lower()
    return "high" if any(kw in blob for kw in _PRIORITY_KEYWORDS) else "normal"


def _store(msg_id, sender, subject, snippet, mailbox, *, quarantined: bool, priority: str) -> None:
    try:
        from core.memory.episodic import EpisodicMemory
        tags = ["email", "inbox", "cloud_inbox"]
        if mailbox:
            tags.append(f"mailbox:{mailbox}")
        if quarantined:
            tags.append("quarantined")
        EpisodicMemory().store(
            event_type="email_received",
            content=f"{sender}: {subject}".strip(": ").strip(),
            tags=tags,
            context={
                "message_id": msg_id, "from": sender, "subject": subject,
                "snippet": snippet, "mailbox": mailbox,
                "priority": priority, "quarantined": quarantined,
            },
            source="cloud_inbox",
        )
    except Exception as e:
        logger.error("[VECTOR][email_bridge] episodic store failed for {}: {}", msg_id, e)


async def handle_email_received(params: dict, *, signature: str = "") -> dict:
    """Ingest one inbound-email event. Returns a small status dict.

    Statuses: ``disabled`` (flag off) · ``rejected`` (bad HMAC) ·
    ``quarantined`` (injection found) · ``ingested`` (stored + classified).
    Never raises — a malformed event must not take down the command loop.
    """
    if not email_bridge_enabled():
        return {"status": "disabled"}

    params = params or {}
    if not _verify_signature(params, signature):
        logger.critical("[VECTOR][email_bridge] bad/missing HMAC — REJECTED (fail-closed)")
        return {"status": "rejected", "reason": "signature"}

    msg_id = str(params.get("message_id") or params.get("id") or "")
    sender = str(params.get("from") or "")
    subject = str(params.get("subject") or "")
    snippet = str(params.get("snippet") or "")
    mailbox = str(params.get("mailbox") or "")
    priority = _priority(subject, snippet)

    # The inbox is attacker-controlled: scan before anything downstream trusts it.
    if not (_is_clean(subject) and _is_clean(snippet)):
        logger.critical("[VECTOR][email_bridge] injection in email {} — quarantined", msg_id)
        _store(msg_id, sender, subject, snippet, mailbox, quarantined=True, priority=priority)
        return {"status": "quarantined", "message_id": msg_id}

    _store(msg_id, sender, subject, snippet, mailbox, quarantined=False, priority=priority)
    logger.info("[VECTOR][email_bridge] ingested email {} (priority={})", msg_id, priority)
    return {"status": "ingested", "message_id": msg_id, "priority": priority}
