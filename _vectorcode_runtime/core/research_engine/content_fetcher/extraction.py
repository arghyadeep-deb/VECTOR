"""LLM-friendly web extraction artifacts.

This is the VECTOR-native contract that Crawl4AI-style providers can plug into:
clean markdown/text, source links, timestamps, hashes, and optional query focus.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urljoin


@dataclass
class WebExtractionArtifact:
    url: str
    markdown: str
    content_hash: str
    fetched_at: str
    extraction_mode: str = "vector_clean_markdown"
    title: str | None = None
    links: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def html_to_markdown(html: str, *, base_url: str = "") -> tuple[str, list[dict[str, str]], str | None]:
    """Conservative dependency-free HTML cleanup for fallback extraction."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = _clean_inline(title_match.group(1)) if title_match else None

    links: list[dict[str, str]] = []
    for match in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, re.I | re.S):
        href = urljoin(base_url, unescape(match.group(1)).strip())
        label = _clean_inline(match.group(2))[:160]
        if href:
            links.append({"url": href, "text": label})

    text = re.sub(r"(?is)<(script|style|noscript|svg|canvas).*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|section|article|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = normalize_markdown(text)
    return text, _dedupe_links(links), title


def normalize_markdown(text: str) -> str:
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if line:
            lines.append(line)
    return "\n\n".join(lines)


def focus_markdown(markdown: str, query: str, *, max_chars: int = 12000) -> str:
    """Simple query-focused pruning, inspired by BM25/fit-markdown behavior."""
    if not query or len(markdown) <= max_chars:
        return markdown[:max_chars]
    terms = {t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", query)}
    chunks = [c.strip() for c in re.split(r"\n{2,}", markdown) if c.strip()]
    scored: list[tuple[int, int, str]] = []
    for idx, chunk in enumerate(chunks):
        lower = chunk.lower()
        score = sum(1 for term in terms if term in lower)
        if score:
            scored.append((score, -idx, chunk))
    selected = [c for _, _, c in sorted(scored, reverse=True)]
    if not selected:
        selected = chunks[:]
    out: list[str] = []
    total = 0
    for chunk in selected:
        if total + len(chunk) + 2 > max_chars:
            break
        out.append(chunk)
        total += len(chunk) + 2
    return "\n\n".join(out) or markdown[:max_chars]


def build_extraction_artifact(
    url: str,
    content: str,
    *,
    title: str | None = None,
    links: list[dict[str, str]] | None = None,
    mode: str = "vector_clean_markdown",
    query: str = "",
    max_chars: int = 12000,
    metadata: dict[str, Any] | None = None,
) -> WebExtractionArtifact:
    markdown = normalize_markdown(content)
    markdown = focus_markdown(markdown, query, max_chars=max_chars)
    return WebExtractionArtifact(
        url=url,
        markdown=markdown,
        content_hash=content_hash(markdown),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        extraction_mode=mode,
        title=title,
        links=_dedupe_links(links or []),
        metadata=metadata or {},
    )


class Crawl4AIProvider:
    """Disabled-by-default optional provider wrapping the real `crawl4ai`
    package, when installed. Normalizes its output into the same
    WebExtractionArtifact contract every other extraction path uses —
    docs/repo_analysis/crawl4ai.md's "Implement a disabled-by-default
    Crawl4AI provider path" recommendation. VECTOR works without it
    installed; this class never imports `crawl4ai` until fetch() is called
    with enabled=True.
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._crawler = None

    def available(self) -> bool:
        if not self.enabled:
            return False
        try:
            import crawl4ai  # noqa: F401
            return True
        except Exception:
            return False

    def _load_crawler(self):
        from crawl4ai import AsyncWebCrawler  # type: ignore

        return AsyncWebCrawler()

    async def fetch(self, url: str, query: str = "", max_chars: int = 12000) -> WebExtractionArtifact:
        if not self.available():
            raise RuntimeError("crawl4ai package not installed or provider disabled")
        crawler = self._load_crawler()
        async with crawler as session:
            result = await session.arun(url)

        markdown = getattr(result, "markdown", None) or getattr(result, "html", "") or ""
        links_raw = getattr(result, "links", {}) or {}
        links = [
            {"url": link.get("href", ""), "text": link.get("text", "")}
            for bucket in links_raw.values()
            for link in (bucket or [])
            if link.get("href")
        ]
        metadata = getattr(result, "metadata", {}) or {}
        return build_extraction_artifact(
            getattr(result, "url", url) or url,
            markdown,
            title=metadata.get("title"),
            links=links,
            mode="crawl4ai_clean_markdown",
            query=query,
            max_chars=max_chars,
            metadata=metadata,
        )


def _get_episodic_memory():
    from core.memory.episodic import EpisodicMemory

    return EpisodicMemory()


def persist_extraction_artifact(artifact: WebExtractionArtifact, query: str = "") -> str | None:
    """Store an extraction result as a citation/hash-tracked research
    artifact — docs/repo_analysis/crawl4ai.md item 3: "Normalize outputs
    into VECTOR research artifacts with citations and hashes." Never
    raises (house convention for observe-style persistence calls);
    returns None on any failure instead of propagating.
    """
    try:
        memory = _get_episodic_memory()
        return memory.store(
            event_type="web_extraction_artifact",
            content={
                "url": artifact.url,
                "content_hash": artifact.content_hash,
                "fetched_at": artifact.fetched_at,
                "extraction_mode": artifact.extraction_mode,
                "title": artifact.title,
                "links": artifact.links,
                "query": query,
            },
        )
    except Exception:
        return None


async def fetch_via_vector_scraper(url: str, query: str = "", max_chars: int = 12000) -> WebExtractionArtifact:
    """Primary extraction path — reuses VECTOR's own already-wired scraper
    (core/scraper/vector_scraper.py::VectorScraper, 7 existing callers)
    instead of an external, not-installed package. SSRF-checked, audited,
    real markdown conversion via `markdownify` already built in.

    Crawl4AIProvider above stays as an explicitly optional upgrade for
    crawl4ai-specific features VectorScraper doesn't have (deep-crawl
    resume, BM25 fit-markdown, schema extraction) — not removed, since
    those are genuinely different capabilities, not pure duplication.
    """
    from core.scraper.vector_scraper import VectorScraper

    scraper = VectorScraper()
    result = await scraper.smart_fetch(url)
    if not result.ok:
        raise RuntimeError(f"fetch failed: {result.error or result.status_code}")

    return build_extraction_artifact(
        url,
        result.markdown or result.content,
        mode="vector_scraper_clean_markdown",
        query=query,
        max_chars=max_chars,
        metadata={"fetcher_used": result.fetcher_used, "status_code": result.status_code},
    )


def _clean_inline(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(html))).strip()


def _dedupe_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for link in links:
        url = link.get("url", "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "text": link.get("text", "").strip()})
    return out

