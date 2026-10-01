"""Audit phase 3 -- core/scraper/spiders + core/scraper/cli.py + core/scraper/core/shell.py.

No real network / DNS: the HTTP layer is a fake session and ``socket.getaddrinfo`` is patched.
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import sys
import types

import pytest
from anyio import Path as AsyncPath

from core.scraper.engines.toolbelt.custom import Response
from core.scraper.spiders import LinkExtractor, Spider
from core.scraper.spiders.cache import ResponseCacheManager
from core.scraper.spiders.checkpoint import CheckpointData, CheckpointManager
from core.scraper.spiders.request import Request
from core.scraper.spiders.robotstxt import RobotsTxtManager
from core.scraper.spiders.templates.sitemap import SitemapSpider

PUBLIC_IP = "93.184.216.34"


# --------------------------------------------------------------------------- helpers
def _resp(url: str, body: str = "<html></html>", status: int = 200) -> Response:
    return Response(url=url, content=body, status=status, reason="", cookies={}, headers={}, request_headers={})


class FakeSession:
    """Stands in for FetcherSession: records every URL that would hit the network."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.fetched: list[str] = []
        self._is_alive = False

    async def __aenter__(self):
        self._is_alive = True
        return self

    async def __aexit__(self, *exc):
        self._is_alive = False

    async def fetch(self, url: str, **kwargs):
        self.fetched.append(url)
        page = self.pages.get(url)
        if page is None:
            raise ConnectionError(f"no fake page for {url}")
        if isinstance(page, Exception):
            raise page
        if isinstance(page, Response):
            return page
        return _resp(url, page)


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """Every hostname resolves to a public IP unless a test overrides socket.getaddrinfo."""

    def _gai(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _gai)


def make_spider(pages: dict, tmp_path, *, parse=None, **attrs):
    session = FakeSession(pages)
    errors: list[tuple[str, Exception]] = []

    async def default_parse(self, response):
        for url in LinkExtractor(deny_extensions=[]).extract(response):
            yield response.follow(url)

    ns = {
        "name": "audit_spider",
        "configure_sessions": lambda self, manager: manager.add("default", session),
        "parse": parse or default_parse,
        "on_error": _record_error(errors),
        "log_file": None,
    }
    ns.update(attrs)
    cls = type("AuditSpider", (Spider,), ns)
    spider = cls(**({"crawldir": attrs.pop("crawldir")} if "crawldir" in attrs else {}))
    return spider, session, errors


def _record_error(errors):
    async def on_error(self, request, error):
        errors.append((request.url, error))

    return on_error


# --------------------------------------------------------------------------- SSRF in the crawler
def test_start_url_cloud_metadata_is_never_fetched(tmp_path):
    spider, session, errors = make_spider({}, tmp_path, start_urls=["http://169.254.169.254/latest/meta-data/"])
    result = spider.start()
    assert session.fetched == []
    assert result.stats.ssrf_blocked_count == 1
    assert result.stats.failed_requests_count == 1
    assert errors and isinstance(errors[0][1], PermissionError)


def test_followed_links_to_loopback_and_file_scheme_are_not_fetched(tmp_path):
    page = (
        '<a href="http://127.0.0.1:8080/admin">a</a>'
        '<a href="file:///etc/passwd">b</a>'
        '<a href="http://169.254.169.254/latest/">c</a>'
        '<a href="http://example.com/ok">d</a>'
    )
    pages = {"http://example.com/": page, "http://example.com/ok": "<p>ok</p>"}
    spider, session, _ = make_spider(pages, tmp_path, start_urls=["http://example.com/"])
    result = spider.start()
    assert sorted(session.fetched) == ["http://example.com/", "http://example.com/ok"]
    assert result.stats.ssrf_blocked_count == 3


def test_public_looking_hostname_resolving_to_private_ip_is_blocked(tmp_path, monkeypatch):
    def _gai(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _gai)
    spider, session, _ = make_spider({}, tmp_path, start_urls=["http://rebind.example.net/"])
    result = spider.start()
    assert session.fetched == []
    assert result.stats.ssrf_blocked_count == 1


def test_dns_failure_fails_closed(tmp_path, monkeypatch):
    def _gai(*a, **k):
        raise socket.gaierror("boom")

    monkeypatch.setattr(socket, "getaddrinfo", _gai)
    spider, session, _ = make_spider({}, tmp_path, start_urls=["http://example.com/"])
    result = spider.start()
    assert session.fetched == []
    assert result.stats.ssrf_blocked_count == 1


def test_allow_private_networks_opt_out_fetches_localhost(tmp_path):
    spider, session, _ = make_spider(
        {"http://127.0.0.1:8080/": "<p>hi</p>"}, tmp_path, start_urls=["http://127.0.0.1:8080/"], allow_private_networks=True
    )
    spider.start()
    assert session.fetched == ["http://127.0.0.1:8080/"]


def test_robots_txt_fetch_goes_through_the_guard(tmp_path):
    spider, session, _ = make_spider(
        {}, tmp_path, start_urls=["http://169.254.169.254/"], robots_txt_obey=True
    )
    spider.start()
    assert session.fetched == []  # neither the page nor http://169.254.169.254/robots.txt


# --------------------------------------------------------------------------- robots.txt semantics
def _robots(fetch):
    return RobotsTxtManager(fetch)


def test_robots_fetch_exception_is_not_allow_everything():
    async def fetch(url, sid):
        raise ConnectionError("down")

    assert asyncio.run(_robots(fetch).can_fetch("http://example.com/private", "s")) is False


def test_robots_5xx_means_disallow_all_and_is_retried_not_cached():
    calls = []
    state = {"status": 503}

    async def fetch(url, sid):
        calls.append(url)
        if state["status"] == 503:
            return _resp(url, "", 503)
        return _resp(url, "User-agent: *\nDisallow: /secret\n", 200)

    mgr = _robots(fetch)

    async def go():
        first = await mgr.can_fetch("http://example.com/page", "s")
        state["status"] = 200
        second = await mgr.can_fetch("http://example.com/page", "s")
        return first, second

    assert asyncio.run(go()) == (False, True)
    assert len(calls) == 2


def test_robots_404_means_allow_all():
    async def fetch(url, sid):
        return _resp(url, "", 404)

    assert asyncio.run(_robots(fetch).can_fetch("http://example.com/x", "s")) is True


# --------------------------------------------------------------------------- checkpoint / cache
@pytest.fixture
def windows_like_rename(monkeypatch):
    """os.rename() on Windows refuses to overwrite an existing target."""
    orig = AsyncPath.rename

    async def strict_rename(self, target):
        if await AsyncPath(target).exists():
            raise FileExistsError(str(target))
        return await orig(self, target)

    monkeypatch.setattr(AsyncPath, "rename", strict_rename)


def test_checkpoint_second_save_overwrites_existing_file(tmp_path, windows_like_rename):
    mgr = CheckpointManager(tmp_path / "crawl")

    async def go():
        await mgr.save(CheckpointData(requests=[Request("http://example.com/a")], seen={b"a"}))
        await mgr.save(CheckpointData(requests=[Request("http://example.com/b")], seen={b"b"}))
        return await mgr.load()

    data = asyncio.run(go())
    assert [r.url for r in data.requests] == ["http://example.com/b"]


def test_cache_put_overwrites_existing_entry(tmp_path, windows_like_rename):
    cache = ResponseCacheManager(tmp_path / "cache")

    async def go():
        await cache.put(b"\x01" * 20, _resp("http://example.com/", "one"))
        await cache.put(b"\x01" * 20, _resp("http://example.com/", "two"))
        return await cache.get(b"\x01" * 20)

    assert asyncio.run(go()).body == b"two"


def test_checkpoint_symlink_to_sibling_dir_with_shared_prefix_is_refused(tmp_path):
    crawl, evil = tmp_path / "crawl", tmp_path / "crawl_evil"
    crawl.mkdir()
    evil.mkdir()
    payload = {"requests": [{"url": "http://example.com/x"}], "seen": []}
    (evil / "checkpoint.json").write_text(json.dumps(payload))
    try:
        (crawl / "checkpoint.json").symlink_to(evil / "checkpoint.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert asyncio.run(CheckpointManager(crawl).load()) is None


def test_legacy_pickle_checkpoint_is_not_deserialized(tmp_path):
    crawl = tmp_path / "crawl"
    crawl.mkdir()
    (crawl / "checkpoint.pkl").write_bytes(b"].")  # a pickle (empty list) the old restricted unpickler accepted
    assert asyncio.run(CheckpointManager(crawl).load()) is None


def test_crashed_crawl_keeps_its_checkpoint(tmp_path):
    crawl = tmp_path / "crawl"
    asyncio.run(
        CheckpointManager(crawl).save(CheckpointData(requests=[Request("http://example.com/a", sid="default")], seen=set()))
    )

    async def on_error(self, request, error):  # a spider whose error hook blows up crashes the crawl
        raise RuntimeError("spider crashed")

    spider, _, _ = make_spider({}, tmp_path, crawldir=crawl, on_error=on_error)
    with pytest.raises(BaseException):
        spider.start()
    assert (crawl / "checkpoint.json").exists()


def test_blocked_response_is_not_cached_in_development_mode(tmp_path):
    cache_dir = tmp_path / "cache"
    spider, _, _ = make_spider(
        {"http://example.com/": _resp("http://example.com/", "denied", 503)},
        tmp_path,
        start_urls=["http://example.com/"],
        development_mode=True,
        development_cache_dir=str(cache_dir),
        max_blocked_retries=0,
    )
    spider.start()
    assert not list(cache_dir.glob("*.json"))


# --------------------------------------------------------------------------- result reporting
def test_all_requests_failed_is_not_reported_as_success(tmp_path):
    spider, _, errors = make_spider(
        {"http://example.com/": ConnectionError("down")}, tmp_path, start_urls=["http://example.com/"]
    )
    result = spider.start()
    assert result.stats.failed_requests_count == 1 and result.stats.requests_count == 0
    assert result.succeeded is False


def test_normal_crawl_is_reported_as_success(tmp_path):
    spider, _, _ = make_spider({"http://example.com/": "<p>x</p>"}, tmp_path, start_urls=["http://example.com/"])
    assert spider.start().succeeded is True


# --------------------------------------------------------------------------- sitemap
def test_sitemap_entities_are_not_expanded(tmp_path):
    class S(SitemapSpider):
        name = "sm"
        sitemap_urls = ["http://example.com/sitemap.xml"]

        def configure_sessions(self, manager):
            manager.add("default", FakeSession({}))

        async def on_error(self, request, error):
            pass

    xml = (
        b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "http://127.0.0.1:9/">]>'
        b"<urlset><url><loc>&a;</loc></url></urlset>"
    )
    assert S()._sm_body(xml).urls == []


# --------------------------------------------------------------------------- CLI / shell
def _write_html_response(status: int):
    return _resp("http://example.com/", "<html><body><p>hello</p></body></html>", status)


def test_cli_extract_get_runs_and_writes_file(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from core.scraper import cli
    from core.scraper.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", staticmethod(lambda url, **kw: _write_html_response(200)))
    out = tmp_path / "out.txt"
    result = CliRunner().invoke(cli.main, ["extract", "get", "http://example.com/", str(out)])
    assert result.exit_code == 0, result.output
    assert "hello" in out.read_text()


def test_cli_extract_http_error_status_exits_nonzero(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from core.scraper import cli
    from core.scraper.fetchers import Fetcher

    monkeypatch.setattr(Fetcher, "get", staticmethod(lambda url, **kw: _write_html_response(404)))
    out = tmp_path / "out.txt"
    result = CliRunner().invoke(cli.main, ["extract", "get", "http://example.com/", str(out)])
    assert result.exit_code != 0
    assert out.exists()  # the error page is still saved for inspection


def test_cli_mcp_defaults_to_loopback():
    from core.scraper import cli

    host = next(p for p in cli.mcp.params if p.name == "host")
    assert host.default == "127.0.0.1"


def test_cli_shell_code_failure_exits_nonzero(monkeypatch):
    from click.testing import CliRunner

    from core.scraper import cli

    class FakeShell:
        def __init__(self, **kw):
            pass

        def __call__(self):
            pass

        def run_cell(self, code, store_history=False):
            return types.SimpleNamespace(success=False, error_before_exec=None, error_in_exec=NameError("x"))

    for name in ("IPython", "IPython.terminal", "IPython.terminal.embed"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    sys.modules["IPython.terminal.embed"].InteractiveShellEmbed = FakeShell
    result = CliRunner().invoke(cli.main, ["shell", "-c", "undefined_name"])
    assert result.exit_code != 0


def test_write_content_does_not_clobber_existing_file_on_extraction_error(tmp_path):
    from core.scraper.core.shell import Convertor

    target = tmp_path / "keep.md"
    target.write_text("precious")
    with pytest.raises(Exception):
        Convertor.write_content_to_file(_write_html_response(200), str(target), css_selector="p[[[")
    assert target.read_text() == "precious"


def test_curl_parse_does_not_log_proxy_credentials(caplog):
    from core.scraper.core.shell import CurlParser

    caplog.set_level(logging.DEBUG, logger="vector_scraper")
    req = CurlParser().parse("curl https://example.com -x http://proxy.local:3128 -U alice:s3cretpw")
    assert "alice:s3cretpw" in req.proxy["http"]  # still used for the request
    assert "s3cretpw" not in caplog.text


def test_curl_parse_does_not_eat_leading_letters_of_the_url():
    from core.scraper.core.shell import CurlParser

    req = CurlParser().parse("culr.example.com/path -X GET")  # no "curl" prefix: lstrip("curl") used to eat "cul"
    assert req.url == "culr.example.com/path"
