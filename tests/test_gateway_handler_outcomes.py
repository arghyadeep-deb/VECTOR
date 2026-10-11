"""Regression tests for explicit Gateway handler outcomes."""

from __future__ import annotations

import asyncio
import pytest


def _run_action(action_type: str, params: dict):
    from core.loop.permission_gateway import Action, PermissionGateway

    gateway = PermissionGateway()
    return asyncio.run(gateway._execute_action(Action(action_type, params, "test")))


def test_unconfigured_overwrite_note_is_not_reported_as_success(monkeypatch):
    from core.config import CONFIG

    monkeypatch.setitem(CONFIG, "obsidian_vault_path", "")

    result = _run_action(
        "overwrite_note_personal",
        {"note": "audit-noop", "content": ""},
    )

    assert result["status"] == "needs_config"
    assert "not written" in result["error"]


def test_failed_attendance_scrape_is_unavailable(monkeypatch):
    from districts.time_calendar.kiit_scraper import KIITScraper

    async def fail_fetch(self):
        raise RuntimeError("calendar backend offline")

    monkeypatch.setattr(KIITScraper, "scrape_all", fail_fetch)

    result = _run_action("check_attendance", {})

    assert result["status"] == "unavailable"
    assert result["checked"] is False
    assert "calendar backend offline" in result["error"]


def test_failed_web_search_is_unavailable(monkeypatch):
    import sys
    import types

    class FailingDDGS:
        def text(self, query, max_results):
            raise RuntimeError("search backend offline")

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FailingDDGS))

    result = _run_action("search_web", {"query": "VECTOR"})

    assert result["status"] == "unavailable"
    assert result["results"] == []
    assert "search backend offline" in result["error"]


def test_local_calendar_fallback_is_incomplete_not_executed(monkeypatch):
    result = _run_action(
        "create_calendar_event",
        {"title": "Review", "time": "2026-10-10T12:00:00"},
    )

    assert result["status"] == "incomplete"
    assert result["local_only"] is True


def test_email_draft_is_incomplete_not_sent(monkeypatch):
    import sys
    import types

    class FakeEmailAgent:
        def draft_email(self, **kwargs):
            return {"draft_id": "draft-1"}

    monkeypatch.setitem(
        sys.modules,
        "districts.communications.email_agent",
        types.SimpleNamespace(EmailAgent=FakeEmailAgent),
    )

    result = _run_action(
        "send_email",
        {"to": "owner@example.com", "subject": "Status", "body": "Draft"},
    )

    assert result["status"] == "incomplete"
    assert result["drafted_only"] is True
    assert result["draft_id"] == "draft-1"


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "unavailable"},
        {"status": "needs_config"},
        {"status": "incomplete"},
    ],
)
def test_non_completion_outcomes_are_terminal(payload):
    from core.runtime.executor import result_failure_reason

    assert result_failure_reason(payload) is not None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
