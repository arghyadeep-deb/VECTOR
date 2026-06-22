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

