import sys
import smtplib
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
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


def send_email(params: SendEmailParams) -> dict[str, str]:
    """Send an email via SMTP using config credentials.

    Mirrors the Cloudflare Email Service binding API surface.
    Falls back to logging if SMTP is not configured (development mode).
    """
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
        return {"message_id": message_id}

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
    except smtplib.SMTPException as e:
        logger.error(f"[VECTOR][email_sender] SMTP error: {e}")
        raise

    return {"message_id": message_id}


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
