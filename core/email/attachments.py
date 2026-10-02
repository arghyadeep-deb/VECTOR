
__all__ = [
    "get_attachment_path",
    "store_attachments",
    "StoredAttachment",
]

import uuid
import re
import base64
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.config import CONFIG
from core.memory.db_utils import configured_db_path

# Local attachment storage root (mirrors R2 bucket structure locally)
_DATA_DIR = CONFIG.get("VECTOR_DATA_DIR") or CONFIG.get("data_dir")
_ATTACH_ROOT = (Path(str(_DATA_DIR)) if _DATA_DIR else configured_db_path().parent) / "attachments"

_UNSAFE_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


@dataclass
class StoredAttachment:
    id: str
    email_id: str
    filename: str
    mimetype: str
    size: int
    content_id: Optional[str]
    disposition: str


def store_attachments(
    email_id: str,
    attachments: list[dict] | None,
    db_conn: sqlite3.Connection | None = None,
) -> list[StoredAttachment]:
    """Store base64-encoded attachments to local filesystem and return metadata.

    Args:
        email_id: Parent email UUID.
        attachments: List of dicts with keys: content (base64), filename, type,
                     disposition, and optionally contentId.
        db_conn: Optional open SQLite connection for recording metadata.
    """
    if not attachments:
        return []

    _ATTACH_ROOT.mkdir(parents=True, exist_ok=True)
    results: list[StoredAttachment] = []

    for att in attachments:
        attachment_id = str(uuid.uuid4())
        raw_name = att.get("filename") or "untitled"
        # Take only the final path component to prevent traversal (e.g. ../../evil.sh → evil.sh)
        raw_name = Path(raw_name).name or "untitled"
        safe_name = _UNSAFE_CHARS.sub("_", raw_name)
        dest_dir = _ATTACH_ROOT / email_id / attachment_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / safe_name

        raw_bytes = base64.b64decode(att["content"])
        dest_path.write_bytes(raw_bytes)

        stored = StoredAttachment(
            id=attachment_id,
            email_id=email_id,
            filename=safe_name,
            mimetype=att.get("type", "application/octet-stream"),
            size=len(raw_bytes),
            content_id=att.get("contentId") or att.get("content_id"),
            disposition=att.get("disposition", "attachment"),
        )
        results.append(stored)

        if db_conn:
            db_conn.execute(
                """INSERT OR REPLACE INTO attachments
                   (id, email_id, filename, mimetype, size, content_id, disposition)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    stored.id,
                    stored.email_id,
                    stored.filename,
                    stored.mimetype,
                    stored.size,
                    stored.content_id,
                    stored.disposition,
                ),
            )
            db_conn.commit()

    return results


def get_attachment_path(email_id: str, attachment_id: str, filename: str) -> Path:
    """Resolve a stored attachment's path, confined to _ATTACH_ROOT.

    Unlike store_attachments() (which strips directory components and unsafe
    characters before ever writing a file), this function had no such check
    on any of its three caller-supplied components -- a filename/email_id/
    attachment_id containing ".." could resolve outside _ATTACH_ROOT. No real
    caller exists today, but this must stay safe for whatever reads it next
    (e.g. an attachment-download HTTP route).
    """
    root = _ATTACH_ROOT.resolve()
    candidate = (root / email_id / attachment_id / filename).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"attachment path escaped storage root: {filename!r}")
    return candidate


if __name__ == "__main__":
    import tempfile, os

    sample = [
        {
            "content": base64.b64encode(b"hello world").decode(),
            "filename": "test.txt",
            "type": "text/plain",
            "disposition": "attachment",
        }
    ]
    stored = store_attachments("email-001", sample)
    assert len(stored) == 1
    assert stored[0].size == len(b"hello world")
    path = get_attachment_path("email-001", stored[0].id, stored[0].filename)
    assert path.read_bytes() == b"hello world"
    print("✅ attachments.py OK")
