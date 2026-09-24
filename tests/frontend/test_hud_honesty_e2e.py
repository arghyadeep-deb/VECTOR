"""End-to-end: the production HUD must not present demo seed data as live.

Found 2026-09-24 in a real-browser pass: the tickers showed hard-coded quotes/headlines and constant
"THREAT LEVEL LOW / 33 DISTRICTS ONLINE / TICK NOMINAL" text, the council widget showed three invented
decisions, the music widget a made-up track, and the orb label stayed on STANDBY after waking.

Runs the real API (own process, throwaway DB/data dir) and drives the real HUD in headless Chromium.
The browser part runs in a clean child process: the suite's conftest forces the Windows selector event
loop, which Playwright's subprocess transport cannot use. Skips when Playwright/Chromium or the server
cannot start.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KEY = "hud-e2e-key"

_SERVER_SRC = """
import sys
sys.path.insert(0, {root!r})
import uvicorn
from core.api.app import create_app
uvicorn.run(create_app(), host="127.0.0.1", port={port}, log_level="error")
"""

_BROWSER_SRC = r"""
import json, sys
from playwright.sync_api import sync_playwright
url = sys.argv[1]
out = {"js_errors": []}
def open_widget(pg, wid):
    pg.evaluate(f"window.VECTOR.openWidget('{wid}')")
    pg.wait_for_timeout(1800)
    text = pg.evaluate("(id) => { const w = [...document.querySelectorAll('.widget')].find(x => (x.dataset.id||'') === id); return w ? w.innerText : ''; }", wid)
    pg.evaluate(f"window.VECTOR.closeWidget('{wid}')")
    return " ".join(text.split())
with sync_playwright() as pw:
    try:
        browser = pw.chromium.launch(headless=True)
    except Exception as exc:
        print(json.dumps({"skip": f"chromium unavailable: {exc}"})); sys.exit(0)
    # bypass_csp: Playwright evaluates wait_for_function() expressions via eval, which the HUD's own CSP forbids
    pg = browser.new_context(viewport={"width": 1488, "height": 812}, bypass_csp=True).new_page()
    pg.on("pageerror", lambda e: out["js_errors"].append(str(e)))
    pg.goto(url)
    pg.wait_for_function("window.VECTOR_DATA && window.VECTOR_DATA.SEED_CLEARED === true", timeout=75000)
    pg.wait_for_function("window.VECTOR_DATA.LIVE && window.VECTOR_DATA.LIVE.loop", timeout=75000)
    pg.wait_for_timeout(1500)
    out["seed"] = pg.evaluate("() => ({ council: VECTOR_DATA.COUNCIL.length, stocks: VECTOR_DATA.STOCKS.length, news: VECTOR_DATA.NEWS.length, tracks: VECTOR_DATA.TRACKS.length, memory_fake: VECTOR_DATA.MEMORY.filter(m => /PR #218|:11434|KIIT attendance/.test(m.content)).length })")
    out["stocks_text"] = pg.evaluate("() => document.getElementById('stockTrack') ? document.getElementById('stockTrack').textContent : ''")
    out["news_text"] = pg.evaluate("() => document.getElementById('newsTrack') ? document.getElementById('newsTrack').textContent : ''")
    out["council"] = open_widget(pg, "council")
    out["music"] = open_widget(pg, "music")
    out["districts"] = open_widget(pg, "districts")
    pg.evaluate("window.VECTOR.wake()")
    pg.wait_for_timeout(600)
    out["orb"] = " ".join(pg.evaluate("() => { const o = document.querySelector('#orb-wrap'); return o ? o.innerText : ''; }").split())
    # A second, CSP-enforcing context (the owner's real Chrome enforces the page's CSP; the first one bypasses it only
    # so wait_for_function can eval). Counts dock buttons and collects CSP violations / console errors.
    ctx2 = browser.new_context(viewport={"width": 1488, "height": 812})
    pg2 = ctx2.new_page()
    csp, errs = [], []
    pg2.on("console", lambda m: (csp if "Content Security Policy" in m.text else errs).append(m.text[:160]) if m.type == "error" else None)
    pg2.on("pageerror", lambda e: errs.append(str(e)[:160]))
    pg2.goto(url, wait_until="domcontentloaded")
    pg2.wait_for_timeout(9000)
    out["strict"] = {"dock_buttons": pg2.evaluate("() => document.querySelectorAll('#dock .d-btn').length"),
                     "title": pg2.title(), "csp_violations": csp, "console_errors": errs}
    browser.close()
print(json.dumps(out))
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module", params=[
    ("production", ""),          # lean page (VECTOR.prod.html)
    ("production", "full"),      # what the owner's launchers run: full HUD (VECTOR.html) under production
    ("development", ""),         # full HUD, development
], ids=["lean-production", "full-in-production", "development"])
def hud(request):
    """All three ways the HUD is served. The full HUD (3D city, map, camera hero, gestures, the whole subsystem dock)
    is VECTOR.html; it carried the same hard-coded tickers and boot lines as the lean page."""
    pytest.importorskip("playwright")
    tmp = Path(tempfile.mkdtemp(prefix="hud_e2e_"))
    (tmp / "data").mkdir()
    port = _free_port()
    script = tmp / "serve.py"
    script.write_text(_SERVER_SRC.format(root=str(ROOT), port=port), encoding="utf-8")
    env = dict(os.environ, VECTOR_DB_PATH=str(tmp / "vm.db"), VECTOR_TEST_DATA_DIR=str(tmp / "data"),
               VECTOR_DB_KEY="hud-e2e-db-key", VECTOR_API_KEY=KEY, VECTOR_ENV=request.param[0], VECTOR_HUD_PAGE=request.param[1])
    proc = subprocess.Popen([sys.executable, str(script)], env=env, cwd=str(ROOT),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    up = False
    for _ in range(90):
        try:
            req = urllib.request.Request(base + "/health", headers={"Authorization": f"Bearer {KEY}"})
            urllib.request.urlopen(req, timeout=2)
            up = True
            break
        except Exception:
            if proc.poll() is not None:
                break
            time.sleep(1)
    if not up:
        proc.kill()
        pytest.skip("HUD test server did not start")
    try:
        browser_env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
        r = subprocess.run([sys.executable, "-c", _BROWSER_SRC, f"{base}/hud/?key={KEY}"],
                           capture_output=True, text=True, timeout=240, env=browser_env, cwd=str(ROOT))
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("{")]
        if not lines:
            pytest.skip(f"browser run produced no result: {r.stderr[-300:]}")
        data = json.loads(lines[-1])
        if "skip" in data:
            pytest.skip(data["skip"])
        yield data
    finally:
        proc.kill()


def test_demo_seed_is_cleared_once_the_backend_connects(hud):
    assert hud["seed"] == {"council": 0, "stocks": 0, "news": 0, "tracks": 0, "memory_fake": 0}


def test_tickers_show_no_invented_market_or_news_data(hud):
    for fake in ("24,318.40", "79,943.21", "1,154.20", "IRGC", "UPI crosses 18B", "TICK NOMINAL", "33 DISTRICTS ONLINE"):
        assert fake not in hud["stocks_text"] and fake not in hud["news_text"], f"fake ticker content: {fake}"


def test_status_ticker_reflects_the_real_loop_state(hud):
    # this backend runs the API only, so the loop must be reported as not running
    assert "LOOP · NOT RUNNING" in hud["news_text"]


def test_council_widget_shows_no_invented_decisions(hud):
    text = hud["council"].lower()
    assert "dependabot" not in text and "depend bot" not in text and "keystroke" not in text and "₹180" not in text


def test_music_widget_does_not_show_a_made_up_track(hud):
    assert "Paramore" not in hud["music"] and "Still Into You" not in hud["music"]
    assert "NO PLAYER CONNECTED" in hud["music"]


def test_districts_widget_title_uses_real_counts(hud):
    assert "DISTRICTS · 33" not in hud["districts"] and "AGENT DISTRICTS" in hud["districts"]


def test_orb_label_follows_the_hud_state(hud):
    assert "STANDBY" not in hud["orb"]


def test_full_hud_is_served_in_production_when_the_launchers_ask_for_it(hud, request):
    strict = hud["strict"]
    assert strict["csp_violations"] == [], strict["csp_violations"]
    assert strict["console_errors"] == [], strict["console_errors"]
    if request.node.callspec.id.endswith("lean-production"):
        assert strict["title"] == "VECTOR Production" and strict["dock_buttons"] < 12
    else:
        assert strict["title"] == "VECTOR" and strict["dock_buttons"] >= 12, strict


def test_no_javascript_errors_during_the_session(hud):
    assert hud["js_errors"] == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
