"""HUD fixes found while recording the reels (2026-09-25). Static contract checks on the frontend sources.

1. VECTOR.closeWidget('city3d') silently did nothing: the 3D city builds its own wrapper that widgets.js's
   `live` registry never sees. closeWidget must hand unknown ids to the widget that owns them.
2. Opening a tall/partly off-screen widget called w.focus(), which scrolled the whole HUD stage upward
   (the grid was found shifted by 448px). Focus must not scroll.
3. `?cinema=1` mode: widgets are enlarged and centred (for screen recordings); floating drift is stopped.
"""
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
WIDGETS = (FRONTEND / "js" / "widgets.js").read_text(encoding="utf-8")
CITY = (FRONTEND / "js" / "city3d.js").read_text(encoding="utf-8")
HTML = (FRONTEND / "VECTOR.html").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    start = src.index(f"function {name}")
    return src[start:start + 1600]


def test_close_widget_hands_unknown_ids_to_their_owner():
    assert "widget:close-external" in _fn(WIDGETS, "closeWidget")


def test_city3d_closes_itself_on_that_event():
    assert "widget:close-external" in CITY and "closeCity()" in CITY.split("widget:close-external", 1)[1][:300]


def test_open_widget_focus_does_not_scroll_the_stage():
    body = _fn(WIDGETS, "openWidget")
    assert "w.focus()" not in body and "preventScroll" in body


def test_city3d_focus_does_not_scroll_the_stage():
    assert "wrap.focus()" not in CITY and "preventScroll" in CITY


def test_cinema_mode_is_switched_on_by_the_query_string():
    assert "cinema" in HTML and "classList.add('cinema')" in HTML


def test_cinema_mode_enlarges_and_centres_widgets():
    assert "function cinemaPlace" in WIDGETS
    body = _fn(WIDGETS, "cinemaPlace")
    assert "zoom" in body and "animation" in body
    assert "V.cinemaPlace" in WIDGETS and "cinemaPlace" in _fn(WIDGETS, "openWidget")
    assert "cinemaPlace" in CITY
