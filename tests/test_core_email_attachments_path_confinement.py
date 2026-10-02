"""Regression: core/email/attachments.py's get_attachment_path() had zero
path confinement on any of its 3 caller-supplied components (email_id,
attachment_id, filename) -- unlike store_attachments(), which strips
directory components and unsafe characters before ever writing a file.
A traversal-containing filename/email_id/attachment_id could resolve
outside _ATTACH_ROOT. No real caller exists today (confirmed via repo-wide
grep), but the function is exported from core/email/__init__.py and
plausibly backs a future attachment-download route -- fixed anyway, same
bar as other dormant-code narrow fixes this cycle.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.email.attachments import get_attachment_path, store_attachments, _ATTACH_ROOT


def test_get_attachment_path_rejects_traversal_in_filename():
    with pytest.raises(ValueError, match="escaped storage root"):
        get_attachment_path("email-1", "att-1", "../../../../etc/passwd")


def test_get_attachment_path_rejects_traversal_in_email_id():
    with pytest.raises(ValueError, match="escaped storage root"):
        get_attachment_path("../../etc", "att-1", "passwd")


def test_get_attachment_path_rejects_traversal_in_attachment_id():
    with pytest.raises(ValueError, match="escaped storage root"):
        get_attachment_path("email-1", "../../etc", "passwd")


def test_get_attachment_path_legitimate_round_trip():
    sample = [{
        "content": __import__("base64").b64encode(b"hello").decode(),
        "filename": "note.txt",
        "type": "text/plain",
        "disposition": "attachment",
    }]
    stored = store_attachments("email-confine-test", sample)
    path = get_attachment_path("email-confine-test", stored[0].id, stored[0].filename)
    assert path.is_relative_to(_ATTACH_ROOT.resolve())
    assert path.read_bytes() == b"hello"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
