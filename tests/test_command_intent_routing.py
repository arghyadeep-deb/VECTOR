"""Regression tests for _detect_intent_action (the command-bar / API intent router).

Found by dogfooding on 2026-07-17: the router had no widget vocabulary, so
  "open the music widget"  -> launch_app  (launched Spotify!)
  "close the music widget" -> play_music  (the exact OPPOSITE of the request)
  "show me London on the map" -> respond  (recited coordinates, never opened the map)

The voice path uses an LLM multi-intent classifier; this HTTP path uses keyword
matching, so it needs its own safety net.

Run: python tests/test_command_intent_routing.py     (or via pytest)
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers.commands import _WIDGET_ALIASES, _WIDGET_IDS, _detect_intent_action

_WIDGETS_JS = Path(__file__).parent.parent / "frontend" / "js" / "widgets.js"

# (text, expected action_type)
CASES = [
    # ── the three dogfood bugs ────────────────────────────────────────────
    ("open the music widget", "widget_open"),
    ("close the music widget", "widget_close"),
    ("show me London on the map", "widget_show_location"),
    # ── widget vocabulary ─────────────────────────────────────────────────
    ("where is Paris", "widget_show_location"),
    ("open the goals panel", "widget_open"),
    ("hide the camera widget", "widget_close"),
    ("close all widgets", "widget_close"),
    ("bring up the finance widget", "widget_open"),
    ("open the camera widget", "widget_open"),      # alias -> webcam
    # A widget that does not exist must NOT be routed as a widget action —
    # openWidget() would console.warn and do nothing. Answering is correct.
    ("bring up the news widget", "respond"),
    # ── music transport vs launching the app ──────────────────────────────
    ("pause the music", "music_pause"),
    ("next song", "music_next"),
    ("previous track", "music_prev"),
    # ── regressions: must NOT change ──────────────────────────────────────
    ("open spotify", "launch_app"),
    ("open notepad", "launch_app"),
    ("play music", "launch_app"),          # owner's established behavior
    ("take a screenshot", "take_screenshot"),
    ("search the web for rust", "search_web"),
    ("what is the capital of France", "respond"),
    ("what are my goals", "respond"),
]


def _route(text: str) -> str:
    return (_detect_intent_action(text) or {}).get("action_type")


def test_intent_routes():
    wrong = [(t, e, _route(t)) for t, e in CASES if _route(t) != e]
    assert not wrong, "misrouted commands: " + "; ".join(
        f"{t!r} -> {g} (expected {e})" for t, e, g in wrong)


def test_widget_params_carry_the_target():
    assert _detect_intent_action("open the music widget")["params"]["id"] == "music"
    assert _detect_intent_action("close all widgets")["params"]["id"] == "all"
    assert "london" in _detect_intent_action("show me London on the map")["params"]["query"]
    # alias: there is no 'camera' widget — the real one is 'webcam'
    assert _detect_intent_action("open the camera widget")["params"]["id"] == "webcam"


def test_every_routable_widget_exists_in_the_frontend():
    """The router must never route to a widget the HUD cannot build.

    widgets.js `openWidget` does: `const make = F[id]; if(!make){ console.warn(
    'no widget', id); return; }` — an unknown id silently does NOTHING. An early
    version of this router listed camera/news/schematic/terminal/text/agents,
    none of which exist (2026-07-17 browser dogfood).
    """
    js = _WIDGETS_JS.read_text(encoding="utf-8", errors="ignore")
    real = set(re.findall(r"^\s*F\.([a-z0-9_]+)\s*=\s*function", js, re.M))
    assert real, "could not parse widget ids out of widgets.js"
    unknown = sorted(set(_WIDGET_IDS) - real)
    assert not unknown, f"router lists widgets that do not exist in widgets.js: {unknown}"
    bad_alias = sorted({v for v in _WIDGET_ALIASES.values()} - real)
    assert not bad_alias, f"aliases point at non-existent widgets: {bad_alias}"


def main() -> bool:
    bad = 0
    for text, exp in CASES:
        got = _route(text)
        ok = got == exp
        bad += (not ok)
        print(f"{'ok  ' if ok else 'FAIL'} {text!r:42s} -> {got}"
              f"{'' if ok else f'  (expected {exp})'}")
    print(f"\n{len(CASES) - bad}/{len(CASES)} routes correct")
    return bad == 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = main()
    print("✅ intent routing OK" if ok else "❌ FAILED")
    raise SystemExit(0 if ok else 1)
