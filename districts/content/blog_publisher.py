"""
VECTOR Blog Platform Publisher — inspired by Postiz's multi-platform posting adapters.

Publishes Markdown/HTML content to technical blog platforms:
  - Dev.to (Forem) — REST API, API key
  - Hashnode — GraphQL API, personal access token
  - Medium — REST API, integration token

All three platforms are relevant for Arghyadeep's technical writing
(CSE projects, VECTOR build notes, AI research summaries).

Usage:
    pub = BlogPublisher()
    result = pub.publish_devto("My Title", "# Hello\nContent here", tags=["python", "ai"])
    result = pub.publish_hashnode("My Title", "# Hello", tags=["python"])
    result = pub.publish_medium("My Title", "<h1>Hello</h1>", content_format="html")
    results = pub.publish_all("Title", "# Content", tags=["ai"])
"""

from __future__ import annotations

__all__ = ["BlogPublisher", "PublishResult"]

import hashlib
from dataclasses import dataclass
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG


def _blog_dedup_hash(platform: str, title: str) -> str:
    """Hash (platform, title) for dedup — prevents publishing the same post twice."""
    raw = f"{platform}|{title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _check_blog_dedup(dedup_hash: str, window_hours: int = 24) -> bool:
    """Return True if this post was already published within the window."""
    try:
        from core.memory.episodic import get_db_connection
        conn = get_db_connection()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS blog_dedup "
            "(dedup_hash TEXT PRIMARY KEY, published_at TEXT)"
        )
        conn.commit()
        row = conn.execute(
            "SELECT published_at FROM blog_dedup WHERE dedup_hash = ?", (dedup_hash,)
        ).fetchone()
        if not row:
            return False
        from datetime import datetime, timedelta
        published_at = datetime.fromisoformat(row[0])
        return (datetime.utcnow() - published_at) < timedelta(hours=window_hours)
    except Exception as e:
        logger.warning(f"[VECTOR][blog] dedup check failed: {e}")
        return False  # fail open


def _record_blog_dedup(dedup_hash: str) -> None:
    """Record that this post was published."""
    try:
        from core.memory.episodic import get_temp_cursor
        from datetime import datetime
        with get_temp_cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO blog_dedup (dedup_hash, published_at) VALUES (?, ?)",
                (dedup_hash, datetime.utcnow().isoformat()),
            )
    except Exception as e:
        logger.warning(f"[VECTOR][blog] dedup record failed: {e}")

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

_DEVTO_API = "https://dev.to/api"
_HASHNODE_API = "https://gql.hashnode.com"
_MEDIUM_API = "https://api.medium.com/v1"

@dataclass
class PublishResult:
    platform: str
    success: bool
    url: str = ""
    post_id: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "success": self.success,
            "url": self.url,
            "post_id": self.post_id,
            "error": self.error,
        }

class BlogPublisher:
    """
    Publishes technical blog posts to Dev.to, Hashnode, and Medium.
    All methods degrade gracefully when API keys are absent.
    """

    def __init__(self) -> None:
        cfg = CONFIG.get("blog", {})
        self._devto_key = cfg.get("devto_api_key", "") or CONFIG.get("api_keys", {}).get("devto_api_key", "")
        self._hashnode_token = cfg.get("hashnode_token", "") or CONFIG.get("api_keys", {}).get("hashnode_token", "")
        self._hashnode_pub_id = cfg.get("hashnode_publication_id", "") or CONFIG.get("api_keys", {}).get("hashnode_publication_id", "")
        self._medium_token = cfg.get("medium_token", "") or CONFIG.get("api_keys", {}).get("medium_token", "")

    def _check_httpx(self, platform: str) -> PublishResult | None:
        if not _HTTPX_AVAILABLE:
            return PublishResult(platform=platform, success=False,
                                 error="httpx not installed (pip install httpx)")
        return None

    # ── Dev.to ─────────────────────────────────────────────────────────────────

    def publish_devto(
        self,
        title: str,
        content_markdown: str,
        *,
        tags: list[str] | None = None,
        published: bool = True,
        canonical_url: str = "",
        series: str = "",
        cover_image_url: str = "",
    ) -> PublishResult:
        """
        Publish an article to Dev.to (Forem).

        Args:
            title:              Article title.
            content_markdown:   Markdown body.
            tags:               Up to 4 tags (e.g. ["python", "ai", "tutorial"]).
            published:          False = draft, True = publish immediately.
            canonical_url:      Optional canonical URL for SEO.
            series:             Optional series name.
            cover_image_url:    Optional cover image URL.
        """
        err = self._check_httpx("devto")
        if err:
            return err
        if not self._devto_key:
            return PublishResult(platform="devto", success=False,
                                 error="DEVTO_API_KEY not configured")
        # Dedup: skip if this title was already published to devto recently
        dedup_hash = _blog_dedup_hash("devto", title)
        if _check_blog_dedup(dedup_hash):
            logger.info("[VECTOR][blog] Dev.to duplicate suppressed: {!r}", title)
            return PublishResult(platform="devto", success=True,
                                 error="duplicate_suppressed")
        try:
            article: dict[str, Any] = {
                "title": title,
                "body_markdown": content_markdown,
                "published": published,
                "tags": (tags or [])[:4],
            }
            if canonical_url:
                article["canonical_url"] = canonical_url
            if series:
                article["series"] = series
            if cover_image_url:
                article["main_image"] = cover_image_url

            resp = httpx.post(
                f"{_DEVTO_API}/articles",
                json={"article": article},
                headers={
                    "api-key": self._devto_key,
                    "Content-Type": "application/json",
                },
                timeout=20,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                url = data.get("url", "")
                post_id = str(data.get("id", ""))
                _record_blog_dedup(dedup_hash)
                logger.info("[VECTOR][blog] Dev.to published: {}", url)
                return PublishResult(platform="devto", success=True, url=url, post_id=post_id)
            return PublishResult(
                platform="devto", success=False,
                error=f"HTTP {resp.status_code}: {resp.text[:120]}",
            )
        except Exception as e:
            logger.warning("[VECTOR][blog] Dev.to publish failed: {}", e)
            return PublishResult(platform="devto", success=False, error=str(e))

    # ── Hashnode ───────────────────────────────────────────────────────────────

    def publish_hashnode(
        self,
        title: str,
        content_markdown: str,
        *,
        tags: list[str] | None = None,
        published: bool = True,
        cover_image_url: str = "",
        subtitle: str = "",
    ) -> PublishResult:
        """
        Publish an article to Hashnode via GraphQL API.
        Requires a Personal Access Token + Publication ID from hashnode.com/settings.
        """
        err = self._check_httpx("hashnode")
        if err:
            return err
        if not self._hashnode_token:
            return PublishResult(platform="hashnode", success=False,
                                 error="HASHNODE_TOKEN not configured")
        if not self._hashnode_pub_id:
            return PublishResult(platform="hashnode", success=False,
                                 error="HASHNODE_PUBLICATION_ID not configured")
        # Dedup: skip if this title was already published to hashnode recently
        dedup_hash = _blog_dedup_hash("hashnode", title)
        if _check_blog_dedup(dedup_hash):
            logger.info("[VECTOR][blog] Hashnode duplicate suppressed: {!r}", title)
            return PublishResult(platform="hashnode", success=True,
                                 error="duplicate_suppressed")
        try:
            tag_slugs = [{"slug": t.lower().replace(" ", "-"), "name": t}
                         for t in (tags or [])]

            mutation = """
            mutation PublishPost($input: PublishPostInput!) {
              publishPost(input: $input) {
                post { id url title }
              }
            }
            """
            variables: dict[str, Any] = {
                "input": {
                    "title": title,
                    "contentMarkdown": content_markdown,
                    "publicationId": self._hashnode_pub_id,
                    "tags": tag_slugs,
                }
            }
            if subtitle:
                variables["input"]["subtitle"] = subtitle
            if cover_image_url:
                variables["input"]["coverImageOptions"] = {"coverImageURL": cover_image_url}

            resp = httpx.post(
                _HASHNODE_API,
                json={"query": mutation, "variables": variables},
                headers={
                    "Authorization": self._hashnode_token,
                    "Content-Type": "application/json",
                },
                timeout=20,
            )
            if resp.status_code == 200:
                body = resp.json()
                errors = body.get("errors")
                if errors:
                    return PublishResult(platform="hashnode", success=False,
                                         error=str(errors[0].get("message", errors)))
                post = body.get("data", {}).get("publishPost", {}).get("post", {})
                url = post.get("url", "")
                post_id = post.get("id", "")
                _record_blog_dedup(dedup_hash)
                logger.info("[VECTOR][blog] Hashnode published: {}", url)
                return PublishResult(platform="hashnode", success=True, url=url, post_id=post_id)
            return PublishResult(
                platform="hashnode", success=False,
                error=f"HTTP {resp.status_code}: {resp.text[:120]}",
            )
        except Exception as e:
            logger.warning("[VECTOR][blog] Hashnode publish failed: {}", e)
            return PublishResult(platform="hashnode", success=False, error=str(e))

    # ── Medium ─────────────────────────────────────────────────────────────────

    def publish_medium(
        self,
        title: str,
        content: str,
        *,
        content_format: str = "markdown",  # "markdown" | "html"
        tags: list[str] | None = None,
        publish_status: str = "public",    # "public" | "draft" | "unlisted"
        canonical_url: str = "",
        notify_followers: bool = True,
    ) -> PublishResult:
        """
        Publish an article to Medium.

        Requires a Medium integration token from medium.com/me/settings.
        First fetches the author ID, then creates the post.
        """
        err = self._check_httpx("medium")
        if err:
            return err
        if not self._medium_token:
            return PublishResult(platform="medium", success=False,
                                 error="MEDIUM_TOKEN not configured")
        # Dedup: skip if this title was already published to medium recently
        dedup_hash = _blog_dedup_hash("medium", title)
        if _check_blog_dedup(dedup_hash):
            logger.info("[VECTOR][blog] Medium duplicate suppressed: {!r}", title)
            return PublishResult(platform="medium", success=True,
                                 error="duplicate_suppressed")
        try:
            headers = {
                "Authorization": f"Bearer {self._medium_token}",
                "Content-Type": "application/json",
            }
            # Step 1: get author user ID
            me_resp = httpx.get(f"{_MEDIUM_API}/me", headers=headers, timeout=10)
            if me_resp.status_code != 200:
                return PublishResult(
                    platform="medium", success=False,
                    error=f"Failed to get user: HTTP {me_resp.status_code}",
                )
            user_id = me_resp.json().get("data", {}).get("id", "")
            if not user_id:
                return PublishResult(platform="medium", success=False,
                                     error="Could not retrieve Medium user ID")

            # Step 2: create post
            payload: dict[str, Any] = {
                "title": title,
                "contentFormat": content_format,
                "content": content,
                "tags": (tags or [])[:5],
                "publishStatus": publish_status,
                "notifyFollowers": notify_followers,
            }
            if canonical_url:
                payload["canonicalUrl"] = canonical_url

            post_resp = httpx.post(
                f"{_MEDIUM_API}/users/{user_id}/posts",
                json=payload,
                headers=headers,
                timeout=20,
            )
            if post_resp.status_code in (200, 201):
                data = post_resp.json().get("data", {})
                url = data.get("url", "")
                post_id = data.get("id", "")
                _record_blog_dedup(dedup_hash)
                logger.info("[VECTOR][blog] Medium published: {}", url)
                return PublishResult(platform="medium", success=True, url=url, post_id=post_id)
            return PublishResult(
                platform="medium", success=False,
                error=f"HTTP {post_resp.status_code}: {post_resp.text[:120]}",
            )
        except Exception as e:
            logger.warning("[VECTOR][blog] Medium publish failed: {}", e)
            return PublishResult(platform="medium", success=False, error=str(e))

    # ── Publish to all configured platforms ────────────────────────────────────

    def publish_all(
        self,
        title: str,
        content_markdown: str,
        *,
        tags: list[str] | None = None,
        platforms: list[str] | None = None,
    ) -> list[PublishResult]:
        """
        Publish to all configured blog platforms at once.
        Only publishes to platforms that have credentials configured.
        platforms: subset of ["devto", "hashnode", "medium"] (default: all).
        """
        target = set(platforms or ["devto", "hashnode", "medium"])
        results: list[PublishResult] = []

        if "devto" in target and self._devto_key:
            results.append(self.publish_devto(title, content_markdown, tags=tags))
        elif "devto" in target:
            results.append(PublishResult(platform="devto", success=False,
                                          error="DEVTO_API_KEY not configured"))

        if "hashnode" in target and self._hashnode_token:
            results.append(self.publish_hashnode(title, content_markdown, tags=tags))
        elif "hashnode" in target:
            results.append(PublishResult(platform="hashnode", success=False,
                                          error="HASHNODE_TOKEN not configured"))

        if "medium" in target and self._medium_token:
            results.append(self.publish_medium(title, content_markdown, tags=tags))
        elif "medium" in target:
            results.append(PublishResult(platform="medium", success=False,
                                          error="MEDIUM_TOKEN not configured"))

        published = [r for r in results if r.success]
        logger.info("[VECTOR][blog] publish_all — {}/{} platforms succeeded",
                    len(published), len(results))
        return results

if __name__ == "__main__":
    pub = BlogPublisher()
    # This self-test must never publish even when the owner's real credentials
    # are configured in the environment.
    pub._devto_key = ""
    pub._hashnode_token = ""
    pub._hashnode_pub_id = ""
    pub._medium_token = ""
    # No keys configured → graceful failures
    r = pub.publish_devto("Test", "# Hello")
    assert r.platform == "devto"
    assert not r.success
    assert r.error

    r2 = pub.publish_hashnode("Test", "# Hello")
    assert not r2.success

    r3 = pub.publish_medium("Test", "# Hello")
    assert not r3.success

    all_results = pub.publish_all("Test", "# Hello", tags=["python"])
    assert len(all_results) == 3
    assert all(not r.success for r in all_results)

    print("OK blog_publisher.py — graceful no-key degradation verified for all 3 platforms")
