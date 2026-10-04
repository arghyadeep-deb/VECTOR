"""Regression for 12 vectorcode/src/{connectors,vc_tools} files that already
correctly imported loguru (`from loguru import logger`, no stdlib shadow) but
still had a leftover %-style placeholder in a suppressed-exception log call
-- most following the repo-wide "[VECTOR][module] suppressed <ExcType>: %s"
convention. loguru's {}-style formatter does not substitute %s/%d/%r, so
every one of these silently printed the literal "%s" instead of the
exception text, making the suppressed exception genuinely invisible.

These were missed by this audit's first survey of this directory scope,
which searched for the "stdlib logging.getLogger shadow" pattern -- these
files never had that shadow, they always had a correct loguru import, just
with a stale %-style call left over from before the loguru migration. Found
via a multi-line-aware scan for %-style tokens inside any logger.* call's
full parenthesized argument list (a same-line-only grep missed several of
these, since the message and the substituted variable are on different
source lines).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_REPO_ROOT = Path(__file__).parent.parent

_FILES = [
    "vectorcode/src/connectors/apple_contacts.py",
    "vectorcode/src/connectors/attachment_store.py",
    "vectorcode/src/connectors/gcalendar.py",
    "vectorcode/src/connectors/gcontacts.py",
    "vectorcode/src/connectors/gdrive.py",
    "vectorcode/src/connectors/github_notifications.py",
    "vectorcode/src/connectors/news_rss.py",
    "vectorcode/src/connectors/oauth.py",
    "vectorcode/src/connectors/store.py",
    "vectorcode/src/connectors/sync_engine.py",
    "vectorcode/src/vc_tools/digest_collect.py",
    "vectorcode/src/vc_tools/storage/sqlite.py",
]

_LOGGER_CALL_START = re.compile(r"logger\.\w+\(")
_PCT_TOKEN = re.compile(r"%[sdrf]|%\.[0-9]*[sf]")


def _logger_calls_containing_percent(src: str) -> list[str]:
    hits = []
    for m in _LOGGER_CALL_START.finditer(src):
        start = m.end() - 1
        depth = 0
        i = start
        while i < len(src):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        call_text = src[start : i + 1]
        if _PCT_TOKEN.search(call_text):
            hits.append(call_text)
    return hits


def test_no_percent_style_logger_calls_remain():
    for rel in _FILES:
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        hits = _logger_calls_containing_percent(src)
        assert hits == [], f"{rel} still has %-style logger call(s): {hits}"


def test_all_files_already_import_loguru_correctly():
    # Sanity check on the premise: these files never had the stdlib-shadow
    # bug, they always had a correct loguru import -- confirming that so a
    # future reader doesn't assume this test overlaps with the shadow-fix test.
    for rel in _FILES:
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "from loguru import logger" in src, f"{rel} unexpectedly lacks a loguru import"
        assert not re.search(r"^import logging\b", src, re.MULTILINE), (
            f"{rel} unexpectedly has a stdlib logging import"
        )


def test_loguru_actually_substitutes_where_percent_style_would_not():
    """Live proof of the underlying mechanism, not just a source grep."""
    import io
    from loguru import logger as live_logger

    buf = io.StringIO()
    live_logger.remove()
    sink_id = live_logger.add(buf, format="{message}")
    try:
        live_logger.debug("suppressed Exception: {}", "boom")
        live_logger.debug("suppressed Exception: %s", "boom")
    finally:
        live_logger.remove(sink_id)

    output = buf.getvalue()
    assert "suppressed Exception: boom" in output
    assert "suppressed Exception: %s" in output  # the %-style call never substitutes


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
