"""Phase-3 audit: SSRF / proxy / logging fixes at the core/scraper fetch entry points.

No real network or DNS: socket.getaddrinfo is monkeypatched and the HTTP/browser layer is faked.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from curl_cffi.curl import CurlError  # noqa: E402

from core.scraper import vector_scraper as vs  # noqa: E402
from core.scraper.engines import static  # noqa: E402

REBIND_HOST = "totally-public-looking.example"
PUBLIC_IP = "93.184.216.34"
_real_getaddrinfo = socket.getaddrinfo


def _fake_dns(mapping: dict[str, str]):
    """getaddrinfo that answers from `mapping`; numeric hosts fall through to the real resolver (no network)."""

    def fake(host, port, *args, **kwargs):
        if host in mapping:
            ip = mapping[host]
            fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
            return [(fam, socket.SOCK_STREAM, 6, "", (ip, port or 0))]
        if host and host.replace(".", "").isdigit() or (host or "").lower().startswith("0x"):
            return _real_getaddrinfo(host, port, *args, **kwargs)
        raise socket.gaierror(-2, "Name or service not known")

    return fake


class _Sentinel(Exception):
    """Raised by fake HTTP sessions so a request that reaches the client is observable."""


class _FakeCurlSession:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def request(self, method, **kw):
        self.calls.append((method, kw))
        raise _Sentinel("client reached")

    async def arequest(self, method, **kw):  # pragma: no cover - helper symmetry
        return self.request(method, **kw)


class _AsyncFakeCurlSession(_FakeCurlSession):
    async def request(self, method, **kw):  # type: ignore[override]
        self.calls.append((method, kw))
        raise _Sentinel("client reached")


def _async_client(**kw):
    client = static.AsyncFetcherClient(**kw)
    fake = _AsyncFakeCurlSession()
    client._async_curl_session = fake
    client.__aenter__ = None  # keep one-off-session branch disabled; we inject our own session
    return client, fake


def _sync_client(**kw):
    client = static.FetcherClient(**kw)
    fake = _FakeCurlSession()
    client._curl_session = fake
    return client, fake


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({REBIND_HOST: PUBLIC_IP}))


# ---------------------------------------------------------------- engine (static.py)

REBIND_TARGETS = ["127.0.0.1", "169.254.169.254", "10.1.2.3", "::1", "192.168.0.10"]


@pytest.mark.parametrize("ip", REBIND_TARGETS)
def test_engine_async_blocks_hostname_resolving_to_internal_ip(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({REBIND_HOST: ip}))
    client, fake = _async_client()
    with pytest.raises(Exception) as ei:
        asyncio.run(client.get(f"http://{REBIND_HOST}/latest/meta-data/"))
    assert fake.calls == [], "HTTP client must not be reached for a host resolving to an internal address"
    assert "SSRF" in str(ei.value)


@pytest.mark.parametrize("ip", REBIND_TARGETS)
def test_engine_sync_blocks_hostname_resolving_to_internal_ip(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({REBIND_HOST: ip}))
    client, fake = _sync_client()
    with pytest.raises(Exception) as ei:
        client.get(f"https://{REBIND_HOST}/")
    assert fake.calls == []
    assert "SSRF" in str(ei.value)


def test_engine_fails_closed_on_dns_error():
    client, fake = _async_client()
    with pytest.raises(Exception) as ei:
        asyncio.run(client.get("http://does-not-resolve.example/"))
    assert fake.calls == []
    assert "SSRF" in str(ei.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://2130706433/",  # decimal loopback, resolved by the OS resolver
        "http://0x7f000001/",  # hex loopback
        "http://localhost./",  # trailing-dot localhost
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com/x",
        "data:text/html,hi",
        f"http://{REBIND_HOST}:6379/",  # blocked port
    ],
)
def test_engine_blocks_scheme_and_ip_tricks(monkeypatch, url):
    monkeypatch.setattr(
        socket, "getaddrinfo", _fake_dns({REBIND_HOST: PUBLIC_IP, "localhost.": "127.0.0.1"})
    )
    client, fake = _async_client()
    with pytest.raises(Exception):
        asyncio.run(client.get(url))
    assert fake.calls == []


def test_engine_userinfo_trick_connects_to_real_host_only(monkeypatch):
    # curl and urlparse both treat the part after '@' as the host: this is evil.example (public), not 127.0.0.1.
    client, fake = _async_client()
    with pytest.raises(_Sentinel):
        asyncio.run(client.get(f"http://127.0.0.1@{REBIND_HOST}/"))
    assert len(fake.calls) == 1
    # ...and the reverse: the real host is 127.0.0.1, userinfo is a public-looking name.
    client2, fake2 = _async_client()
    with pytest.raises(Exception) as ei:
        asyncio.run(client2.get(f"http://{REBIND_HOST}@127.0.0.1/"))
    assert fake2.calls == [] and "SSRF" in str(ei.value)


def test_engine_allows_public_host():
    client, fake = _async_client()
    with pytest.raises(_Sentinel):
        asyncio.run(client.get(f"https://{REBIND_HOST}/page"))
    assert len(fake.calls) == 1


def test_engine_skips_local_dns_when_proxied(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("local DNS must not be used when a proxy resolves the host")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    client, fake = _async_client()
    with pytest.raises(_Sentinel):
        asyncio.run(client.get(f"https://{REBIND_HOST}/", proxy="http://proxy.example:8080"))
    assert len(fake.calls) == 1
    # literal internal IPs are still refused with a proxy
    client2, fake2 = _async_client()
    with pytest.raises(Exception):
        asyncio.run(client2.get("http://127.0.0.1/", proxy="http://proxy.example:8080"))
    assert fake2.calls == []


def test_engine_session_default_proxy_is_used():
    client, fake = _async_client(proxy="http://user:pw@proxy.example:8080")
    with pytest.raises(_Sentinel):
        asyncio.run(client.get(f"https://{REBIND_HOST}/"))
    assert fake.calls[0][1]["proxy"] == "http://user:pw@proxy.example:8080"


def test_engine_explicit_proxy_none_still_disables_default():
    client, fake = _async_client(proxy="http://user:pw@proxy.example:8080")
    with pytest.raises(_Sentinel):
        asyncio.run(client.get(f"https://{REBIND_HOST}/", proxy=None))
    assert fake.calls[0][1]["proxy"] is None


def test_proxy_credentials_not_logged(caplog):
    class _FailingSession(_AsyncFakeCurlSession):
        async def request(self, method, **kw):  # type: ignore[override]
            raise CurlError("Failed to connect to proxy")

    client = static.AsyncFetcherClient(
        proxy="http://proxyuser:hunter2secret@proxy.example:8080", retries=2, retry_delay=0
    )
    client._async_curl_session = _FailingSession()
    logging.getLogger("vector_scraper").propagate = True
    with caplog.at_level(logging.INFO, logger="vector_scraper"):
        with pytest.raises(CurlError):
            asyncio.run(client.get(f"https://{REBIND_HOST}/"))
    text = caplog.text
    assert "proxy.example" in text
    assert "hunter2secret" not in text and "proxyuser" not in text


def test_redact_url_drops_secrets():
    out = static.redact_url("https://u:pw@host.example:8443/p/a?api_key=SECRET#frag")
    assert out == "https://host.example:8443/p/a"


# ---------------------------------------------------------------- VectorScraper wrapper


class _FakeResp:
    status = 200
    html_content = "<html><body>ok</body></html>"
    text = "ok"


def _install_fake_async_fetcher(monkeypatch):
    import core.scraper.fetchers as fetchers

    seen: dict = {"calls": []}

    class FakeAsyncFetcher:
        def __init__(self, *a, **k):  # deprecated no-op constructor like the real BaseFetcher
            seen["init"] = k

        @classmethod
        async def get(cls, url, **kw):
            seen["calls"].append(("GET", url, kw))
            return _FakeResp()

        @classmethod
        async def post(cls, url, **kw):
            seen["calls"].append(("POST", url, kw))
            return _FakeResp()

    monkeypatch.setattr(fetchers, "AsyncFetcher", FakeAsyncFetcher, raising=False)
    return seen


@pytest.mark.parametrize("ip", ["127.0.0.1", "169.254.169.254", "10.0.0.5"])
def test_vector_scraper_fetch_blocks_dns_rebind_host(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({REBIND_HOST: ip}))
    seen = _install_fake_async_fetcher(monkeypatch)
    res = asyncio.run(vs.VectorScraper().fetch(f"http://{REBIND_HOST}/secret"))
    assert seen["calls"] == [], "HTTP client must never be called for a host resolving to an internal IP"
    assert not res.ok and res.error == "SSRF blocked" and res.status_code == 403


def test_vector_scraper_fails_closed_on_dns_error(monkeypatch):
    seen = _install_fake_async_fetcher(monkeypatch)
    res = asyncio.run(vs.VectorScraper().fetch("http://nxdomain.example/"))
    assert seen["calls"] == []
    assert res.error == "SSRF blocked"


def test_vector_scraper_stealth_and_dynamic_blocked_before_browser(monkeypatch):
    import core.scraper.fetchers as fetchers

    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({REBIND_HOST: "127.0.0.1"}))
    launched: list = []

    class FakeBrowser:
        def __init__(self, *a, **k):
            launched.append(1)

    monkeypatch.setattr(fetchers, "StealthyFetcher", FakeBrowser, raising=False)
    monkeypatch.setattr(fetchers, "DynamicFetcher", FakeBrowser, raising=False)
    s = vs.VectorScraper()
    r1 = asyncio.run(s.fetch_stealth(f"http://{REBIND_HOST}/"))
    r2 = asyncio.run(s.fetch_dynamic(f"http://{REBIND_HOST}/"))
    assert launched == []
    assert r1.error == "SSRF blocked" and r2.error == "SSRF blocked"
    assert asyncio.run(s.crawl(f"http://{REBIND_HOST}/")) == []


def test_vector_scraper_public_host_still_fetches(monkeypatch):
    seen = _install_fake_async_fetcher(monkeypatch)
    res = asyncio.run(vs.VectorScraper().fetch(f"https://{REBIND_HOST}/ok"))
    assert res.ok and len(seen["calls"]) == 1


def test_vector_scraper_fetch_passes_proxy_timeout_impersonate_to_request(monkeypatch):
    seen = _install_fake_async_fetcher(monkeypatch)
    s = vs.VectorScraper(proxy="http://proxy.example:8080", timeout=7, impersonate="firefox")
    asyncio.run(s.fetch(f"https://{REBIND_HOST}/"))
    kw = seen["calls"][0][2]
    assert kw["proxy"] == "http://proxy.example:8080"
    assert kw["timeout"] == 7 and kw["impersonate"] == "firefox"


def test_vector_scraper_audit_and_logs_omit_query_secrets(monkeypatch):
    _install_fake_async_fetcher(monkeypatch)
    payloads: list[dict] = []

    class FakeChain:
        def log(self, **kw):
            payloads.append(kw["payload"])

    import core.audit.merkle_chain as mc

    monkeypatch.setattr(mc, "get_audit_chain", lambda: FakeChain())
    asyncio.run(vs.VectorScraper().fetch(f"https://user:pw@{REBIND_HOST}/p?api_key=SUPERSECRET&x=1"))
    assert payloads, "audit entry expected"
    assert "SUPERSECRET" not in payloads[0]["url"] and "pw@" not in payloads[0]["url"]
    assert payloads[0]["url"] == f"https://{REBIND_HOST}/p"


def test_no_literal_suppressed_exception_message_left():
    src = Path(vs.__file__).read_text(encoding="utf-8")
    assert "suppressed exception" not in src


# ---------------------------------------------------------------- MCP server (core/ai.py)


def test_mcp_bulk_get_clamps_follow_redirects_to_safe(monkeypatch):
    from core.scraper.core import ai

    seen: list = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        def get(self, url, **kw):
            seen.append(kw["follow_redirects"])
            raise _Sentinel("stop")

    monkeypatch.setattr(ai, "FetcherSession", FakeSession)
    for requested in (True, "all", "safe"):
        with pytest.raises(_Sentinel):
            asyncio.run(ai.VectorScraperMCPServer.bulk_get(urls=[f"https://{REBIND_HOST}/"], follow_redirects=requested))
    assert seen == ["safe", "safe", "safe"]


def test_mcp_browser_tools_block_internal_hosts_before_launching(monkeypatch):
    from core.scraper.core import ai

    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({REBIND_HOST: "169.254.169.254"}))
    launched: list = []

    class FakeSession:
        def __init__(self, *a, **k):
            launched.append(1)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def fetch(self, *a, **k):
            launched.append("fetch")
            raise _Sentinel("browser navigated")

    monkeypatch.setattr(ai, "AsyncDynamicSession", FakeSession)
    monkeypatch.setattr(ai, "AsyncStealthySession", FakeSession)
    srv = ai.VectorScraperMCPServer()
    url = f"http://{REBIND_HOST}/latest/meta-data/"
    with pytest.raises(Exception) as e1:
        asyncio.run(srv.bulk_fetch(urls=[url]))
    with pytest.raises(Exception) as e2:
        asyncio.run(srv.bulk_stealthy_fetch(urls=[url]))
    assert launched == []
    assert "SSRF" in str(e1.value) and "SSRF" in str(e2.value)

    # screenshot via an already-open session must be guarded too
    srv._sessions["s1"] = ai._SessionEntry(session=FakeSession(), session_type="dynamic")
    srv._sessions["s1"].session._is_alive = True
    launched.clear()
    with pytest.raises(Exception) as e3:
        asyncio.run(srv.screenshot(url, session_id="s1"))
    assert "fetch" not in launched and "SSRF" in str(e3.value)


def test_browser_fetchers_block_before_session_creation(monkeypatch):
    from core.scraper.fetchers import chrome, stealth_chrome

    monkeypatch.setattr(socket, "getaddrinfo", _fake_dns({REBIND_HOST: "127.0.0.1"}))
    created: list = []

    class Fake:
        def __init__(self, *a, **k):
            created.append(1)

    monkeypatch.setattr(chrome, "DynamicSession", Fake)
    monkeypatch.setattr(chrome, "AsyncDynamicSession", Fake)
    monkeypatch.setattr(stealth_chrome, "StealthySession", Fake)
    monkeypatch.setattr(stealth_chrome, "AsyncStealthySession", Fake)
    url = f"http://{REBIND_HOST}/"
    with pytest.raises(Exception) as e1:
        chrome.DynamicFetcher.fetch(url)
    with pytest.raises(Exception) as e2:
        asyncio.run(chrome.DynamicFetcher.async_fetch(url))
    with pytest.raises(Exception) as e3:
        stealth_chrome.StealthyFetcher.fetch(url)
    with pytest.raises(Exception) as e4:
        asyncio.run(stealth_chrome.StealthyFetcher.async_fetch(url))
    assert created == []
    assert all("SSRF" in str(e.value) for e in (e1, e2, e3, e4))
