"""Read-only page extraction: fetch one web page and return structured, checkable evidence.

Built 2026-09-26 for the V1 handoff's "workflow C" (a safe, persistent, multi-step browser task: open an index, discover a
detail URL, follow it, extract fields, verify them independently). The model-driven browser stack (BrowserController /
GUIAutomationAgent, RED tier) is built for interaction; this is the opposite on purpose -- a GREEN, read-only primitive
with no login, no cookies, no forms, no JavaScript execution, nothing that changes the outside world:

  * http/https GET only; every hop of a redirect chain is re-checked by the SSRF guard (no private/link-local/metadata
    hosts) and at most `max_redirects` hops are followed;
  * hard size and time limits; only text-like content types are parsed;
  * output is structured (title, named fields, absolute links, a short excerpt, a content hash, the final URL and HTTP
    status) so a plan can bind one step's output into the next and verify it against an independently known value;
  * page text is scanned for prompt-injection and flagged (`injection_suspected`); page text is never executed or fed to a
    model here, and only a short excerpt leaves this function.

Statuses: "ok"; "partial" (page fetched but a required field was not found: `missing_fields`); "error" (blocked URL,
network failure, non-2xx, wrong content type, too large). "partial" and "error" are terminal for the executor, so a plan
step never counts them as done.

Private-network fetches are refused unless VECTOR_WEB_EXTRACT_ALLOW_PRIVATE=1 (tests and local development only).
"""
from __future__ import annotations

__all__ = ["extract_page"]

import datetime
import hashlib
import os
from typing import Any
from urllib.parse import urljoin, urlparse

import httpcore
from loguru import logger

_TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain", "application/xml", "text/xml")
_EXCERPT_CHARS = 1500
_MAX_FIELD_CHARS = 2000


class _PinnedBackend(httpcore.SyncBackend):
    """Connect a validated hostname to its preflight DNS answers without resolving it a second time."""

    def __init__(self, hostname: str, addresses: tuple[str, ...]) -> None:
        self._hostname = hostname.rstrip(".").lower()
        self._addresses = addresses

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if str(host).rstrip(".").lower() != self._hostname or not self._addresses:
            raise OSError(f"connection target {host!r} was not DNS-pinned")
        last_error: Exception | None = None
        for address in self._addresses:
            try:
                return super().connect_tcp(address, port, timeout, local_address, socket_options)
            except (OSError, httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        raise last_error or OSError("all pinned addresses failed")


def _pinned_transport(hostname: str, addresses: tuple[str, ...]):
    """HTTPX transport whose TCP layer uses only addresses approved by the SSRF preflight."""
    import httpx
    import httpx._transports.default as default_transport

    transport = httpx.HTTPTransport(trust_env=False)
    transport._pool.close()
    transport._pool = httpcore.ConnectionPool(
        ssl_context=default_transport.create_ssl_context(verify=True, cert=None, trust_env=False),
        network_backend=_PinnedBackend(hostname, addresses),
    )
    return transport


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _guard(allow_private: bool):
    from core.security.ssrf_guard import SSRFGuard

    return SSRFGuard(allow_private=allow_private, resolve_dns=not allow_private)


def _spec(name: str, raw: Any) -> dict[str, Any]:
    """Normalise a field spec: "css" | "css@attr" | {"selector": .., "attr": .., "all": bool, "required": bool}."""
    if isinstance(raw, str):
        sel, _, attr = raw.partition("@")
        return {"selector": sel.strip(), "attr": attr.strip() or None, "all": False, "required": True}
    if isinstance(raw, dict):
        return {
            "selector": str(raw.get("selector", "")).strip(),
            "attr": (str(raw["attr"]).strip() or None) if raw.get("attr") else None,
            "all": bool(raw.get("all", False)),
            "required": bool(raw.get("required", True)),
        }
    return {"selector": "", "attr": None, "all": False, "required": True}


def _value(node: Any, attr: str | None, base_url: str) -> str:
    if attr:
        v = node.get(attr)
        v = " ".join(v) if isinstance(v, list) else (v or "")
        if attr in ("href", "src", "action") and v:
            v = urljoin(base_url, v)
        return str(v).strip()[:_MAX_FIELD_CHARS]
    return " ".join(node.get_text(" ", strip=True).split())[:_MAX_FIELD_CHARS]


def extract_page(
    url: str,
    fields: dict[str, Any] | None = None,
    *,
    want_links: bool = True,
    max_links: int = 50,
    timeout: float = 15.0,
    max_bytes: int = 2_000_000,
    max_redirects: int = 3,
    allow_private: bool | None = None,
    transport: Any = None,
) -> dict[str, Any]:
    """Fetch `url` and return structured evidence. Never raises."""
    import httpx

    if allow_private is None:
        allow_private = os.environ.get("VECTOR_WEB_EXTRACT_ALLOW_PRIVATE", "") == "1"
    guard = _guard(allow_private)
    requested = url
    base: dict[str, Any] = {"status": "error", "url": requested, "fetched_at": _now()}

    if not isinstance(url, str) or not url.strip():
        return {**base, "error": "no url given"}
    try:
        current = url.strip()
        for hop in range(max_redirects + 1):
            verdict = guard.check_url(current)
            if not verdict.safe:
                return {**base, "url": current, "error": f"blocked by SSRF guard: {verdict.reason}"}
            hop_transport = transport
            if hop_transport is None and not allow_private:
                hop_transport = _pinned_transport(urlparse(current).hostname or "", verdict.addresses)
            # One client per redirect hop keeps connection reuse from crossing a newly validated destination.
            with httpx.Client(follow_redirects=False, timeout=timeout, transport=hop_transport, trust_env=False,
                              headers={"User-Agent": "VECTOR-read-only-extractor/1.0", "Accept": "text/html,text/plain;q=0.9"}) as client:
                resp = client.send(client.build_request("GET", current), stream=True)
                try:
                    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                        if hop >= max_redirects:
                            return {**base, "url": current, "error": f"more than {max_redirects} redirects"}
                        current = urljoin(current, resp.headers["location"])
                        continue
                    if not (200 <= resp.status_code < 300):
                        return {**base, "url": current, "http_status": resp.status_code,
                                "error": f"HTTP {resp.status_code}"}
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype and not ctype.startswith(_TEXT_TYPES):
                        return {**base, "url": current, "http_status": resp.status_code,
                                "error": f"unsupported content type {ctype!r}"}
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            return {**base, "url": current, "http_status": resp.status_code,
                                    "error": f"response larger than {max_bytes} bytes"}
                    charset = resp.encoding or "utf-8"
                    status_code = resp.status_code
                finally:
                    resp.close()
                break
        else:  # pragma: no cover - loop always returns or breaks
            return {**base, "error": "redirect loop"}
    except httpx.TimeoutException:
        return {**base, "error": f"timed out after {timeout}s"}
    except Exception as exc:
        logger.warning("[VECTOR][page_extract] fetch failed for {}: {}", requested, exc)
        return {**base, "error": f"fetch failed: {exc}"}

    text = bytes(body).decode(charset, errors="replace")
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(text, "lxml")
    except Exception as exc:
        return {**base, "url": current, "http_status": status_code, "error": f"could not parse page: {exc}"}

    for junk in soup(["script", "style", "noscript", "template"]):
        junk.decompose()

    out: dict[str, Any] = {
        "status": "ok",
        "url": current,
        "requested_url": requested,
        "http_status": status_code,
        "fetched_at": _now(),
        "content_sha256": hashlib.sha256(bytes(body)).hexdigest(),
        "bytes": len(body),
        "title": " ".join((soup.title.get_text(" ", strip=True) if soup.title else "").split())[:300],
    }

    extracted: dict[str, Any] = {}
    missing: list[str] = []
    for name, raw in (fields or {}).items():
        spec = _spec(str(name), raw)
        try:
            nodes = soup.select(spec["selector"]) if spec["selector"] else []
        except Exception:
            nodes = []
        values = [v for v in (_value(n, spec["attr"], current) for n in nodes) if v]
        if not values:
            if spec["required"]:
                missing.append(str(name))
            continue
        extracted[str(name)] = values if spec["all"] else values[0]
    out["fields"] = extracted

    if want_links:
        links, seen = [], set()
        for a in soup.select("a[href]"):
            href = urljoin(current, a.get("href", "").strip())
            if urlparse(href).scheme in ("http", "https") and href not in seen:
                seen.add(href)
                links.append({"text": " ".join(a.get_text(" ", strip=True).split())[:120], "href": href})
                if len(links) >= max_links:
                    break
        out["links"] = links

    page_text = " ".join(soup.get_text(" ", strip=True).split())
    out["text_excerpt"] = page_text[:_EXCERPT_CHARS]

    try:
        from core.security.prompt_injection import scan_text

        scan = scan_text(out["title"] + "\n" + page_text[:20000], context="page_extract")
        out["injection_suspected"] = not scan.clean
        if not scan.clean:
            out["injection_warnings"] = [w.description for w in scan.warnings[:5]]
            logger.warning("[VECTOR][page_extract] possible prompt injection in {}: {}", current, out["injection_warnings"])
    except Exception:
        out["injection_suspected"] = False

    if missing:
        out["status"] = "partial"
        out["missing_fields"] = missing
    return out


if __name__ == "__main__":
    import http.server
    import threading

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b"<html><head><title>T</title></head><body><h1>Hi</h1><a href='/x'>x</a></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # silence
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    r = extract_page(f"http://127.0.0.1:{srv.server_port}/", {"h": "h1"}, allow_private=True)
    print("page_extract OK" if r["status"] == "ok" and r["fields"] == {"h": "Hi"} else f"FAILED {r}")
    srv.shutdown()
