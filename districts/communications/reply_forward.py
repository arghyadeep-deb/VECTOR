import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.email.helpers import (
    validate_sender,
    SenderValidationError,
    generate_message_id,
    build_references_chain,
    build_threading_headers,
)
from core.email.attachments import store_attachments
from core.email.sender import SendEmailParams, send_email
from core.email.schema import get_connection
from loguru import logger

_FOLDER_SENT = "sent"


def _resolve_original(conn, email_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM emails WHERE id = ?", (email_id,)
    ).fetchone()
    if not row:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM emails LIMIT 0").description or []]
    # Re-fetch with column names
    row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    cur = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def handle_reply_email(
    mailbox_id: str,
    original_id: str,
    to: str | list[str],
    from_addr: str | dict[str, str],
    subject: str,
    html: Optional[str] = None,
    text: Optional[str] = None,
    cc: Optional[str | list[str]] = None,
    bcc: Optional[str | list[str]] = None,
    attachments: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """Send a reply to an existing email and record it in the sent folder."""
    conn = get_connection()

    cur = conn.execute("SELECT * FROM emails WHERE id = ?", (original_id,))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    if not row:
        return {"error": "Original email not found", "status": 404}

    original = dict(zip(cols, row))

    # If original is a draft with in_reply_to, resolve the real original
    if original.get("folder_id") == "draft" and original.get("in_reply_to"):
        real_cur = conn.execute("SELECT * FROM emails WHERE id = ?", (original["in_reply_to"],))
        real_cols = [d[0] for d in real_cur.description]
        real_row = real_cur.fetchone()
        if real_row:
            original = dict(zip(real_cols, real_row))

    try:
        validated = validate_sender(to, from_addr, mailbox_id)
    except SenderValidationError as e:
        return {"error": str(e), "status": 400}

    chain = build_references_chain(original)
    original_msg_id = chain["original_msg_id"]
    references = chain["references"]
    thread_id = chain["thread_id"]

    ids = generate_message_id(validated["from_domain"])
    message_id = ids["message_id"]
    outgoing_message_id = ids["outgoing_message_id"]

    stored_attachments = store_attachments(message_id, attachments or [], conn)

    to_str = ", ".join(to) if isinstance(to, list) else to
    cc_str = (", ".join(cc) if isinstance(cc, list) else cc) if cc else None
    bcc_str = (", ".join(bcc) if isinstance(bcc, list) else bcc) if bcc else None
    now = _now_iso()
    from_str = from_addr if isinstance(from_addr, str) else f"{from_addr.get('name','')} <{from_addr['email']}>"

    raw_headers = [
        {"key": "from", "value": from_str},
        {"key": "to", "value": to_str},
        {"key": "subject", "value": subject},
        {"key": "date", "value": now},
        {"key": "message-id", "value": f"<{outgoing_message_id}>"},
    ]
    if cc_str:
        raw_headers.append({"key": "cc", "value": cc_str})
    if bcc_str:
        raw_headers.append({"key": "bcc", "value": bcc_str})
    if original_msg_id:
        raw_headers.append({"key": "in-reply-to", "value": f"<{original_msg_id}>"})
    if references:
        raw_headers.append({"key": "references", "value": " ".join(f"<{r}>" for r in references)})

    conn.execute(
        """INSERT INTO emails
           (id, folder_id, subject, sender, recipient, cc, bcc, date, body,
            in_reply_to, email_references, thread_id, message_id, raw_headers, read)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (
            message_id,
            _FOLDER_SENT,
            subject,
            validated["from_email"],
            to_str,
            cc_str,
            bcc_str,
            now,
            html or text or "",
            original_msg_id,
            json.dumps(references),
            thread_id,
            outgoing_message_id,
            json.dumps(raw_headers),
        ),
    )
    conn.commit()

    for att in stored_attachments:
        conn.execute(
            """INSERT OR IGNORE INTO attachments
               (id, email_id, filename, mimetype, size, content_id, disposition)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (att.id, att.email_id, att.filename, att.mimetype, att.size, att.content_id, att.disposition),
        )
    conn.commit()

    try:
        send_email(SendEmailParams(
            to=to,
            from_addr=from_addr,
            subject=subject,
            html=html,
            text=text,
            cc=cc,
            bcc=bcc,
            attachments=attachments or [],
            headers=build_threading_headers(original_msg_id, references),
        ))
    except Exception as e:
        logger.error("[VECTOR][reply_forward] Reply delivery failed: {}", e)
        # Delivery failed: do not leave a phantom row in Sent or report success.
        conn.execute("UPDATE emails SET folder_id='draft' WHERE id = ?", (message_id,))
        conn.commit()
        return {"error": f"reply delivery failed: {e}", "status": 502, "id": message_id}

    return {"id": message_id, "status": "sent"}


def handle_forward_email(
    mailbox_id: str,
    original_id: str,
    to: str | list[str],
    from_addr: str | dict[str, str],
    subject: str,
    html: Optional[str] = None,
    text: Optional[str] = None,
    cc: Optional[str | list[str]] = None,
    bcc: Optional[str | list[str]] = None,
    attachments: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """Forward an email to new recipients."""
    conn = get_connection()

    cur = conn.execute("SELECT * FROM emails WHERE id = ?", (original_id,))
    if not cur.fetchone():
        return {"error": "Original email not found", "status": 404}

    try:
        validated = validate_sender(to, from_addr, mailbox_id)
    except SenderValidationError as e:
        return {"error": str(e), "status": 400}

    ids = generate_message_id(validated["from_domain"])
    message_id = ids["message_id"]
    outgoing_message_id = ids["outgoing_message_id"]

    stored_attachments = store_attachments(message_id, attachments or [], conn)

    to_str = ", ".join(to) if isinstance(to, list) else to
    cc_str = (", ".join(cc) if isinstance(cc, list) else cc) if cc else None
    bcc_str = (", ".join(bcc) if isinstance(bcc, list) else bcc) if bcc else None
    now = _now_iso()
    from_str = from_addr if isinstance(from_addr, str) else f"{from_addr.get('name','')} <{from_addr['email']}>"

    raw_headers = [
        {"key": "from", "value": from_str},
        {"key": "to", "value": to_str},
        {"key": "subject", "value": subject},
        {"key": "date", "value": now},
        {"key": "message-id", "value": f"<{outgoing_message_id}>"},
    ]
    if cc_str:
        raw_headers.append({"key": "cc", "value": cc_str})
    if bcc_str:
        raw_headers.append({"key": "bcc", "value": bcc_str})

    conn.execute(
        """INSERT INTO emails
           (id, folder_id, subject, sender, recipient, cc, bcc, date, body,
            in_reply_to, email_references, thread_id, message_id, raw_headers, read)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, 1)""",
        (
            message_id,
            _FOLDER_SENT,
            subject,
            validated["from_email"],
            to_str,
            cc_str,
            bcc_str,
            now,
            html or text or "",
            message_id,
            outgoing_message_id,
            json.dumps(raw_headers),
        ),
    )
    conn.commit()

    for att in stored_attachments:
        conn.execute(
            """INSERT OR IGNORE INTO attachments
               (id, email_id, filename, mimetype, size, content_id, disposition)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (att.id, att.email_id, att.filename, att.mimetype, att.size, att.content_id, att.disposition),
        )
    conn.commit()

    try:
        send_email(SendEmailParams(
            to=to,
            from_addr=from_addr,
            subject=subject,
            html=html,
            text=text,
            cc=cc,
            bcc=bcc,
            attachments=attachments or [],
        ))
    except Exception as e:
        logger.error("[VECTOR][reply_forward] Forward delivery failed: {}", e)
        # Delivery failed: do not leave a phantom row in Sent or report success.
        conn.execute("UPDATE emails SET folder_id='draft' WHERE id = ?", (message_id,))
        conn.commit()
        return {"error": f"forward delivery failed: {e}", "status": 502, "id": message_id}

    return {"id": message_id, "status": "sent"}


if __name__ == "__main__":
    from core.email.schema import init_schema
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        init_schema(db_path)
        print("✅ reply_forward.py OK (schema initialized)")
    finally:
        db_path.unlink(missing_ok=True)
