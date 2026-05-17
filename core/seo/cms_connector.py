"""
VECTOR CMS Connector — detect and fetch content from any CMS.

Supports: WordPress (REST API), Strapi (GraphQL), Contentful (GraphQL),
Ghost (Content API). Auto-detects which CMS is configured via env vars.

Usage:
    connector = CMSConnector()
    cms_type = connector.detect()        # "wordpress" | "strapi" | "contentful" | "ghost" | None
    posts = connector.fetch_posts(limit=20)
    connector.update_seo_meta(post_id, title="New title", description="...")
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _detect_cms() -> Optional[str]:
    """Detect CMS type from environment variables."""
    if _env("WP_URL") and _env("WP_USER") and _env("WP_APP_PASSWORD"):
        return "wordpress"
    if _env("CONTENTFUL_SPACE_ID") and _env("CONTENTFUL_MANAGEMENT_TOKEN"):
        return "contentful"
    if _env("GHOST_URL") and _env("GHOST_CONTENT_API_KEY"):
        return "ghost"
    if _env("STRAPI_URL") and _env("STRAPI_TOKEN"):
        return "strapi"
    return None


# ── WordPress ─────────────────────────────────────────────────────────────────

def _wp_request(path: str, method: str = "GET", data: dict | None = None) -> Any:
    base = _env("WP_URL").rstrip("/")
    url = f"{base}/wp-json/wp/v2/{path}"
    user = _env("WP_USER")
    password = _env("WP_APP_PASSWORD")
    import base64
    creds = base64.b64encode(f"{user}:{password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _wp_fetch_posts(limit: int = 20) -> list[dict]:
    posts = _wp_request(f"posts?per_page={limit}&_fields=id,title,slug,link,date,yoast_head_json")
    return [
        {
            "id": str(p.get("id", "")),
            "title": p.get("title", {}).get("rendered", ""),
            "slug": p.get("slug", ""),
            "url":  p.get("link", ""),
            "date": p.get("date", ""),
        }
        for p in posts
    ]


def _wp_update_seo(post_id: str, title: str = "", description: str = "") -> bool:
    try:
        meta = {}
        if title:
            meta["yoast_title"] = title
            meta["_yoast_wpseo_title"] = title
        if description:
            meta["yoast_description"] = description
            meta["_yoast_wpseo_metadesc"] = description
        _wp_request(f"posts/{post_id}", method="POST", data={"meta": meta})
        return True
    except Exception as e:
        logger.warning("[VECTOR][cms] WP SEO update failed: {}", e)
        return False


# ── Ghost ─────────────────────────────────────────────────────────────────────

def _ghost_fetch_posts(limit: int = 20) -> list[dict]:
    base = _env("GHOST_URL").rstrip("/")
    key  = _env("GHOST_CONTENT_API_KEY")
    url  = f"{base}/ghost/api/content/posts/?key={key}&limit={limit}&fields=id,title,slug,url,published_at"
    req  = urllib.request.Request(url, headers={"User-Agent": "VECTOR/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return [
        {
            "id": p.get("id", ""),
            "title": p.get("title", ""),
            "slug": p.get("slug", ""),
            "url":  p.get("url", ""),
            "date": p.get("published_at", ""),
        }
        for p in data.get("posts", [])
    ]


# ── Contentful ────────────────────────────────────────────────────────────────

def _contentful_fetch_entries(limit: int = 20, content_type: str = "blogPost") -> list[dict]:
    space = _env("CONTENTFUL_SPACE_ID")
    token = _env("CONTENTFUL_MANAGEMENT_TOKEN")
    url   = (f"https://cdn.contentful.com/spaces/{space}/entries"
             f"?content_type={content_type}&limit={limit}")
    headers = {"Authorization": f"Bearer {token}"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    entries = []
    for item in data.get("items", []):
        fields = item.get("fields", {})
        entries.append({
            "id":    item.get("sys", {}).get("id", ""),
            "title": fields.get("title", ""),
            "slug":  fields.get("slug", ""),
            "url":   f"/{fields.get('slug', '')}",
        })
    return entries


# ── Strapi ────────────────────────────────────────────────────────────────────

def _strapi_fetch_entries(limit: int = 20) -> list[dict]:
    base  = _env("STRAPI_URL").rstrip("/")
    token = _env("STRAPI_TOKEN")
    url   = f"{base}/api/articles?pagination[limit]={limit}"
    headers = {"Authorization": f"Bearer {token}"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    entries = []
    for item in data.get("data", []):
        attrs = item.get("attributes", {})
        entries.append({
            "id":    str(item.get("id", "")),
            "title": attrs.get("title", ""),
            "slug":  attrs.get("slug", ""),
            "url":   f"/{attrs.get('slug', '')}",
        })
    return entries


# ── CMSConnector ──────────────────────────────────────────────────────────────

class CMSConnector:
    """
    VECTOR's unified CMS connector.
    Detects CMS from env vars and provides a consistent interface.
    """

    def __init__(self) -> None:
        self._cms = _detect_cms()
        if self._cms:
            logger.info("[VECTOR][cms] detected: {}", self._cms)
        else:
            logger.debug("[VECTOR][cms] no CMS configured — set WP_URL/GHOST_URL/etc.")

    def detect(self) -> Optional[str]:
        return self._cms

    def fetch_posts(self, limit: int = 20) -> list[dict]:
        """Fetch content from the detected CMS."""
        if self._cms == "wordpress":
            return _wp_fetch_posts(limit)
        elif self._cms == "ghost":
            return _ghost_fetch_posts(limit)
        elif self._cms == "contentful":
            return _contentful_fetch_entries(limit)
        elif self._cms == "strapi":
            return _strapi_fetch_entries(limit)
        logger.warning("[VECTOR][cms] no CMS configured — returning empty list")
        return []

    def update_seo_meta(
        self,
        post_id: str,
        title: str = "",
        description: str = "",
    ) -> bool:
        """Update SEO meta for a post (WordPress only for now)."""
        if self._cms == "wordpress":
            return _wp_update_seo(post_id, title=title, description=description)
        logger.warning("[VECTOR][cms] SEO meta update not supported for {}", self._cms)
        return False

    def is_configured(self) -> bool:
        return self._cms is not None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    connector = CMSConnector()
    print(f"OK cms_connector.py — detected: {connector.detect() or 'none'}")
    print("  Set WP_URL+WP_USER+WP_APP_PASSWORD for WordPress")
    print("  Set GHOST_URL+GHOST_CONTENT_API_KEY for Ghost")
