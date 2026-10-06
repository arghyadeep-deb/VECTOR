"""Regression for vectorcode/src/connectors/news_rss.py: two bugs.

1. sync() had no try/except at all -- a failed sync (malformed config,
   unexpected parse error) left self._status at its default "idle" state
   with no error ever recorded, indistinguishable from "nothing synced yet".

2. The since-filter did ``pub_dt.replace(tzinfo=None) < since`` -- stripping
   tzinfo from the parsed publish date but NOT from `since`. parsedate_to_datetime()
   always returns a timezone-aware datetime, and SyncEngine's checkpoint-derived
   since= is also timezone-aware (stored via datetime.now(tz=timezone.utc)),
   so comparing a naive value against an aware one raised TypeError on every
   real incremental sync -- not a wrong-result bug, an outright crash.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from vectorcode.src.connectors.news_rss import NewsRSSConnector

_RSS_XML = """<?xml version="1.0"?>
<rss><channel>
<item>
<title>Headline</title>
<description>Body text</description>
<link>https://example.test/a</link>
<pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
</item>
</channel></rss>
"""


def test_sync_with_malformed_config_reports_error_status(tmp_path):
    config_path = tmp_path / "news_rss.json"
    config_path.write_text("{not valid json", encoding="utf-8")
    connector = NewsRSSConnector(config_path=str(config_path))

    assert connector.sync_status().state == "idle"

    with pytest.raises(json.JSONDecodeError):
        list(connector.sync())

    status = connector.sync_status()
    assert status.state == "error"
    assert status.error is not None


def test_sync_since_filter_does_not_crash_on_aware_since(tmp_path):
    config_path = tmp_path / "news_rss.json"
    config_path.write_text(
        json.dumps({"feeds": [{"name": "Test Feed", "url": "https://example.test/rss"}]}),
        encoding="utf-8",
    )
    connector = NewsRSSConnector(config_path=str(config_path))

    # since is timezone-aware, matching how SyncEngine derives it from a
    # stored checkpoint (datetime.fromisoformat() of an isoformat() string
    # produced by datetime.now(tz=timezone.utc)).
    since = datetime(2023, 1, 1, tzinfo=timezone.utc)

    with patch(
        "vectorcode.src.connectors.news_rss._fetch_feed", return_value=_RSS_XML
    ):
        docs = list(connector.sync(since=since))

    assert len(docs) == 1
    assert connector.sync_status().state == "idle"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
