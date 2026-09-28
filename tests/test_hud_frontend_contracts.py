"""Static regression checks for HUD bugs found by real-browser dogfooding on
2026-07-17 (Playwright driving the actual HUD via keyboard/mouse — Ctrl+Shift+H
terminal, typed `open <panel>` commands, dock clicks, #cmd-bar-input).

These are cheap, server-less checks (regex/AST over the source) so they run in
CI without booting VECTOR or a browser. Each one locks in a fix found by that
session so a future edit can't silently reopen the same bug.

Run: python tests/test_hud_frontend_contracts.py     (or via pytest)
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TERMINAL_JS = ROOT / "frontend" / "js" / "terminal.js"
WIDGETS_JS = ROOT / "frontend" / "js" / "widgets.js"
MIDDLEWARE_PY = ROOT / "core" / "api" / "middleware.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def _strip_js_line_comments(src: str) -> str:
    """Drop '// ...' comments so a mention inside prose (e.g. this file's own
    "'city3d' intentionally NOT listed" comment) doesn't trip a substring
    check meant to look at real code."""
    return re.sub(r"//[^\n]*", "", src)


# ── terminal.js ───────────────────────────────────────────────────────────────

def test_terminal_advertises_city3d_only_while_the_hud_loads_it():
    """`open city3d` printed "opened city3d" and nothing appeared while the lean production bundle (since removed)
    dropped city3d.js (2026-07-17 dogfood). There is now one HUD, VECTOR.html, which loads city3d.js; the terminal may
    list the widget exactly as long as that page does."""
    js = _read(TERMINAL_JS)
    m = re.search(r"const WIDGETS\s*=\s*\[(.*?)\];", js, re.S)
    assert m, "could not find WIDGETS array in terminal.js"
    code_only = _strip_js_line_comments(m.group(1))
    html = _read(ROOT / "frontend" / "VECTOR.html")
    assert ("'city3d'" in code_only) == ("js/city3d.js" in html), "terminal city3d listing must match what the HUD loads"


def test_terminal_ctrl_shift_h_bubbles_past_the_input_handler():
    """onKey() used to call e.stopPropagation() unconditionally BEFORE
    checking which key was pressed, so once the terminal input had focus
    (i.e. right after typing any command), Ctrl+Shift+H could never reach
    the global toggle listener and the terminal could not be closed via its
    own documented shortcut (2026-07-17: reproduced live via Playwright —
    the terminal visibly stayed open after the shortcut was pressed).
    The fix returns early for Ctrl+Shift+H (and Escape) before the
    unconditional stopPropagation() line."""
    js = _read(TERMINAL_JS)
    fn = re.search(r"function onKey\(e\)\{(.*?)\n  \}", js, re.S)
    assert fn, "could not find onKey() in terminal.js"
    body = fn.group(1)
    ctrl_h_pos = body.find("ctrlKey && e.shiftKey")
    stoppropagation_pos = body.find("e.stopPropagation()")
    assert ctrl_h_pos != -1, "Ctrl+Shift+H check missing from onKey()"
    assert stoppropagation_pos != -1, "stopPropagation() missing from onKey()"
    assert ctrl_h_pos < stoppropagation_pos, (
        "Ctrl+Shift+H check must come BEFORE stopPropagation() so the global "
        "toggle listener still receives the event while the input is focused")


def test_terminal_open_command_verifies_before_claiming_success():
    """openName() used to always print 'opened <n>' regardless of whether
    V.openWidget() actually created a DOM node — a lie whenever the id had
    no factory function (exactly what happened with 'city3d' before it was
    removed from WIDGETS). Must check the DOM before reporting success."""
    js = _read(TERMINAL_JS)
    fn = re.search(r"function openName\(n\)\{(.*?)\n  \}", js, re.S)
    assert fn, "could not find openName() in terminal.js"
    assert "querySelector" in fn.group(1), (
        "openName() must verify the widget actually rendered before "
        "reporting 'opened <n>'")


# ── widgets.js ────────────────────────────────────────────────────────────────

def test_health_sleep_is_not_a_bare_get_readout():
    """/health/sleep is POST-only (core/api/routers/health.py). It used to be
    listed in healthpanel's `reads` override, which bypasses endpointMeta's
    readable filter entirely and renders as a one-click KPI button;
    hydrateReadouts() fires a GET on every KPI the instant the panel opens
    (no click needed) -> guaranteed 405 on every healthpanel open
    (2026-07-17 dogfood: HTTP 405 GET /health/sleep)."""
    js = _read(WIDGETS_JS)
    m = re.search(r"healthpanel:\s*\{[^}]*reads:\s*\[([^\]]*)\]", js)
    assert m, "could not find healthpanel blueprint reads[] in widgets.js"
    assert "/health/sleep" not in m.group(1), (
        "/health/sleep is POST-only and must not be in a bare-GET reads list")


def test_endpoint_meta_health_prefix_does_not_swallow_write_routes():
    """endpointMeta()'s safePrefixes used to include a bare '/health' prefix,
    which (via startsWith) ALSO matched /health/sleep and /health/exercise —
    both POST-only. A prefix match is too broad; the safe GET routes must be
    listed explicitly."""
    js = _read(WIDGETS_JS)
    m = re.search(r"const safePrefixes\s*=\s*\[(.*?)\];", js, re.S)
    assert m, "could not find safePrefixes in widgets.js"
    prefixes = m.group(1)
    assert "'/health'," not in prefixes.replace(" ", ""), (
        "bare '/health' prefix must not be reintroduced — it swallows "
        "POST-only /health/sleep and /health/exercise")
    assert "/health/status" in prefixes, "explicit safe health GET routes must be listed"


def test_research_papers_has_a_default_query_param():
    """GET /research/papers requires `query` (core/api/routers/research.py:
    `async def research_papers(query: str, ...)`). The registry listed it
    bare while its sibling /research/search already carried a default
    (?query=vector) — clicking/auto-loading the bare one guaranteed a 422
    (2026-07-17 dogfood)."""
    js = _read(WIDGETS_JS)
    assert "'/research/papers'" not in js, (
        "/research/papers must not appear without a default query param")
    assert "/research/papers?query=" in js


# ── middleware.py ─────────────────────────────────────────────────────────────

def test_permissions_policy_allows_self_for_mic_and_camera():
    """Permissions-Policy: microphone=(), camera=() has an EMPTY allowlist,
    which blocks the page from requesting mic/camera even from itself, even
    with the browser's native permission prompt granted. That silently broke
    the HUD's own voice input (speech.js/voice_duplex.js) and webcam widget
    in every real browser (2026-07-17 dogfood: 'Permissions policy violation:
    microphone/camera is not allowed in this document' on every attempt).
    Must be (self), not ()."""
    py = _read(MIDDLEWARE_PY)
    m = re.search(r'"Permissions-Policy":\s*"([^"]*)"', py)
    assert m, "could not find Permissions-Policy header in middleware.py"
    policy = m.group(1)
    assert "microphone=(self)" in policy, f"microphone must be (self): {policy!r}"
    assert "camera=(self)" in policy, f"camera must be (self): {policy!r}"
    assert "microphone=()" not in policy and "camera=()" not in policy


def test_csp_allows_blob_media_for_kokoro_playback():
    """audio.js._speakKokoro() plays VECTOR's real voice via
    URL.createObjectURL(wavBlob) + new Audio(blobUrl) -- a `blob:` media
    source. With no media-src directive this fell back to default-src
    'self', which does not cover blob:, so every reply was silently blocked
    by CSP and the HUD fell back to the robotic browser voice the owner
    explicitly banned (2026-07-17 dogfood: 'Loading media from blob:...
    violates CSP directive'; confirmed gone after the fix via isolated
    Playwright repro)."""
    py = _read(MIDDLEWARE_PY)
    m = re.search(r'"Content-Security-Policy"\]\s*=\s*\(\s*(.*?frame-ancestors[^)]*)\)', py, re.S)
    assert m, "could not find CSP header assignment in middleware.py"
    csp = m.group(1)
    assert "media-src" in csp and "blob:" in csp, (
        "CSP must include media-src ... blob: for Kokoro voice playback")


def test_csp_frame_src_allows_loopback_sidecars():
    """Regression guard for the earlier (2026-07-16) frame-src fix — CSP must
    keep allowing local sidecar iframes (comfyui/librechat/openwebui) without
    opening up the public internet."""
    py = _read(MIDDLEWARE_PY)
    m = re.search(r'"Content-Security-Policy"\]\s*=\s*\(\s*(.*?frame-ancestors[^)]*)\)', py, re.S)
    assert m
    csp = m.group(1)
    assert "frame-src" in csp
    assert "127.0.0.1" in csp and "localhost" in csp


def main() -> bool:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t()
            print(f"ok   {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} pass")
    return not failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = main()
    print("✅ HUD frontend contracts OK" if ok else "❌ FAILED")
    raise SystemExit(0 if ok else 1)
