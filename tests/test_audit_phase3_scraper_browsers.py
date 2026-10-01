"""Audit phase 3 - core/scraper/engines/_browsers + toolbelt regression tests.

No real browser, network or DNS: Playwright objects are MagicMock/AsyncMock fakes and socket.getaddrinfo is patched.
"""
from __future__ import annotations

import logging
import socket
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright._impl._errors import Error as PlaywrightError

from core.scraper.engines._browsers import _controllers, _stealth
from core.scraper.engines._browsers._controllers import AsyncDynamicSession, DynamicSession
from core.scraper.engines._browsers._stealth import AsyncStealthySession, StealthySession
from core.scraper.engines._browsers._validators import PlaywrightConfig, StealthConfig, validate
from core.scraper.engines.toolbelt.convertor import ResponseFactory
from core.scraper.engines.toolbelt.custom import BaseFetcher, Response

PUBLIC_IP = "93.184.216.34"


def _dns(monkeypatch, ip: str = PUBLIC_IP):
    calls: list[str] = []

    def fake_getaddrinfo(host, port, *a, **kw):
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    return calls


def _sync_page():
    page = MagicMock()
    page.goto.return_value = MagicMock()
    return page


def _async_page():
    page = MagicMock()
    for name in ("goto", "wait_for_load_state", "wait_for_timeout", "set_extra_http_headers", "route", "close"):
        setattr(page, name, AsyncMock())
    return page


def _make(kind: str):
    """Return (session, new_page_mock) for one of the four session types, already 'started' with fakes."""
    cls = {"dyn": DynamicSession, "dyn_async": AsyncDynamicSession, "st": StealthySession, "st_async": AsyncStealthySession}[kind]
    sess = cls(retries=1, retry_delay=0)
    sess._is_alive = True
    if kind.endswith("async"):
        sess.context = MagicMock()
        sess.context.new_page = AsyncMock(return_value=_async_page())
    else:
        sess.context = MagicMock()
        sess.context.new_page.return_value = _sync_page()
    return sess, sess.context.new_page


async def _fetch(sess, url: str):
    res = sess.fetch(url)
    if hasattr(res, "__await__"):
        res = await res
    return res


KINDS = ["dyn", "dyn_async", "st", "st_async"]


@pytest.fixture(autouse=True)
def _fake_response_factory(monkeypatch):
    sentinel = object()
    fake = MagicMock()
    fake.from_playwright_response.return_value = sentinel
    fake.from_async_playwright_response = AsyncMock(return_value=sentinel)
    for mod in (_controllers, _stealth):
        monkeypatch.setattr(mod, "ResponseFactory", fake)
    return sentinel


# --------------------------------------------------------------------------- SSRF on navigation
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "chrome://settings",
        "javascript:alert(1)",
        "data:text/html,<script>1</script>",
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8000/admin",
        "http://localhost/",
    ],
)
async def test_navigation_blocks_unsafe_urls_before_any_page(kind, url, monkeypatch):
    _dns(monkeypatch)
    sess, new_page = _make(kind)
    with pytest.raises(ValueError, match="SSRF"):
        await _fetch(sess, url)
    new_page.assert_not_called()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("ip", ["127.0.0.1", "169.254.169.254", "10.1.2.3"])
async def test_navigation_blocks_hostname_resolving_to_internal_ip(kind, ip, monkeypatch):
    calls = _dns(monkeypatch, ip)
    sess, new_page = _make(kind)
    with pytest.raises(ValueError, match="SSRF"):
        await _fetch(sess, "https://totally-public-looking.example.com/x")
    assert calls, "hostname must actually be resolved"
    new_page.assert_not_called()


@pytest.mark.parametrize("kind", KINDS)
async def test_navigation_fails_closed_on_dns_error(kind, monkeypatch):
    def boom(*a, **kw):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    sess, new_page = _make(kind)
    with pytest.raises(ValueError, match="SSRF"):
        await _fetch(sess, "https://nx.example.com/")
    new_page.assert_not_called()


@pytest.mark.parametrize("kind", KINDS)
async def test_navigation_allows_public_url(kind, monkeypatch, _fake_response_factory):
    _dns(monkeypatch)
    sess, new_page = _make(kind)
    result = await _fetch(sess, "https://example.com/page")
    assert result is _fake_response_factory
    page = new_page.return_value if kind in ("dyn", "st") else new_page.return_value
    page.goto.assert_called_once()
    assert page.goto.call_args.args[0] == "https://example.com/page"


async def test_non_string_url_rejected(monkeypatch):
    _dns(monkeypatch)
    sess, new_page = _make("dyn")
    with pytest.raises(TypeError):
        sess.fetch(None)  # type: ignore[arg-type]
    new_page.assert_not_called()


# --------------------------------------------------------------------------- launch flags
def test_extra_flags_no_longer_drop_stealth_flags():
    sess = StealthySession(extra_flags=["--lang=de"], block_webrtc=True, allow_webgl=False)
    args = list(sess._browser_options["args"])
    assert "--lang=de" in args
    assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in args
    assert "--disable-webgl" in args
    assert "--mute-audio" in args  # a STEALTH_ARGS entry
    assert len(args) == len(set(args))


def test_dynamic_extra_flags_keep_default_args():
    sess = DynamicSession(extra_flags=["--foo-bar"])
    args = list(sess._browser_options["args"])
    assert "--foo-bar" in args and "--no-first-run" in args


@pytest.mark.parametrize(
    "flag",
    [
        "--remote-debugging-port=9222",
        "--REMOTE-DEBUGGING-ADDRESS=0.0.0.0",
        "--disable-web-security",
        "--load-extension=/tmp/evil",
        "--user-data-dir=/home/u/.config/google-chrome",
        "--no-sandbox",
        "--proxy-server=http://evil:8080",
        "--host-resolver-rules=MAP * 127.0.0.1",
    ],
)
def test_dangerous_chrome_flags_rejected(flag):
    with pytest.raises((ValueError, TypeError), match="(?i)not allowed|extra_flags"):
        validate({"extra_flags": [flag]}, PlaywrightConfig)
    with pytest.raises((ValueError, TypeError)):
        DynamicSession(extra_flags=[flag])


def test_non_switch_extra_flag_rejected():
    # Chrome would open this as a start URL, bypassing the navigation guard
    with pytest.raises((ValueError, TypeError), match="switch"):
        validate({"extra_flags": ["file:///etc/passwd"]}, PlaywrightConfig)


def test_safe_flags_accepted():
    cfg = validate({"extra_flags": ["--lang=fr", "--mute-audio"]}, StealthConfig)
    assert cfg.extra_flags == ["--lang=fr", "--mute-audio"]


@pytest.mark.parametrize("key", ["args", "executable_path", "env", "record_har_path", "storage_state", "channel"])
def test_additional_args_cannot_override_launch_options(key):
    with pytest.raises((ValueError, TypeError), match="additional_args"):
        validate({"additional_args": {key: "x"}}, PlaywrightConfig)


def test_additional_args_regular_options_still_work():
    cfg = validate({"additional_args": {"java_script_enabled": False}}, PlaywrightConfig)
    assert cfg.additional_args == {"java_script_enabled": False}


# --------------------------------------------------------------------------- validators
def test_zero_timeout_rejected():
    with pytest.raises((ValueError, TypeError)):
        validate({"timeout": 0}, PlaywrightConfig)


def test_init_script_validation_not_stuck_on_stale_cache(tmp_path):
    script = tmp_path / "late_script.js"
    with pytest.raises((ValueError, TypeError), match="not found"):
        validate({"init_script": str(script)}, PlaywrightConfig)
    script.write_text("window.x = 1;", encoding="utf-8")
    assert validate({"init_script": str(script)}, PlaywrightConfig).init_script == str(script)


def test_cdp_url_scheme_and_proxy_conflict_rejected():
    with pytest.raises((ValueError, TypeError)):
        validate({"cdp_url": "http://127.0.0.1:9222"}, PlaywrightConfig)
    with pytest.raises((ValueError, TypeError)):
        validate({"proxy": "http://p:1", "proxy_rotator": object()}, PlaywrightConfig)


# --------------------------------------------------------------------------- resource cleanup
def test_sync_close_releases_everything_when_context_close_fails():
    sess = DynamicSession()
    ctx, browser, pw = MagicMock(), MagicMock(), MagicMock()
    ctx.close.side_effect = PlaywrightError("Target closed")
    sess.context, sess.browser, sess.playwright, sess._is_alive = ctx, browser, pw, True
    sess.close()
    browser.close.assert_called_once()
    pw.stop.assert_called_once()
    assert sess._is_alive is False and sess.context is None and sess.browser is None and sess.playwright is None


async def test_async_close_releases_everything_when_browser_close_fails():
    sess = AsyncDynamicSession()
    ctx, browser, pw = MagicMock(), MagicMock(), MagicMock()
    ctx.close = AsyncMock(side_effect=PlaywrightError("Target closed"))
    browser.close = AsyncMock()
    pw.stop = AsyncMock()
    sess.context, sess.browser, sess.playwright, sess._is_alive = ctx, browser, pw, True
    await sess.close()
    browser.close.assert_awaited_once()
    pw.stop.assert_awaited_once()
    assert sess._is_alive is False and sess.playwright is None


def test_page_close_failure_does_not_leak_pool_slot():
    sess, new_page = _make("dyn")
    new_page.return_value.close.side_effect = PlaywrightError("page crashed")
    with sess._page_generator(1000, None, False):
        assert sess.page_pool.pages_count == 1
    assert sess.page_pool.pages_count == 0


async def test_async_page_close_failure_does_not_leak_pool_slot():
    sess, new_page = _make("dyn_async")
    new_page.return_value.close.side_effect = PlaywrightError("page crashed")
    async with sess._page_generator(1000, None, False):
        assert sess.page_pool.pages_count == 1
    assert sess.page_pool.pages_count == 0


# --------------------------------------------------------------------------- failure reported as success
def _fake_sync_pw_response(status=200, ctype="text/html"):
    r = MagicMock()
    r.status = status
    r.status_text = "OK"
    r.headers = {"content-type": ctype}
    r.all_headers.return_value = {"content-type": ctype}
    r.request.redirected_from = None
    r.request.all_headers.return_value = {}
    r.url = "https://example.com/"
    r.body.side_effect = PlaywrightError("body unavailable")
    return r


def test_unreadable_main_document_raises_instead_of_empty_200():
    page = MagicMock()
    page.url = "https://example.com/"
    page.content.side_effect = PlaywrightError("page navigated away")
    page.context.cookies.return_value = []
    resp = _fake_sync_pw_response()
    with pytest.raises(RuntimeError, match="page content"):
        ResponseFactory.from_playwright_response(page, resp, resp, {})


def test_unreadable_captured_xhr_body_stays_tolerated():
    resp = _fake_sync_pw_response(ctype="application/json")
    out = ResponseFactory.from_playwright_response(None, resp, None, {}, collect_history=False)
    assert out.status == 200 and out.body == b""


async def test_async_unreadable_main_document_raises_instead_of_empty_200():
    page = MagicMock()
    page.url = "https://example.com/"
    page.content = AsyncMock(side_effect=PlaywrightError("page navigated away"))
    page.wait_for_timeout = AsyncMock()
    page.context.cookies = AsyncMock(return_value=[])
    resp = _fake_sync_pw_response()
    resp.all_headers = AsyncMock(return_value={"content-type": "text/html"})
    resp.request.all_headers = AsyncMock(return_value={})
    with pytest.raises(RuntimeError, match="page content"):
        await ResponseFactory.from_async_playwright_response(page, resp, resp, {})


# --------------------------------------------------------------------------- secrets in logs
async def test_proxy_credentials_not_logged_on_retry(caplog):
    sess = DynamicSession(retries=2, retry_delay=0)
    sess._is_alive = True
    sess.browser = MagicMock()
    ctx = MagicMock()
    sess.browser.new_context.return_value = ctx
    ctx.new_page.return_value.goto.side_effect = PlaywrightError("net::ERR_PROXY_CONNECTION_FAILED")
    import socket as _s

    orig = _s.getaddrinfo
    _s.getaddrinfo = lambda h, p, *a, **k: [(_s.AF_INET, _s.SOCK_STREAM, 6, "", (PUBLIC_IP, p or 0))]
    try:
        with caplog.at_level(logging.INFO, logger="vector_scraper"):
            with pytest.raises(PlaywrightError):
                sess.fetch("https://example.com/", proxy="http://user:SuperSecret@proxy.example:8080")
    finally:
        _s.getaddrinfo = orig
    assert "Proxy" in caplog.text
    assert "SuperSecret" not in caplog.text


def test_response_log_strips_url_query_and_userinfo(caplog):
    with caplog.at_level(logging.INFO, logger="vector_scraper"):
        Response(
            url="https://bob:pw123@example.com/path?api_key=TOPSECRET#frag",
            content=b"<html></html>",
            status=200,
            reason="OK",
            cookies={},
            headers={},
            request_headers={},
        )
    assert "Fetched (200)" in caplog.text
    assert "example.com/path" in caplog.text
    assert "TOPSECRET" not in caplog.text and "pw123" not in caplog.text


def test_basefetcher_deprecation_warning_does_not_log_values(caplog):
    with caplog.at_level(logging.WARNING, logger="vector_scraper"):
        BaseFetcher(proxy="http://u:LeakyPass@h:1")
    assert "deprecated" in caplog.text
    assert "LeakyPass" not in caplog.text
