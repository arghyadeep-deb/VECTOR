"""Regression test for a real, verified bug found during the 2026-09-30 Phase 3
codebase audit: districts/security/data_redactor.py::DataRedactor.run() read
text/messages/cloud_mode straight off `task` instead of `task["params"]`.

The real governor dispatch shape (core/city/governor.py dispatch() ->
`await agent.run(task)`, task = {"type": ..., "params": {...}}) always put
the caller's real text/messages under `params`, so every real dispatch to
this agent silently redacted/scanned an empty string and reported
`status: "ok"` with zero findings -- even when the caller supplied a real
secret. Verified live before fixing:
    agent.run({"type": "redact_text", "params": {"text": "<real API key>"}})
    -> {"redacted": "", "findings": [], "changed": False}

This is security/privacy-relevant: DataRedactor exists specifically to
enforce RULE 11 (local-first privacy, no PII/secrets to cloud providers) --
a silent no-op here means a real secret would sail through unredacted the
one time this agent was actually invoked as the governor invokes every
other agent.

DataRedactor has zero manifest DISTRICT_TASK_MAP exact routes for 3 of its 4
capabilities (redact_text/redact_messages/scan -- only cloud_safety has one),
which is a separate, lower-severity finding (not this file's concern) --
this file only tests the dispatch-shape bug's fix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.security.data_redactor import DataRedactor


@pytest.mark.asyncio
async def test_redact_text_reads_real_governor_dispatch_shape():
    """The exact shape governor.py's dispatch() sends: {"type": ..., "params": {...}}."""
    agent = DataRedactor()
    result = await agent.run({
        "type": "redact_text",
        "params": {"text": "My API key is sk-ant-api03-abcdef1234567890abcdef"},
    })
    assert result["status"] == "ok"
    assert result["changed"] is True
    assert "[ANTHROPIC_KEY_REDACTED]" in result["redacted"]
    assert result["findings"]


@pytest.mark.asyncio
async def test_redact_messages_reads_real_governor_dispatch_shape():
    agent = DataRedactor()
    result = await agent.run({
        "type": "redact_messages",
        "params": {"messages": [{"role": "user", "content": "password=hunter2"}]},
    })
    assert result["status"] == "ok"
    assert result["redacted_count"] == 1
    assert result["messages"][0]["content"] != "password=hunter2"


@pytest.mark.asyncio
async def test_cloud_safety_reads_real_governor_dispatch_shape():
    agent = DataRedactor()
    result = await agent.run({
        "type": "cloud_safety",
        "params": {"messages": [{"role": "user", "content": "my card is 4111 1111 1111 1111"}]},
    })
    assert result["status"] == "ok"
    assert result["safety"]["safe"] is False
    assert result["safety"]["action"] == "redact_first"


@pytest.mark.asyncio
async def test_scan_reads_real_governor_dispatch_shape():
    agent = DataRedactor()
    result = await agent.run({
        "type": "scan",
        "params": {"text": "reach me at real.person@example.com"},
    })
    assert result["status"] == "ok"
    assert result["scan"]["has_secrets"] is True
    assert result["scan"]["count"] == 1


@pytest.mark.asyncio
async def test_flat_legacy_shape_still_works_for_backward_compat():
    """The file's own __main__ smoke test uses this flat (no "params" key)
    shape -- must keep working exactly as documented in the fix comment."""
    agent = DataRedactor()
    result = await agent.run({"type": "scan", "text": "contact me at test@example.com"})
    assert result["status"] == "ok"
    assert result["scan"]["has_secrets"] is True


@pytest.mark.asyncio
async def test_no_text_and_no_params_scans_empty_string_not_a_crash():
    """Honest edge case: neither params nor a flat text key -- must degrade
    to an empty-string scan, not raise."""
    agent = DataRedactor()
    result = await agent.run({"type": "scan"})
    assert result["status"] == "ok"
    assert result["scan"]["has_secrets"] is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
