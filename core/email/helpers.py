
__all__ = [
    "build_quoted_reply_block",
    "build_references_chain",
    "build_threading_headers",
    "escape_html",
    "format_email_date",
    "generate_message_id",
    "SenderValidationError",
    "strip_html_to_text",
    "text_to_html",
    "validate_sender",
]

import uuid
import json
import re
from typing import Any

from loguru import logger
from core.config import CONFIG
from core.email.dates import format_quoted_date


# â”€â”€ Sender Validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class SenderValidationError(ValueError):
    pass


def validate_sender(
    to: str | list[str],
    from_addr: str | dict[str, str],
    mailbox_id: str,
) -> dict[str, str]:
    to_str = (", ".join(to) if isinstance(to, list) else to).lower()
    from_email = (from_addr if isinstance(from_addr, str) else from_addr["email"]).lower()

    if from_email != mailbox_id.lower():
        raise SenderValidationError("From address must match the mailbox email address")

    parts = from_email.split("@")
    if len(parts) != 2 or not parts[1]:
        raise SenderValidationError("Invalid sender email address")

    return {"to_str": to_str, "from_email": from_email, "from_domain": parts[1]}


# â”€â”€ Message ID â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def generate_message_id(from_domain: str) -> dict[str, str]:
    message_id = str(uuid.uuid4())
    outgoing_message_id = f"{message_id}@{from_domain}"
    return {"message_id": message_id, "outgoing_message_id": outgoing_message_id}


# â”€â”€ Threading â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def build_references_chain(original: dict[str, Any]) -> dict[str, Any]:
    original_msg_id = original.get("message_id") or original.get("id", "")
    existing_refs: list[str] = []
    raw = original.get("email_references")
    if raw:
        try:
            existing_refs = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("[VECTOR][email_helpers] malformed email_references JSON, ignoring: {}", e)
    references = [r for r in [*existing_refs, original_msg_id] if r]
    thread_id = original.get("thread_id") or original.get("id", "")
    return {"original_msg_id": original_msg_id, "references": references, "thread_id": thread_id}


def build_threading_headers(original_msg_id: str, references: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {"In-Reply-To": f"<{original_msg_id}>"}
    if references:
        headers["References"] = " ".join(f"<{r}>" for r in references)
    return headers


# â”€â”€ HTML Utilities â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def escape_html(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
    )


def text_to_html(text: str) -> str:
    if not text:
        return ""
    escaped = escape_html(text).replace("\n", "<br>")
    return f'<div style="white-space:pre-wrap">{escaped}</div>'


def strip_html_to_text(html: str) -> str:
    if not html:
        return ""
    result = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    result = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", result, flags=re.IGNORECASE)
    result = re.sub(r"<[^>]+>", " ", result)
    return re.sub(r"\s+", " ", result).strip()


def build_quoted_reply_block(original: dict[str, Any]) -> str:
    body = original.get("body")
    if not body:
        return ""
    sender = escape_html(original.get("sender") or "unknown")
    date = escape_html(format_quoted_date(original.get("date") or ""))
    plain = strip_html_to_text(body)
    body_quoted = escape_html(plain).replace("\n", "<br>")
    return (
        f'<br><blockquote style="border-left: 2px solid #ccc; margin: 0; padding-left: 1em; color: #666;">'
        f"On {date}, {sender} wrote:<br><br>{body_quoted}</blockquote>"
    )


# â”€â”€ Convenience aliases â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

format_email_date = format_quoted_date


if __name__ == "__main__":
    mid = generate_message_id("example.com")
    assert "@" in mid["outgoing_message_id"]
    assert escape_html("<script>") == "&lt;script&gt;"
    assert strip_html_to_text("<p>Hello <b>world</b></p>") == "Hello world"
    print("✅ helpers.py OK")
