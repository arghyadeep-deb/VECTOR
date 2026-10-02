
__all__ = [
    "fetch_new_emails",
    "FetchedEmail",
]

import imaplib
import email as email_lib
import email.message  # noqa: F401 -- binds email.message so email_lib.message.Message
                       # resolves standalone; relying on some OTHER import to have
                       # already pulled this in made this module crash with
                       # AttributeError when run first/alone (confirmed via git stash).
from email.header import decode_header
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.config import CONFIG
from loguru import logger


@dataclass
class FetchedEmail:
    message_id: str
    sender: str
    subject: str
    body: str
    thread_id: Optional[str]
    raw_headers: str
    date: datetime


def _decode_subject(raw: str) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    return "".join(
        part.decode(enc or "utf-8", errors="replace") if isinstance(part, bytes) else part
        for part, enc in parts
    )


def _extract_text_body(msg: email_lib.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode("utf-8", errors="replace") if payload else ""


def _parse_date(msg: email_lib.message.Message) -> datetime:
    date_str = msg.get("Date", "")
    if not date_str:
        return datetime.now()
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return datetime.now()


def fetch_new_emails(since: Optional[datetime] = None, limit: int = 25) -> list[FetchedEmail]:
    """Fetch unseen messages from the configured IMAP inbox.

    Mirrors `sender.py::send_email`'s graceful-degradation style: returns an
    empty list (and logs a warning) if IMAP isn't configured or the login
    fails, so callers can poll unconditionally without crashing.
    """
    imap_host = CONFIG.get("IMAP_HOST", "")
    imap_user = CONFIG.get("IMAP_USER", "") or CONFIG.get("EMAIL_ADDRESS", "")
    imap_pass = CONFIG.get("IMAP_PASS", "")

    if not imap_host or not imap_user or not imap_pass:
        logger.warning("[VECTOR][email_receiver] IMAP not configured — skipping inbox poll")
        return []

    try:
        imap = imaplib.IMAP4_SSL(imap_host)
    except Exception as e:
        logger.error(f"[VECTOR][email_receiver] IMAP connection failed: {e}")
        return []

    fetched: list[FetchedEmail] = []
    try:
        imap.login(imap_user, imap_pass)
        imap.select("INBOX", readonly=True)

        if since:
            _, data = imap.search(None, f'SINCE {since.strftime("%d-%b-%Y")} UNSEEN')
        else:
            _, data = imap.search(None, "UNSEEN")

        msg_ids = data[0].split()[-limit:]
        for mid in msg_ids:
            try:
                _, msg_data = imap.fetch(mid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
            except Exception as e:
                logger.debug(f"[VECTOR][email_receiver] failed to parse message {mid}: {e}")
                continue

            references = msg.get("References", "")
            # `or` binds tighter than the ternary, so the obvious-looking
            # "In-Reply-To or (last reference if References else None)"
            # actually parsed as "(In-Reply-To or last-reference) if
            # References else None" -- discarding a genuinely present
            # In-Reply-To whenever References was simply absent (a common
            # case: not every client sets References on a first reply).
            thread_id = msg.get("In-Reply-To") or (references.split()[-1] if references else None)

            fetched.append(FetchedEmail(
                message_id=msg.get("Message-ID", mid.decode()),
                sender=msg.get("From", ""),
                subject=_decode_subject(msg.get("Subject", "")),
                body=_extract_text_body(msg),
                thread_id=thread_id,
                raw_headers=str(msg.items()),
                date=_parse_date(msg),
            ))

        imap.logout()
    except imaplib.IMAP4.error as e:
        logger.error(f"[VECTOR][email_receiver] IMAP login/fetch error: {e}")
        return []
    except Exception as e:
        logger.error(f"[VECTOR][email_receiver] IMAP poll failed: {e}")
        return []

    if fetched:
        logger.info(f"[VECTOR][email_receiver] fetched {len(fetched)} new message(s) via {imap_host}")
    return fetched


if __name__ == "__main__":
    # Without IMAP configured, should return [] without crashing
    result = fetch_new_emails()
    assert isinstance(result, list)
    print("✅ receiver.py OK")
