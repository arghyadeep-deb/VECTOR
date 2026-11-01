
__all__ = [
    "send_email",
    "SendEmailParams",
]

import smtplib
import base64
import hashlib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr
from typing import Any, Optional
from dataclasses import dataclass, field

from core.config import CONFIG
from loguru import logger


@dataclass
class SendEmailParams:
    to: str | list[str]
    from_addr: str | dict[str, str]
    subject: str
    html: Optional[str] = None
    text: Optional[str] = None
    cc: Optional[str | list[str]] = None
    bcc: Optional[str | list[str]] = None
    reply_to: Optional[str | dict[str, str]] = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)


def _addr_str(addr: str | dict[str, str]) -> str:
    if isinstance(addr, str):
        return addr
    return formataddr((addr.get("name", ""), addr["email"]))


def _list_str(val: str | list[str] | None) -> str:
    if val is None:
        return ""
    return ", ".join(val) if isinstance(val, list) else val


def _email_dedup_hash(params: SendEmailParams) -> str:
    """Hash (to, subject, body) for dedup — prevents duplicate sends on retry."""
    to_key = _list_str(params.to)
    body_key = params.html or params.text or ""
    raw = f"{to_key}|{params.subject}|{body_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _check_email_dedup(dedup_hash: str, window_hours: int = 24) -> bool:
    """Return True if this email was already sent within the window."""
    try:
        from core.memory.episodic import get_db_connection, get_temp_cursor
        conn = get_db_connection()
        # Ensure table exists (idempotent)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS email_dedup "
            "(dedup_hash TEXT PRIMARY KEY, sent_at TEXT)"
        )
        conn.commit()
        row = conn.execute(
            "SELECT sent_at FROM email_dedup WHERE dedup_hash = ?", (dedup_hash,)
        ).fetchone()
        if not row:
            return False
        from datetime import datetime, timedelta
        sent_at = datetime.fromisoformat(row[0])
        return (datetime.utcnow() - sent_at) < timedelta(hours=window_hours)
    except Exception as e:
        logger.warning(f"[VECTOR][email_sender] dedup check failed: {e}")
        return False  # fail open — better to send twice than never


def _record_email_dedup(dedup_hash: str) -> None:
    """Record that this email was sent."""
    try:
        from core.memory.episodic import get_temp_cursor
        from datetime import datetime
        with get_temp_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO email_dedup (dedup_hash, sent_at) VALUES (?, ?)",
                (dedup_hash, datetime.utcnow().isoformat()),
            )
    except Exception as e:
        logger.warning(f"[VECTOR][email_sender] dedup record failed: {e}")


def send_email(params: SendEmailParams) -> dict[str, str]:
    """Send an email via SMTP using config credentials.

    Mirrors the Cloudflare Email Service binding API surface.
    Falls back to logging if SMTP is not configured (development mode).

    Dedup: hashes (to, subject, body) and skips if the same email was sent
    within the last 24 hours — prevents duplicates when retries fire.
    """
    # Dedup check — skip if this exact email was recently sent
    dedup_hash = _email_dedup_hash(params)
    if _check_email_dedup(dedup_hash):
        logger.info(
            f"[VECTOR][email_sender] Duplicate suppressed (hash={dedup_hash[:8]}…) "
            f"to={_list_str(params.to)} subject={params.subject!r}"
        )
        return {"message_id": "", "status": "duplicate_suppressed"}

    smtp_host = CONFIG.get("SMTP_HOST", "")
    smtp_port = int(CONFIG.get("SMTP_PORT", 587))
    smtp_user = CONFIG.get("SMTP_USER", "")
    smtp_pass = CONFIG.get("SMTP_PASS", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = params.subject
    msg["From"] = _addr_str(params.from_addr)
    msg["To"] = _list_str(params.to)
    if params.cc:
        msg["Cc"] = _list_str(params.cc)
    if params.reply_to:
        msg["Reply-To"] = _addr_str(params.reply_to)
    for key, value in params.headers.items():
        msg[key] = value

    if params.text:
        msg.attach(MIMEText(params.text, "plain", "utf-8"))
    if params.html:
        msg.attach(MIMEText(params.html, "html", "utf-8"))

    for att in params.attachments:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(base64.b64decode(att["content"]))
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            att.get("disposition", "attachment"),
            filename=att.get("filename", "file"),
        )
        if att.get("contentId"):
            part.add_header("Content-ID", f'<{att["contentId"]}>')
        msg.attach(part)

    import uuid
    message_id = str(uuid.uuid4())

    if not smtp_host:
        logger.warning("[VECTOR][email_sender] SMTP not configured — email queued locally only")
        _record_email_dedup(dedup_hash)
        # Same success-shaped {"message_id": ...} as a genuinely delivered
        # email below (phantom success) -- callers that only guard a raised
        # exception (as districts/communications/reply_forward.py did) saw
        # this as an ordinary successful send. "status" distinguishes the
        # two without breaking the documented dev-mode graceful-degradation
        # behavior (not configured -> log + queue, never crash).
        return {"message_id": message_id, "status": "queued_locally"}

    all_recipients = []
    to_list = params.to if isinstance(params.to, list) else [params.to]
    all_recipients.extend(to_list)
    if params.cc:
        cc_list = params.cc if isinstance(params.cc, list) else [params.cc]
        all_recipients.extend(cc_list)
    if params.bcc:
        bcc_list = params.bcc if isinstance(params.bcc, list) else [params.bcc]
        all_recipients.extend(bcc_list)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.sendmail(_addr_str(params.from_addr), all_recipients, msg.as_string())
        logger.info(f"[VECTOR][email_sender] Sent to {all_recipients} via {smtp_host}")
        _record_email_dedup(dedup_hash)
    except smtplib.SMTPException as e:
        logger.error(f"[VECTOR][email_sender] SMTP error: {e}")
        raise

    return {"message_id": message_id, "status": "sent"}


if __name__ == "__main__":
    # Without SMTP configured, should return message_id without crashing
    params = SendEmailParams(
        to="test@example.com",
        from_addr={"email": "me@example.com", "name": "VECTOR"},
        subject="Test",
        text="Hello from VECTOR",
    )
    result = send_email(params)
    assert "message_id" in result
    print("✅ sender.py OK")
