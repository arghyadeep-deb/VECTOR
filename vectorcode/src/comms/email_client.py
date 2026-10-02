"""Email client — IMAP receive + SMTP send with graceful degradation."""

import sys
from pathlib import Path


from loguru import logger

import imaplib
import smtplib
import email as email_lib
import os
import hashlib
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders as email_encoders
from email.header import decode_header
from email.utils import parseaddr, getaddresses
from typing import Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class EmailMessage:
    uid: str
    subject: str
    sender: str
    recipients: list[str]
    body: str
    html_body: str = ""
    date: str = ""
    attachments: list[dict] = field(default_factory=list)
    thread_id: str = ""

# ---------------------------------------------------------------------------
# Helper -- decode RFC2047-encoded header values
# ---------------------------------------------------------------------------

def _decode_header_value(raw: str | bytes | None) -> str:
    """Decode an RFC2047-encoded header value to a plain Python string."""
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    parts = decode_header(raw)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)

# ---------------------------------------------------------------------------
# EmailClient
# ---------------------------------------------------------------------------

class EmailClient:
    def __init__(
        self,
        imap_host: str = "",
        imap_port: int = 993,
        imap_user: str = "",
        imap_pass: str = "",
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_pass: str = "",
        *,
        use_ssl: bool = True,
    ) -> None:
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.imap_user = imap_user
        self.imap_pass = imap_pass
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self.use_ssl = use_ssl
        self._imap: Optional[imaplib.IMAP4] = None

    # ------------------------------------------------------------------
    # IMAP connection management
    # ------------------------------------------------------------------

    def connect_imap(self) -> bool:
        """Open IMAP connection. Returns False if credentials are missing."""
        if not self.imap_host or not self.imap_user or not self.imap_pass:
            logger.warning("[VECTOR][email] IMAP credentials missing — skipping connect")
            return False
        try:
            if self.use_ssl:
                self._imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            else:
                self._imap = imaplib.IMAP4(self.imap_host, self.imap_port)
            self._imap.login(self.imap_user, self.imap_pass)
            logger.info(f"[VECTOR][email] IMAP connected -> {self.imap_host}")
            return True
        except Exception as exc:
            logger.error(f"[VECTOR][email] IMAP connect failed: {exc}")
            self._imap = None
            return False

    def disconnect_imap(self) -> None:
        """Close the IMAP connection if open."""
        if self._imap is None:
            return
        try:
            self._imap.logout()
        except Exception as _sve:
            logger.debug("[VECTOR][comms.email_client] IMAP logout failed: {}", _sve)
        finally:
            self._imap = None
            logger.debug("[VECTOR][email] IMAP disconnected")

    # ------------------------------------------------------------------
    # Fetch unread messages
    # ------------------------------------------------------------------

    def fetch_unread(self, folder: str = "INBOX", limit: int = 20) -> list[EmailMessage]:
        """
        Fetch unread messages from *folder*.  Marks them SEEN after parsing.
        Returns messages sorted by date descending.  Returns [] if not connected.
        """
        if self._imap is None:
            logger.debug("[VECTOR][email] fetch_unread called but not connected")
            return []
        try:
            status, _ = self._imap.select(folder)
            if status != "OK":
                logger.warning(f"[VECTOR][email] SELECT {folder} failed: {status}")
                return []

            status, data = self._imap.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                return []

            uids: list[bytes] = data[0].split()
            # newest first, capped at limit
            uids = uids[-limit:][::-1]

            messages: list[EmailMessage] = []
            for uid_bytes in uids:
                try:
                    uid = uid_bytes.decode()
                    status, raw = self._imap.fetch(uid_bytes, "(RFC822)")
                    if status != "OK" or not raw or raw[0] is None:
                        continue
                    raw_bytes: bytes = raw[0][1]  # type: ignore[index]
                    msg = self._parse_message(raw_bytes)
                    msg.uid = uid
                    messages.append(msg)
                    # mark seen
                    self._imap.store(uid_bytes, "+FLAGS", "\\Seen")
                except Exception as exc:
                    logger.warning(f"[VECTOR][email] Failed to parse message {uid_bytes}: {exc}")

            return messages
        except Exception as exc:
            logger.error(f"[VECTOR][email] fetch_unread error: {exc}")
            return []

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, folder: str = "INBOX", limit: int = 20) -> list[EmailMessage]:
        """
        Run an IMAP SEARCH with *query* (e.g. 'FROM "boss@co.com"').
        Returns up to *limit* messages sorted by date descending.
        """
        if self._imap is None:
            logger.debug("[VECTOR][email] search called but not connected")
            return []
        try:
            self._imap.select(folder)
            status, data = self._imap.search(None, query)
            if status != "OK" or not data or not data[0]:
                return []

            uids = data[0].split()
            uids = uids[-limit:][::-1]

            messages: list[EmailMessage] = []
            for uid_bytes in uids:
                try:
                    uid = uid_bytes.decode()
                    status, raw = self._imap.fetch(uid_bytes, "(RFC822)")
                    if status != "OK" or not raw or raw[0] is None:
                        continue
                    msg = self._parse_message(raw[0][1])  # type: ignore[index]
                    msg.uid = uid
                    messages.append(msg)
                except Exception as exc:
                    logger.warning(f"[VECTOR][email] search parse error {uid_bytes}: {exc}")

            return messages
        except Exception as exc:
            logger.error(f"[VECTOR][email] search error: {exc}")
            return []

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def send(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        *,
        html_body: str = "",
        reply_to_uid: str = "",
        attachments: list[str] | None = None,
    ) -> dict:
        """
        Send an email via SMTP.

        Returns {"success": True, "message_id": ...}  on success.
        Returns {"success": False, "error": ...}       on failure or missing creds.
        """
        if not self.smtp_host or not self.smtp_user or not self.smtp_pass:
            logger.warning("[VECTOR][email] SMTP credentials missing — cannot send")
            return {"success": False, "error": "SMTP credentials not configured"}

        recipients: list[str] = [to] if isinstance(to, str) else list(to)

        try:
            # Build MIME message
            mime = MIMEMultipart("alternative") if not attachments else MIMEMultipart("mixed")
            mime["From"] = self.smtp_user
            mime["To"] = ", ".join(recipients)
            mime["Subject"] = subject

            # Generate a deterministic Message-ID
            unique = f"{self.smtp_user}{subject}{''.join(recipients)}"
            msg_id = f"<{hashlib.md5(unique.encode()).hexdigest()}@vectorcode>"
            mime["Message-ID"] = msg_id

            # In-reply-to header for threading
            if reply_to_uid:
                mime["In-Reply-To"] = reply_to_uid
                mime["References"] = reply_to_uid

            # Body parts
            mime.attach(MIMEText(body, "plain", "utf-8"))
            if html_body:
                mime.attach(MIMEText(html_body, "html", "utf-8"))

            # Attachments
            if attachments:
                for filepath in attachments:
                    path = Path(filepath)
                    if not path.exists():
                        logger.warning(f"[VECTOR][email] Attachment not found: {filepath}")
                        continue
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(path.read_bytes())
                    email_encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        "attachment",
                        filename=path.name,
                    )
                    mime.attach(part)

            # Connect and send
            if self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                    server.login(self.smtp_user, self.smtp_pass)
                    server.sendmail(self.smtp_user, recipients, mime.as_bytes())
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.smtp_user, self.smtp_pass)
                    server.sendmail(self.smtp_user, recipients, mime.as_bytes())

            logger.info(f"[VECTOR][email] Sent to {recipients} | subject='{subject}'")
            return {"success": True, "message_id": msg_id}

        except Exception as exc:
            logger.error(f"[VECTOR][email] send failed: {exc}")
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Flag helpers
    # ------------------------------------------------------------------

    def mark_read(self, uid: str, folder: str = "INBOX") -> None:
        """Mark a message as read (\\Seen)."""
        self._set_flag(uid, folder, "+FLAGS", "\\Seen")

    def mark_unread(self, uid: str, folder: str = "INBOX") -> None:
        """Remove \\Seen flag."""
        self._set_flag(uid, folder, "-FLAGS", "\\Seen")

    def move_to_folder(self, uid: str, destination: str) -> None:
        """Copy *uid* to *destination* then delete from INBOX."""
        if self._imap is None:
            return
        try:
            self._imap.copy(uid.encode(), destination)
            self._imap.store(uid.encode(), "+FLAGS", "\\Deleted")
            self._imap.expunge()
            logger.debug(f"[VECTOR][email] Moved {uid} -> {destination}")
        except Exception as exc:
            logger.error(f"[VECTOR][email] move_to_folder error: {exc}")

    def _set_flag(self, uid: str, folder: str, action: str, flag: str) -> None:
        if self._imap is None:
            return
        try:
            self._imap.select(folder)
            self._imap.store(uid.encode(), action, flag)
        except Exception as exc:
            logger.error(f"[VECTOR][email] _set_flag({action} {flag}) error: {exc}")

    # ------------------------------------------------------------------
    # MIME parser
    # ------------------------------------------------------------------

    def _parse_message(self, raw_bytes: bytes) -> EmailMessage:
        """Parse raw MIME bytes into an EmailMessage."""
        parsed = email_lib.message_from_bytes(raw_bytes)

        subject = _decode_header_value(parsed.get("Subject", ""))
        sender = _decode_header_value(parsed.get("From", ""))
        date_str = parsed.get("Date", "")
        thread_id = parsed.get("Message-ID", "")

        # Recipients: To + CC
        to_raw = parsed.get_all("To", [])
        cc_raw = parsed.get_all("Cc", [])
        recipients = [
            addr for _, addr in getaddresses(to_raw + cc_raw) if addr
        ]

        body = ""
        html_body = ""
        attachments: list[dict] = []

        if parsed.is_multipart():
            for part in parsed.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in disposition:
                    filename = _decode_header_value(part.get_filename("attachment"))
                    payload = part.get_payload(decode=True) or b""
                    attachments.append({
                        "filename": filename,
                        "content_type": content_type,
                        "size": len(payload),
                    })
                elif content_type == "text/plain" and not body:
                    raw_payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset("utf-8") or "utf-8"
                    body = raw_payload.decode(charset, errors="replace")
                elif content_type == "text/html" and not html_body:
                    raw_payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset("utf-8") or "utf-8"
                    html_body = raw_payload.decode(charset, errors="replace")
        else:
            raw_payload = parsed.get_payload(decode=True) or b""
            charset = parsed.get_content_charset("utf-8") or "utf-8"
            if parsed.get_content_type() == "text/html":
                html_body = raw_payload.decode(charset, errors="replace")
            else:
                body = raw_payload.decode(charset, errors="replace")

        return EmailMessage(
            uid="",  # caller fills this in
            subject=subject,
            sender=sender,
            recipients=recipients,
            body=body,
            html_body=html_body,
            date=date_str,
            attachments=attachments,
            thread_id=thread_id,
        )

# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_client_singleton: Optional[EmailClient] = None

def get_email_client() -> EmailClient:
    """
    Return a module-level singleton EmailClient.
    Reads credentials from environment variables:
        VECTOR_EMAIL_IMAP_HOST / _PORT / _USER / _PASS
        VECTOR_EMAIL_SMTP_HOST / _PORT / _USER / _PASS
    """
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = EmailClient(
            imap_host=os.environ.get("VECTOR_EMAIL_IMAP_HOST", ""),
            imap_port=int(os.environ.get("VECTOR_EMAIL_IMAP_PORT", "993")),
            imap_user=os.environ.get("VECTOR_EMAIL_IMAP_USER", ""),
            imap_pass=os.environ.get("VECTOR_EMAIL_IMAP_PASS", ""),
            smtp_host=os.environ.get("VECTOR_EMAIL_SMTP_HOST", ""),
            smtp_port=int(os.environ.get("VECTOR_EMAIL_SMTP_PORT", "587")),
            smtp_user=os.environ.get("VECTOR_EMAIL_SMTP_USER", ""),
            smtp_pass=os.environ.get("VECTOR_EMAIL_SMTP_PASS", ""),
        )
    return _client_singleton

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("[VECTOR][email] Running smoke test…")

    # Test 1: connect_imap with no credentials returns False without crashing
    client = EmailClient()
    result = client.connect_imap()
    assert result is False, f"Expected False, got {result}"
    logger.info("[VECTOR][email] connect_imap(no creds) -> False ✅")

    # Test 2: send with no credentials returns {"success": False, ...}
    send_result = client.send("test@example.com", "Test", "Hello")
    assert send_result["success"] is False, f"Expected success=False, got {send_result}"
    assert "error" in send_result, "Expected 'error' key in result"
    logger.info(f"[VECTOR][email] send(no creds) -> {send_result} ✅")

    # Test 3: fetch_unread without connection returns []
    messages = client.fetch_unread()
    assert messages == [], f"Expected [], got {messages}"
    logger.info("[VECTOR][email] fetch_unread(not connected) -> [] ✅")

    # Test 4: search without connection returns []
    results = client.search('FROM "anyone@example.com"')
    assert results == [], f"Expected [], got {results}"
    logger.info("[VECTOR][email] search(not connected) -> [] ✅")

    # Test 5: singleton factory
    singleton = get_email_client()
    assert isinstance(singleton, EmailClient)
    assert get_email_client() is singleton, "Singleton not returning same instance"
    logger.info("[VECTOR][email] get_email_client() singleton ✅")

    # Test 6: _parse_message with a minimal raw MIME
    raw = (
        b"From: sender@example.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Subject: Hello =?utf-8?b?V29ybGQ=?=\r\n"
        b"Date: Wed, 14 May 2026 10:00:00 +0000\r\n"
        b"Message-ID: <test123@example.com>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"This is the body.\r\n"
    )
    parsed = client._parse_message(raw)
    assert parsed.subject == "Hello World", f"Subject decode failed: {parsed.subject!r}"
    assert parsed.body.strip() == "This is the body."
    assert parsed.sender == "sender@example.com"
    logger.info("[VECTOR][email] _parse_message MIME ✅")

    logger.info("[VECTOR][email] All smoke tests passed")
    sys.stdout.buffer.write(b"[OK] email_client.py OK\n")
