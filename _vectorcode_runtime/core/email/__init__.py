"""VECTOR email core — AI security, schema, helpers, dates, search, attachments, sender."""
from core.email.schema import init_schema, get_connection, EMAIL_DB_PATH
from core.email.ai_security import is_prompt_injection, verify_draft
from core.email.helpers import (
    escape_html, text_to_html, strip_html_to_text,
    build_quoted_reply_block, validate_sender, SenderValidationError,
    generate_message_id, build_references_chain, build_threading_headers,
    format_email_date,
)
from core.email.dates import (
    format_list_date, format_detail_date, format_short_date, format_quoted_date,
)
from core.email.search import parse_search_query, ParsedSearch
from core.email.attachments import store_attachments, StoredAttachment, get_attachment_path
from core.email.sender import send_email, SendEmailParams
from core.email.ui_helpers import (
    format_bytes, html_to_plain_text, get_snippet_text,
    split_email_list, get_non_inline_attachments, get_attachment_url,
)

__all__ = [
    "init_schema", "get_connection", "EMAIL_DB_PATH",
    "is_prompt_injection", "verify_draft",
    "escape_html", "text_to_html", "strip_html_to_text",
    "build_quoted_reply_block", "validate_sender", "SenderValidationError",
    "generate_message_id", "build_references_chain", "build_threading_headers",
    "format_email_date",
    "format_list_date", "format_detail_date", "format_short_date", "format_quoted_date",
    "parse_search_query", "ParsedSearch",
    "store_attachments", "StoredAttachment", "get_attachment_path",
    "send_email", "SendEmailParams",
    "format_bytes", "html_to_plain_text", "get_snippet_text",
    "split_email_list", "get_non_inline_attachments", "get_attachment_url",
]
