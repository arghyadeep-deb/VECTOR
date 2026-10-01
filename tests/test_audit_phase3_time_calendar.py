"""Audit phase 3 — districts/time_calendar regression tests (no network/browser)."""
from __future__ import annotations

import asyncio
import datetime as dt
import time

from districts.time_calendar.booking import BookingRequest
from districts.time_calendar.deadline_manager import DeadlineManager
from districts.time_calendar.kiit_scraper import KIITScraper


def _iso(d: dt.datetime) -> str:
    return d.isoformat(timespec="seconds")


# ---------------------------------------------------------------- booking
def test_booking_created_at_is_per_instance():
    a = BookingRequest("1", "x", dt.datetime.now(dt.timezone.utc), dt.datetime.now(dt.timezone.utc), "t")
    time.sleep(0.01)
    b = BookingRequest("2", "x", dt.datetime.now(dt.timezone.utc), dt.datetime.now(dt.timezone.utc), "t")
    assert b.created_at > a.created_at


# ---------------------------------------------------------------- deadline manager
def _dm_with_events(events):
    dm = DeadlineManager()
    dm.get_upcoming_events = lambda hours=24: events  # type: ignore
    dm.last_fetch_error = ""
    return dm


def test_is_class_soon_handles_offset_timestamps():
    dm = DeadlineManager()
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    start = dt.datetime.now(ist) + dt.timedelta(minutes=10)
    dm.get_upcoming_events = lambda hours=1: [  # type: ignore
        {"title": "Physics Lecture", "start": _iso(start), "end": _iso(start + dt.timedelta(hours=1))}
    ]
    assert dm.is_class_soon(20) is True


def test_is_class_soon_handles_z_timestamps():
    dm = DeadlineManager()
    start = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)
    dm.get_upcoming_events = lambda hours=1: [  # type: ignore
        {"title": "Lab", "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": ""}
    ]
    assert dm.is_class_soon(20) is True


def test_free_blocks_sub_hour_event_marks_slot_busy():
    local = dt.datetime.now().astimezone()
    # Pick a slot hour later today (or skip logic by using now hour+0 window).
    h = local.hour
    start = local.replace(minute=0, second=0, microsecond=0)
    ev = {"title": "Quick sync", "start": _iso(start), "end": _iso(start + dt.timedelta(minutes=30))}
    dm = _dm_with_events([ev])
    dm._hour_to_window = lambda hour: "peak"  # type: ignore  # time-of-day independent
    free = dm._get_free_blocks_today()
    assert not any(f.startswith(f"{h:02d}:00") for f in free)


def test_free_blocks_unavailable_calendar_not_reported_free():
    dm = DeadlineManager()
    dm._service = None
    dm._get_service = lambda: None  # type: ignore
    assert dm._get_free_blocks_today() == []
    ctx = dm.get_schedule_context()
    assert ctx["calendar_available"] is False
    assert ctx["calendar_error"]


def test_run_reports_error_when_calendar_unreadable():
    dm = DeadlineManager()
    dm._get_service = lambda: None  # type: ignore
    res = asyncio.run(dm.run({"params": {"hours": 6}}))
    assert res["status"] == "error"
    assert res["error"]


def test_run_tolerates_null_or_bad_params():
    dm = _dm_with_events([])
    dm.get_schedule_context = lambda: {}  # type: ignore
    assert asyncio.run(dm.run({"params": None}))["status"] == "ok"
    assert asyncio.run(dm.run({"params": {"hours": "abc"}}))["status"] == "ok"


# ---------------------------------------------------------------- KIIT scraper
class _FakePage:
    def __init__(self, password_field_after_login: bool, rows=None):
        self._pw = password_field_after_login
        self._rows = rows or []

    async def goto(self, *a, **k): ...
    async def wait_for_selector(self, *a, **k): ...
    async def fill(self, *a, **k): ...
    async def click(self, *a, **k): ...
    async def wait_for_load_state(self, *a, **k): ...

    async def query_selector(self, sel):
        return object() if (self._pw and "password" in sel) else None

    async def query_selector_all(self, sel):
        return self._rows


class _Cell:
    def __init__(self, t): self.t = t
    async def inner_text(self): return self.t


class _Row:
    def __init__(self, texts): self.cells = [_Cell(t) for t in texts]
    async def query_selector_all(self, sel): return self.cells


def _scraper(page):
    s = KIITScraper()
    s._credentials = {"username": "u", "password": "p"}

    async def _gb():
        return page
    s._get_browser = _gb  # type: ignore
    return s


def test_login_rejected_is_not_reported_as_success():
    s = _scraper(_FakePage(password_field_after_login=True))
    assert asyncio.run(s._login(s._page or _FakePage(True))) is False


def test_failed_login_surfaces_error_not_clean_run():
    s = _scraper(_FakePage(password_field_after_login=True))
    res = asyncio.run(s.run({"type": "check_attendance"}))
    assert res["status"] == "error"
    assert res["alerts"] == []


def test_scrape_all_includes_errors_on_failed_login():
    s = _scraper(_FakePage(password_field_after_login=True))
    res = asyncio.run(s.scrape_all())
    assert res["errors"].get("attendance") == "login_failed"
    assert res["errors"].get("schedule") == "login_failed"


def test_unparseable_attendance_row_not_fabricated_as_zero_percent():
    rows = [_Row(["h", "h", "h"]), _Row(["Maths", "n/a", "x"]), _Row(["Physics", "30", "40"])]
    s = _scraper(_FakePage(False, rows))
    att = asyncio.run(s.get_attendance())
    assert [a["subject"] for a in att] == ["Physics"]
    assert "Maths" not in s._at_risk(att)
    assert "attendance" in s.last_errors  # partial parse is flagged


def test_zero_total_subject_not_flagged_at_risk():
    s = KIITScraper()
    assert s._at_risk([{"subject": "New", "present": 0, "total": 0, "percent": 0.0}]) == []
    assert s._at_risk([{"subject": "Low", "present": 1, "total": 4, "percent": 25.0}]) == ["Low"]


def test_good_scrape_status_ok():
    rows = [_Row(["h", "h", "h"]), _Row(["Physics", "30", "40"])]
    s = _scraper(_FakePage(False, rows))
    res = asyncio.run(s.run({"type": "check_attendance"}))
    assert res["status"] == "ok"
