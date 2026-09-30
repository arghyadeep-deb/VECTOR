"""Regression test for a real, verified bug found during the 2026-09-30 Phase 3
codebase audit: districts/communications/email_agent.py::EmailAgent.run()
read every argument (folder/limit/page/email_id/subject/body/...) straight
off `task` instead of `task["params"]`.

The real governor dispatch shape (core/city/governor.py dispatch() ->
`await agent.run(task)`) is `task = {"type": ..., "params": {...}}` -- so
every real dispatch to this agent silently ignored the caller's real
arguments and fell back to hardcoded defaults. Verified live before fixing:
    agent.run({"type": "list", "params": {"folder": "sent", "limit": 5,
                                            "page": 2}})
    -> called list_emails("inbox", 20, 1), the defaults, not "sent"/5/2.

Fixed by flattening params into task once at the top of run() (params
values win on overlap) rather than editing each of the many individual
.get() calls across ~15 task-type branches -- less error-prone and keeps
every flat-shape caller/test (task.get("params") is {} for those) working
unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.communications.email_agent import EmailAgent


@pytest.mark.asyncio
async def test_list_reads_folder_limit_page_from_nested_params():
    agent = EmailAgent()
    captured = {}

    def fake_list_emails(folder, limit, page):
        captured["folder"] = folder
        captured["limit"] = limit
        captured["page"] = page
        return []

    agent.list_emails = fake_list_emails
    await agent.run({"type": "list", "params": {"folder": "sent", "limit": 5, "page": 2}})
    assert captured == {"folder": "sent", "limit": 5, "page": 2}


@pytest.mark.asyncio
async def test_get_reads_email_id_from_nested_params():
    agent = EmailAgent()
    captured = {}

    def fake_get_email(email_id):
        captured["email_id"] = email_id
        return {"id": email_id}

    agent.get_email = fake_get_email
    result = await agent.run({"type": "get", "params": {"email_id": "msg-123"}})
    assert captured == {"email_id": "msg-123"}
    assert result["email"]["id"] == "msg-123"


@pytest.mark.asyncio
async def test_search_reads_query_and_folder_from_nested_params():
    agent = EmailAgent()
    captured = {}

    def fake_search_emails(query, folder):
        captured["query"] = query
        captured["folder"] = folder
        return []

    agent.search_emails = fake_search_emails
    await agent.run({"type": "search", "params": {"query": "invoice", "folder": "archive"}})
    assert captured == {"query": "invoice", "folder": "archive"}


@pytest.mark.asyncio
async def test_flat_legacy_shape_still_works_for_backward_compat():
    agent = EmailAgent()
    captured = {}

    def fake_list_emails(folder, limit, page):
        captured["folder"] = folder
        captured["limit"] = limit
        captured["page"] = page
        return []

    agent.list_emails = fake_list_emails
    await agent.run({"type": "list", "folder": "drafts", "limit": 3, "page": 1})
    assert captured == {"folder": "drafts", "limit": 3, "page": 1}


@pytest.mark.asyncio
async def test_no_params_key_defaults_unchanged():
    agent = EmailAgent()
    captured = {}

    def fake_list_emails(folder, limit, page):
        captured["folder"] = folder
        captured["limit"] = limit
        captured["page"] = page
        return []

    agent.list_emails = fake_list_emails
    await agent.run({"type": "list"})
    assert captured == {"folder": "inbox", "limit": 20, "page": 1}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
