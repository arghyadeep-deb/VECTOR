"""Regression for vectorcode/src/connectors/dropbox.py's DropboxConnector.sync():

the text-file download branch caught ANY exception from
_dropbox_api_download() (including a revoked/expired OAuth token, not just
"this file isn't actually text") and silently substituted placeholder
content with zero logging. A persistent auth failure partway through a
sync would therefore look like a completely successful sync that just
happened to produce "[File: name]" placeholders for every subsequent text
file -- the same "phantom success" shape already fixed in
connectors/slack_connector.py this audit cycle, just via silent exception
swallowing instead of an unchecked response field.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.connectors.dropbox import DropboxConnector


def _list_folder_response(entries, has_more=False, cursor=None):
    return {"entries": entries, "has_more": has_more, "cursor": cursor}


def test_download_failure_still_falls_back_to_placeholder(tmp_path):
    creds_path = tmp_path / "dropbox.json"
    creds_path.write_text('{"token": "fake-token"}', encoding="utf-8")

    connector = DropboxConnector(credentials_path=str(creds_path))

    entry = {
        ".tag": "file",
        "name": "notes.md",
        "path_lower": "/notes.md",
        "server_modified": "2026-01-01T00:00:00Z",
        "size": 42,
    }

    with patch(
        "vectorcode.src.connectors.dropbox._dropbox_api_list_folder",
        return_value=_list_folder_response([entry]),
    ), patch(
        "vectorcode.src.connectors.dropbox._dropbox_api_download",
        side_effect=RuntimeError("401 Unauthorized: token revoked"),
    ):
        docs = list(connector.sync())

    # The sync itself doesn't need to abort (unchanged behavior) -- it's
    # the missing visibility into *why* that was the bug.
    assert len(docs) == 1
    assert docs[0].content == "[File: notes.md]"


def test_download_failure_logs_via_loguru(tmp_path):
    """Same scenario, asserted directly against loguru's sink instead of
    stdlib caplog (loguru doesn't propagate to logging.Handler by default).
    """
    from loguru import logger

    creds_path = tmp_path / "dropbox.json"
    creds_path.write_text('{"token": "fake-token"}', encoding="utf-8")
    connector = DropboxConnector(credentials_path=str(creds_path))

    entry = {
        ".tag": "file",
        "name": "notes.md",
        "path_lower": "/notes.md",
        "server_modified": "2026-01-01T00:00:00Z",
        "size": 42,
    }

    captured = []
    sink_id = logger.add(lambda msg: captured.append(msg), level="WARNING")
    try:
        with patch(
            "vectorcode.src.connectors.dropbox._dropbox_api_list_folder",
            return_value=_list_folder_response([entry]),
        ), patch(
            "vectorcode.src.connectors.dropbox._dropbox_api_download",
            side_effect=RuntimeError("401 Unauthorized: token revoked"),
        ):
            list(connector.sync())
    finally:
        logger.remove(sink_id)

    assert any("token revoked" in str(m) for m in captured), (
        "download failure was not logged -- it silently became a placeholder"
    )


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
