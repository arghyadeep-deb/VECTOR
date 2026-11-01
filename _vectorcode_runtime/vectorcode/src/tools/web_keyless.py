"""Keyless web access for VectorCode: bounded direct-HTTP extraction and DuckDuckGo search.

Selected by ``tools.web_tools`` only when no keyed provider (Firecrawl, Parallel, Tavily, Exa) is
configured or detected. No LLM is called here and nothing is summarised or invented: callers get the
text that was retrieved, where it came from, when, or an explicit error / empty result.

Limits (also in docs/superpowers/plans/2026-10-26-vectorcode-web-access.md):
  - plain HTTP GET + stdlib HTML-to-text; no JavaScript, CAPTCHA, consent-wall or login handling
  - PDF text is extracted with bounded pypdf parsing; other binary types are refused
  - at most MAX_FETCH_BYTES are read and MAX_TEXT_CHARS returned; ``truncated`` says when that happened
  - the initial URL and every redirect hop go through ``is_safe_url`` and ``check_website_access``
  - search depends on third-party DuckDuckGo behaviour; bot challenges are reported, never papered over
"""

from __future__ import annotations

import importlib
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from loguru import logger
from tools.url_safety import is_safe_url
from tools.website_policy import check_website_access

FETCH_TIMEOUT = 15.0
SEARCH_TIMEOUT = 10.0
MAX_FETCH_BYTES = 1_000_000
MAX_SEARCH_BYTES = 500_000
MAX_TEXT_CHARS = 12_000
MAX_REDIRECTS = 5
MAX_SEARCH_RESULTS = 20
USER_AGENT = "Mozilla/5.0 (compatible; VectorCode/1.0; keyless-web)"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_TEXT_TYPES = {
    "application/xhtml+xml",
    "application/json",
    "application/xml",
    "application/rss+xml",
    "application/atom+xml",
    "application/javascript",
    "application/x-yaml",
}
_HTML_TYPES = {"text/html", "application/xhtml+xml"}
_CHALLENGE_RE = re.compile(r"anomaly-modal|bots use duckduckgo|unusual traffic|challenge-form", re.I)
_NO_RESULTS_RE = re.compile(r"no\s+results|no-results", re.I)
_BLOCK_TAGS = {
    "p",
    "div",
    "br",
    "li",
    "ul",
    "ol",
    "tr",
    "table",
    "section",
    "article",
    "header",
    "footer",
    "nav",
    "main",
    "pre",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "dd",
    "dt",
    "hr",
}
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "iframe"}


class SearchBackendError(Exception):
    """A search backend failed or was challenged; the message is shown to the caller verbatim."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _transport() -> httpx.BaseTransport | None:
    """Network transport override; None in production. Tests replace only this, keeping the real client setup."""
    return None


def _client() -> httpx.Client:
    """The one place an outbound client is built."""
    return httpx.Client(
        transport=_transport(),
        timeout=httpx.Timeout(FETCH_TIMEOUT),
        follow_redirects=False,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
        },
    )


# ─── URL handling ─────────────────────────────────────────────────────────────


def normalize_url(url: str) -> str | None:
    """Return an http(s) URL (adding ``https://`` to bare hosts), or None for other schemes."""
    value = (url or "").strip()
    if not value:
        return None
    if "://" in value:
        return value if _scheme(value) in ("http", "https") else None
    if value.lower().startswith(("javascript:", "data:", "file:", "mailto:", "ftp:", "about:")):
        return None
    return "https://" + value


def _scheme(url: str) -> str:
    try:
        return urlparse(url).scheme.lower()
    except ValueError:
        return ""


def _malformed(url: str) -> str | None:
    """Reason a URL cannot be fetched safely (unparsable, bad port, embedded credentials), else None."""
    try:
        parsed = urlparse(url)
        parsed.port  # raises ValueError for an invalid port
        host = parsed.hostname
    except ValueError as exc:
        return f"Malformed URL: {exc}"
    if not host:
        return "Malformed URL: no host"
    if parsed.username is not None or parsed.password is not None:
        return "Blocked: URLs with embedded credentials are not fetched"
    return None


def _guard(url: str) -> dict[str, Any] | None:
    """Existing SSRF + website-blocklist checks; returns ``{"error": ...}`` when the URL is refused."""
    scheme = _scheme(url)
    if scheme not in ("http", "https"):
        return {"error": f"Blocked: only http and https URLs are supported (got '{scheme or 'none'}')"}
    bad = _malformed(url)
    if bad:
        return {"error": bad}
    try:
        from urllib.parse import unquote

        from agent.redact import _PREFIX_RE

        if _PREFIX_RE.search(url) or _PREFIX_RE.search(unquote(url)):
            return {"error": "Blocked: URL contains what appears to be an API key or token"}
    except ImportError:
        return {"error": "Blocked: secret-in-URL validation is unavailable"}
    if not is_safe_url(url):
        return {"error": "Blocked: URL targets a private or internal network address"}
    blocked = check_website_access(url)
    if blocked:
        return {
            "error": blocked["message"],
            "blocked_by_policy": {"host": blocked["host"], "rule": blocked["rule"], "source": blocked["source"]},
        }
    return None


# ─── Reading and decoding ─────────────────────────────────────────────────────


def _read_capped(response: httpx.Response, cap: int) -> tuple[bytes, bool]:
    """Read at most ``cap`` decoded bytes; the rest of the stream is never consumed."""
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > cap:
            keep = len(chunk) - (size - cap)
            if keep > 0:
                chunks.append(chunk[:keep])
            return b"".join(chunks), True
        chunks.append(chunk)
    return b"".join(chunks), False


def _is_text_type(content_type: str) -> bool:
    return content_type.startswith("text/") or content_type in _TEXT_TYPES or content_type.endswith(("+xml", "+json"))


def _decode(body: bytes, content_type_header: str) -> str:
    match = re.search(r"charset=([\w.\-]+)", content_type_header or "", re.I)
    if not match:
        match = re.search(rb"<meta[^>]+charset=[\"']?([\w.\-]+)", body[:2048], re.I)
    charset = match.group(1) if match else "utf-8"
    if isinstance(charset, bytes):
        charset = charset.decode("ascii", "ignore")
    try:
        return body.decode(charset, "replace")
    except LookupError:
        return body.decode("utf-8", "replace")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n- " if tag == "li" else "\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip:
            self.parts.append(data)


def _clean(text: str) -> str:
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def _html_to_text(markup: str) -> tuple[str, str]:
    parser = _TextExtractor()
    try:
        parser.feed(markup)
        parser.close()
    except Exception as exc:  # malformed markup: keep what was parsed so far
        logger.debug("[VECTOR][web_keyless] HTML parse stopped early: {}", exc)
    return _clean("".join(parser.title_parts)), _clean("".join(parser.parts))


# ─── Fetch ────────────────────────────────────────────────────────────────────


def fetch(url: str) -> dict[str, Any]:
    """GET one page without any key. Never raises; failures are in ``error``."""
    requested = (url or "").strip()
    out: dict[str, Any] = {
        "url": requested,
        "requested_url": requested,
        "title": "",
        "content": "",
        "raw_content": "",
        "error": None,
        "status": None,
        "content_type": "",
        "retrieved_at": _now(),
        "truncated": False,
        "backend": "direct-http",
    }
    target = normalize_url(requested)
    if target is None:
        out["error"] = "Unsupported URL: only http and https addresses can be fetched"
        return out
    try:
        return _fetch_hops(out, target)
    except ValueError as exc:  # e.g. a redirect Location that cannot be parsed or joined
        out["error"] = f"Malformed URL or redirect: {exc}"
    except Exception as exc:  # never leak an exception to tool callers
        out["error"] = f"Fetch failed: {type(exc).__name__}: {exc}"
    return out


def _fetch_hops(out: dict[str, Any], target: str) -> dict[str, Any]:
    try:
        with _client() as client:
            for hop in range(MAX_REDIRECTS + 1):
                refused = _guard(target)
                if refused:
                    message = refused.pop("error")
                    out["error"] = message if hop == 0 else f"Redirect blocked ({target}): {message}"
                    out["url"] = target
                    out.update(refused)
                    return out
                with client.stream("GET", target) as response:
                    out["status"] = response.status_code
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            out["url"] = target
                            out["error"] = (
                                f"HTTP {response.status_code} redirect from {target} without a Location header"
                            )
                            return out
                        target = urljoin(target, location)
                        continue
                    return _finish(out, response, target)
            out["error"] = f"Too many redirects (more than {MAX_REDIRECTS})"
            out["url"] = target
    except httpx.TimeoutException:
        out["error"] = f"Timed out after {FETCH_TIMEOUT:.0f}s fetching {target}"
    except httpx.HTTPError as exc:
        out["error"] = f"Request failed: {type(exc).__name__}: {exc}"
    return out


def _finish(out: dict[str, Any], response: httpx.Response, target: str) -> dict[str, Any]:
    out["url"] = target
    header = response.headers.get("content-type", "")
    content_type = header.split(";")[0].strip().lower()
    out["content_type"] = content_type
    if response.status_code >= 400:
        out["error"] = f"HTTP {response.status_code} {response.reason_phrase} from {target}".replace("  ", " ")
        return out
    if content_type in {"application/pdf", "application/x-pdf", "application/octet-stream"}:
        body, truncated = _read_capped(response, MAX_FETCH_BYTES)
        if content_type != "application/octet-stream" or body.startswith(b"%PDF-"):
            return _finish_pdf(out, body, truncated)
    if content_type and not _is_text_type(content_type):
        out["error"] = (
            f"Unsupported content type '{content_type}': binary or non-text content is not extracted "
            "by the keyless backend"
        )
        return out
    body, truncated = _read_capped(response, MAX_FETCH_BYTES)
    if not content_type and body.startswith(b"%PDF-"):
        return _finish_pdf(out, body, truncated)
    if not content_type and b"\x00" in body[:1024]:
        out["error"] = "Unsupported content: response looks binary and was not extracted"
        return out
    markup = _decode(body, header)
    looks_html = content_type in _HTML_TYPES or (
        not content_type and re.search(r"<!doctype html|<html", markup[:1024], re.I) is not None
    )
    if looks_html:
        title, text = _html_to_text(markup)
    else:
        title, text = "", _clean(markup)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS].rstrip() + f"\n[... truncated at {MAX_TEXT_CHARS:,} characters ...]"
        truncated = True
    out.update(title=title, content=text, raw_content=text, truncated=truncated)
    if not text:
        out["error"] = "No readable text was extracted (the page may need JavaScript, a login or a consent step)"
    return out


def _finish_pdf(out: dict[str, Any], body: bytes, truncated: bool) -> dict[str, Any]:
    import os
    import subprocess
    import sys
    from pathlib import Path

    if truncated:
        out.update(error="PDF exceeds the 1 MB download limit; incomplete PDFs are not parsed", truncated=True)
        return out
    try:
        from vectorcode.src.tools.environments.local import _sanitize_subprocess_env

        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("pdf_extract.py")),
             "--max-chars", str(MAX_TEXT_CHARS), "--max-bytes", str(MAX_FETCH_BYTES)],
            input=body, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=FETCH_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, check=True,
            env=_sanitize_subprocess_env(dict(os.environ)),
        )
        parsed = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        out["error"] = f"PDF extraction timed out after {FETCH_TIMEOUT:g}s"
        return out
    except Exception:
        out["error"] = "PDF extraction is unavailable or failed; check the installed pypdf dependency"
        return out
    if parsed.get("error"):
        out["error"] = parsed["error"]
        return out
    text = parsed["text"]
    if parsed.get("truncated"):
        text += f"\n[... truncated at {MAX_TEXT_CHARS:,} characters or PDF page limit ...]"
    out.update(content=text, raw_content=text, truncated=bool(parsed.get("truncated")), pdf_pages=parsed.get("pages"))
    return out


# ─── Search ───────────────────────────────────────────────────────────────────


def _ddgs_text(query: str, limit: int) -> list[dict[str, Any]]:
    """Modern ``ddgs`` first, legacy ``duckduckgo_search`` if that is all that is installed or it fails."""
    errors: list[str] = []
    tried = False
    for module_name in ("ddgs", "duckduckgo_search"):
        try:
            client_class = importlib.import_module(module_name).DDGS
        except (ImportError, AttributeError):
            continue
        tried = True
        try:
            rows = list(client_class(timeout=SEARCH_TIMEOUT).text(query, max_results=limit))
        except Exception as exc:
            errors.append(f"{module_name}: {type(exc).__name__}: {exc}")
            continue
        if rows:
            return rows
    if errors:
        raise SearchBackendError("; ".join(errors))
    if not tried:
        raise SearchBackendError("neither 'ddgs' nor legacy 'duckduckgo_search' is installed")
    return []


class _DDGParser(HTMLParser):
    """Collects ``result__a`` links and their ``result__snippet`` text from DuckDuckGo's HTML page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._mode: str | None = None
        self._tag: str | None = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        if self._mode:
            if tag == self._tag:
                self._depth += 1
            return
        if "result__a" in classes and tag == "a":
            self.rows.append({"href": dict(attrs).get("href") or "", "title": [], "body": []})
            self._mode, self._tag, self._depth = "title", tag, 1
        elif ("result__snippet" in classes or "result-snippet" in classes) and self.rows:
            self._mode, self._tag, self._depth = "body", tag, 1

    def handle_endtag(self, tag):
        if self._mode and tag == self._tag:
            self._depth -= 1
            if self._depth <= 0:
                self._mode = self._tag = None

    def handle_data(self, data):
        if self._mode and self.rows:
            self.rows[-1][self._mode].append(data)


def _unwrap_ddg_link(href: str) -> str:
    """Resolve DuckDuckGo's ``/l/?uddg=<target>`` redirect wrapper; '' for ads and internal links."""
    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        href = "https://duckduckgo.com" + href
    parsed = urlparse(href)
    host = (parsed.hostname or "").lower()
    if host == "duckduckgo.com" or host.endswith(".duckduckgo.com"):
        if parsed.path.startswith("/l/"):
            return parse_qs(parsed.query).get("uddg", [""])[0]
        return ""
    return href


def _parse_ddg_html(markup: str) -> list[dict[str, Any]]:
    parser = _DDGParser()
    parser.feed(markup)
    parser.close()
    rows = []
    for raw in parser.rows:
        url = _unwrap_ddg_link(raw["href"])
        if url:
            rows.append(
                {
                    "href": url,
                    "title": _clean("".join(raw["title"])),
                    "body": _clean("".join(raw["body"])),
                }
            )
    return rows


def _ddg_html(query: str, limit: int) -> list[dict[str, Any]]:
    try:
        with _client() as client:
            with client.stream("POST", DDG_HTML_URL, data={"q": query}, timeout=SEARCH_TIMEOUT) as response:
                status = response.status_code
                body, _ = _read_capped(response, MAX_SEARCH_BYTES)
    except httpx.HTTPError as exc:
        raise SearchBackendError(f"DuckDuckGo HTML request failed: {type(exc).__name__}: {exc}") from exc
    markup = body.decode("utf-8", "replace")
    if status in (202, 403, 429) or _CHALLENGE_RE.search(markup):
        raise SearchBackendError(
            f"DuckDuckGo HTML returned a bot challenge or rate limit (HTTP {status}); no results were produced"
        )
    if status >= 400:
        raise SearchBackendError(f"DuckDuckGo HTML returned HTTP {status}")
    rows = _parse_ddg_html(markup)
    if not rows and not _NO_RESULTS_RE.search(markup):
        raise SearchBackendError(
            "DuckDuckGo HTML page had no parseable results and no 'no results' notice "
            "(the markup may have changed, or this is an unrecognised challenge page)"
        )
    return rows[:limit]


def _usable(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Keep http(s) rows the website policy allows; returns (kept, number blocked by policy)."""
    kept: list[dict[str, Any]] = []
    seen = set()
    blocked_count = 0
    for row in rows:
        url = str(row.get("href") or row.get("url") or "").strip()
        if urlparse(url).scheme.lower() not in ("http", "https") or url in seen:
            continue
        if check_website_access(url):
            blocked_count += 1
            continue
        seen.add(url)
        kept.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": url,
                "description": str(row.get("body") or row.get("description") or "").strip()[:300],
                "position": len(kept) + 1,
            }
        )
    return kept, blocked_count


def search(query: str, limit: int = 5) -> dict[str, Any]:
    """Keyless web search. Never raises; the shape matches ``web_search_tool``'s JSON."""
    query = (query or "").strip()
    limit = max(1, min(int(limit or 5), MAX_SEARCH_RESULTS))
    out: dict[str, Any] = {
        "success": False,
        "query": query,
        "backend": "",
        "retrieved_at": _now(),
        "data": {"web": []},
        "attempts": [],
    }
    if not query:
        out["error"] = "Empty search query"
        return out
    for name, runner in (("ddgs", _ddgs_text), ("ddg-html", _ddg_html)):
        try:
            kept, blocked_count = _usable(runner(query, limit))
        except Exception as exc:
            detail = str(exc) if isinstance(exc, SearchBackendError) else f"{type(exc).__name__}: {exc}"
            out["attempts"].append({"backend": name, "status": "error", "detail": detail[:400]})
            logger.warning("[VECTOR][web_keyless] {} search failed: {}", name, detail[:200])
            continue
        if kept:
            out["attempts"].append({"backend": name, "status": "results", "detail": f"{len(kept)} result(s)"})
            out.update(success=True, backend=name)
            out["data"]["web"] = kept[:limit]
            return out
        detail = f"{blocked_count} result(s) skipped by the website policy" if blocked_count else "no results returned"
        out["attempts"].append({"backend": name, "status": "empty", "detail": detail})
    last = out["attempts"][-1]
    if last["backend"] == "ddg-html" and last["status"] == "empty":
        out.update(success=True, backend="ddg-html", message=f"No results found: {last['detail']}")
    else:
        out["error"] = "Keyless search failed. " + "; ".join(
            f"{a['backend']}: {a['status']} ({a['detail']})" for a in out["attempts"]
        )
    return out


# ─── Rendering for terminals and conversation history ─────────────────────────


def render_search(raw: str) -> str:
    """Readable text for a ``web_search_tool`` JSON result (keyless or keyed)."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return f"search error: unreadable result: {str(raw)[:200]}"
    if not isinstance(data, dict):
        return f"search error: unexpected result: {str(raw)[:200]}"
    rows = (data.get("data") or {}).get("web") or []
    source = data.get("backend") or "configured web backend"
    stamp = data.get("retrieved_at") or ""
    if not rows:
        reason = data.get("error") or data.get("message") or "no results"
        return f"search: {reason}" + (f"\n(retrieved {stamp})" if stamp else "")
    lines = [f"Search results via {source}" + (f", retrieved {stamp}" if stamp else "") + ":"]
    for index, row in enumerate(rows, 1):
        lines.append(f"{row.get('position', index)}. {row.get('title') or '(untitled)'}")
        lines.append(f"   {row.get('url', '')}")
        if row.get("description"):
            lines.append(f"   {str(row['description'])[:300]}")
    return "\n".join(lines)


def render_extract(raw: str) -> tuple[bool, str]:
    """(has_content, readable text with provenance) for a ``web_extract_tool`` JSON result."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return False, f"fetch error: unreadable result: {str(raw)[:200]}"
    if not isinstance(data, dict):
        return False, f"fetch error: unexpected result: {str(raw)[:200]}"
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return False, f"fetch error: {data.get('error') or 'no result returned'}"
    blocks: list[str] = []
    has_content = False
    for item in results:
        header = f"Source: {item.get('url') or item.get('requested_url') or '?'}"
        if item.get("requested_url") and item.get("requested_url") != item.get("url"):
            header += f" (requested {item['requested_url']})"
        meta = [
            f"retrieved {item.get('retrieved_at')}" if item.get("retrieved_at") else "",
            f"via {item.get('backend')}" if item.get("backend") else "",
            f"HTTP {item['status']}" if item.get("status") else "",
            "truncated" if item.get("truncated") else "",
        ]
        if any(meta):
            header += "\n" + ", ".join(part for part in meta if part)
        if item.get("title"):
            header += f"\nTitle: {item['title']}"
        content = (item.get("content") or "").strip()
        if item.get("error"):
            blocks.append(f"{header}\nError: {item['error']}")
        elif content:
            has_content = True
            blocks.append(f"{header}\n\n{content}")
        else:
            blocks.append(f"{header}\nNo readable text was returned.")
    return has_content, "\n\n---\n\n".join(blocks)


if __name__ == "__main__":
    assert normalize_url("example.com/a") == "https://example.com/a"
    assert normalize_url("file:///etc/passwd") is None
    title, text = _html_to_text(
        "<html><head><title>T</title></head><body><p>Hello <b>world</b></p><script>x()</script></body></html>"
    )
    assert (title, text) == ("T", "Hello world"), (title, text)
    rows = _parse_ddg_html(
        '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.python.org%2F&rut=x">'
        'Welcome to <b>Python</b>.org</a><a class="result__snippet" href="#">The official home</a>'
    )
    assert rows == [
        {"href": "https://www.python.org/", "title": "Welcome to Python.org", "body": "The official home"}
    ], rows
    assert fetch("https://[")["error"] and fetch("https://user:pw@example.com/")["error"] is not None
    logger.info("[VECTOR][web_keyless] self-check OK")
