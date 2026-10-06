# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""News/RSS connector — aggregate headlines from RSS and Atom feeds.

Uses stdlib xml.etree.ElementTree for parsing (no extra dependencies).
Config file lists feeds to follow. All HTTP calls are in module-level
functions for easy mocking in tests.
"""

from __future__ import annotations
from loguru import logger

import json
try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import httpx

from vectorcode.src.connectors._abc import BaseConnector, Document, SyncStatus
from vectorcode.src.vc_core.config import DEFAULT_CONFIG_DIR
from vectorcode.src.vc_core.registry import ConnectorRegistry

_DEFAULT_CONFIG_PATH = str(DEFAULT_CONFIG_DIR / "connectors" / "news_rss.json")

def _fetch_feed(url: str) -> str:
    """Download raw XML from a feed URL."""
    resp = httpx.get(url, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.text

def _parse_rss_items(xml_text: str, max_items: int = 5) -> List[Dict[str, str]]:
    """Parse RSS or Atom XML and return up to *max_items* entries."""
    root = ET.fromstring(xml_text)
    items: List[Dict[str, str]] = []

    # RSS 2.0: <rss><channel><item>
    for item_el in root.iter("item"):
        if len(items) >= max_items:
            break
        items.append(
            {
                "title": (item_el.findtext("title") or "").strip(),
                "description": (item_el.findtext("description") or "").strip()[:200],
                "link": (item_el.findtext("link") or "").strip(),
                "pubDate": (item_el.findtext("pubDate") or "").strip(),
            }
        )

    # Atom: <feed><entry>
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry_el in root.iter("{http://www.w3.org/2005/Atom}entry"):
            if len(items) >= max_items:
                break
            link_el = entry_el.find("atom:link", ns)
            link_href = link_el.get("href", "") if link_el is not None else ""
            summary = entry_el.findtext("{http://www.w3.org/2005/Atom}summary") or ""
            updated = entry_el.findtext("{http://www.w3.org/2005/Atom}updated") or ""
            items.append(
                {
                    "title": (
                        entry_el.findtext("{http://www.w3.org/2005/Atom}title") or ""
                    ).strip(),
                    "description": summary.strip()[:200],
                    "link": link_href.strip(),
                    "pubDate": updated.strip(),
                }
            )

    return items

def _parse_pub_date(date_str: str) -> Optional[datetime]:
    """Best-effort parse of an RSS pubDate or Atom updated timestamp."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except (ValueError, TypeError) as _sve:
        logger.debug("[VECTOR][connectors.news_rss] suppressed (ValueError, TypeError): {}", _sve)
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None

def _is_before(dt: datetime, cutoff: datetime) -> bool:
    """Compare two datetimes as real instants, never naive-vs-aware.

    parsedate_to_datetime() returns a timezone-aware datetime, while a
    checkpoint-derived since= (e.g. from SyncEngine) is also aware -- mixing
    an aware value with a naively-stripped one raises TypeError. Normalize
    both sides to aware UTC before comparing instead.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    return dt < cutoff

@ConnectorRegistry.register("news_rss")
class NewsRSSConnector(BaseConnector):
    """Aggregate headlines from configured RSS/Atom feeds."""

    connector_id = "news_rss"
    display_name = "News / RSS"
    auth_type = "local"

    def __init__(self, *, config_path: str = _DEFAULT_CONFIG_PATH) -> None:
        self._config_path = Path(config_path)
        self._status = SyncStatus()

    def _load_config(self) -> List[Dict[str, str]]:
        """Load feed list from disk."""
        data = json.loads(self._config_path.read_text(encoding="utf-8"))
        return data.get("feeds", [])

    def is_connected(self) -> bool:
        if not self._config_path.exists():
            return False
        try:
            feeds = self._load_config()
            return len(feeds) > 0
        except (json.JSONDecodeError, OSError):
            return False

    def disconnect(self) -> None:
        if self._config_path.exists():
            self._config_path.unlink()

    def sync(
        self, *, since: Optional[datetime] = None, cursor: Optional[str] = None
    ) -> Iterator[Document]:
        """Yield Documents for recent items across all configured feeds."""
        try:
            feeds = self._load_config()

            for feed in feeds:
                feed_name = feed.get("name", "Unknown Feed")
                feed_url = feed.get("url", "")
                if not feed_url:
                    continue

                try:
                    xml_text = _fetch_feed(feed_url)
                except httpx.HTTPError:
                    continue

                items = _parse_rss_items(xml_text)
                for item in items:
                    pub_dt = _parse_pub_date(item["pubDate"])

                    # Filter by since if the date is parseable
                    if since and pub_dt and _is_before(pub_dt, since):
                        continue

                    title = item["title"] or "Untitled"
                    doc_id = f"rss-{feed_name}-{title[:40]}"

                    yield Document(
                        doc_id=doc_id,
                        source="news_rss",
                        doc_type="article",
                        content=item["description"],
                        title=title,
                        timestamp=pub_dt or datetime.now(),
                        url=item["link"] or None,
                        metadata={"feed_name": feed_name},
                    )

            self._status.state = "idle"
            self._status.last_sync = datetime.now()
            self._status.error = None
        except Exception as exc:
            # self._status.state defaults to "idle" -- the same value a
            # successful sync ends on -- so without this, a failed sync
            # (malformed config JSON, an unexpected parse error) is
            # indistinguishable from "nothing synced yet" to any caller
            # polling sync_status().
            self._status.state = "error"
            self._status.error = str(exc)
            raise

    def sync_status(self) -> SyncStatus:
        return self._status
