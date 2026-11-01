import re
import html as html_module
from typing import Optional

from core.email.dates import format_list_date, format_detail_date, format_short_date, format_quoted_date
from core.email.helpers import escape_html


def format_bytes(num_bytes: int, decimals: int = 1) -> str:
    """Human-readable file size: '1.2 MB'."""
    if num_bytes == 0:
        return "0 B"
    k = 1024
    sizes = ["B", "KB", "MB", "GB"]
    i = 0
    val = float(num_bytes)
    while val >= k and i < len(sizes) - 1:
        val /= k
        i += 1
    return f"{val:.{max(0, decimals)}f} {sizes[i]}"


def split_email_list(value: Optional[str]) -> list[str]:
    """Split a comma-separated email field into individual addresses."""
    if not value:
        return []
    return [e.strip() for e in value.split(",") if e.strip()]


def to_email_list_value(addresses: list[str]) -> str | list[str] | None:
    if not addresses:
        return None
    return addresses[0] if len(addresses) == 1 else addresses


def _decode_html_entities(text: str) -> str:
    return html_module.unescape(text)


def html_to_plain_text(html: str) -> str:
    """Convert HTML to plain text (server-side safe, no DOM required)."""
    result = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    result = re.sub(r"<br\s*/?>", "\n", result, flags=re.IGNORECASE)
    result = re.sub(r"</p>", "\n\n", result, flags=re.IGNORECASE)
    result = re.sub(r"<p[^>]*>", "", result, flags=re.IGNORECASE)
    result = re.sub(r"<div[^>]*>", "", result, flags=re.IGNORECASE)
    result = re.sub(r"</div>", "\n", result, flags=re.IGNORECASE)
    result = re.sub(r"<[^>]+>", "", result)
    return result.strip()


def strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", html)).strip()


def get_snippet_text(snippet: Optional[str], max_length: int = 100) -> str:
    if not snippet:
        return ""
    # Was: a chained `.__class__(...)` call on a discarded first re.sub()
    # result -- str.__class__ is just str, so that was a disguised,
    # redundant str(...) no-op wrapping an IDENTICAL second computation of
    # the same style-stripping regex against the same input. Same output,
    # without computing it twice through an obfuscated type-cast idiom.
    no_style = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", snippet, flags=re.IGNORECASE)
    cleaned = _decode_html_entities(re.sub(r"<[^>]*>", " ", no_style))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    return f"{cleaned[:max_length]}..." if len(cleaned) > max_length else cleaned


def build_quoted_reply_block(date_str: Optional[str], sender: str, body: str) -> str:
    if not body:
        return ""
    formatted_date = format_quoted_date(date_str)
    escaped_sender = escape_html(sender)
    body_quoted = escape_html(strip_html(body)).replace("\n", "<br>")
    return (
        f'<br><blockquote style="border-left: 2px solid #ccc; margin: 0; padding-left: 1em; color: #666;">'
        f"On {formatted_date}, {escaped_sender} wrote:<br><br>{body_quoted}</blockquote>"
    )


def get_attachment_url(mailbox_id: str, email_id: str, attachment_id: str) -> str:
    return f"/api/v1/mailboxes/{mailbox_id}/emails/{email_id}/attachments/{attachment_id}"


def get_non_inline_attachments(attachments: list[dict]) -> list[dict]:
    return [a for a in attachments if a.get("disposition") != "inline"]


# Re-export date helpers so callers can import from one place
__all__ = [
    "format_list_date",
    "format_detail_date",
    "format_short_date",
    "format_quoted_date",
    "format_bytes",
    "split_email_list",
    "to_email_list_value",
    "html_to_plain_text",
    "strip_html",
    "get_snippet_text",
    "build_quoted_reply_block",
    "escape_html",
    "get_attachment_url",
    "get_non_inline_attachments",
]


if __name__ == "__main__":
    assert format_bytes(0) == "0 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1536) == "1.5 KB"
    assert format_bytes(1048576) == "1.0 MB"
    assert get_snippet_text("<p>Hello world</p>") == "Hello world"
    assert get_snippet_text(None) == ""
    assert strip_html("<b>Bold</b>") == "Bold"
    snippet = build_quoted_reply_block("2026-05-17T12:00:00Z", "alice@example.com", "<p>Hi</p>")
    assert "blockquote" in snippet
    print("✅ ui_helpers.py OK")
