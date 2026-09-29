"""Real-execution tests for SlackArchaeologist (chief_of_staff district).

Relocated from tests/test_security_specialists.py (2026-09-29): SELF_DEV_AGENT_SPEC.md's own
district map places slack-archaeologist under chief_of_staff, not security -- a placement error
found and corrected on re-reading the spec's own map, not a new decision (see the manifest
comment and districts/chief_of_staff/slack_archaeologist.py's module docstring for the full
reasoning).
"""
from __future__ import annotations

import pytest

from core.city.agent_base import AgentBase
from core.city.declarative_manifest import ManifestLoader
from core.city.governor import DISTRICT_TASK_MAP
from core.config import CONFIG
from districts.chief_of_staff.slack_archaeologist import SlackArchaeologist


def test_manifest_tier_and_route_are_exact():
    definitions = ManifestLoader().load()
    chief_of_staff = {e["name"]: e for e in definitions if e["district"] == "chief_of_staff"}
    entry = chief_of_staff["slack_archaeologist"]
    assert entry["class"].endswith(".SlackArchaeologist")
    instance = SlackArchaeologist()
    assert isinstance(instance, AgentBase)
    assert instance.district == "chief_of_staff"
    assert entry["capabilities"] == instance.capabilities
    for action in instance.capabilities:
        assert DISTRICT_TASK_MAP[action] == "chief_of_staff"
        assert action in CONFIG["permission"]["green"]
        assert action not in CONFIG["permission"]["yellow"]
        assert action not in CONFIG["permission"]["red"]


@pytest.mark.asyncio
async def test_brief_reports_missing_and_present_evidence():
    agent = SlackArchaeologist()
    missing = await agent.run({"type": "slack_archaeology_brief", "evidence": {}})
    assert missing["report"]["status"] == "needs_human"
    assert set(missing["report"]["missing_evidence"]) == {"channel_or_thread_ref", "messages"}

    complete = await agent.run(
        {
            "type": "slack_archaeology_brief",
            "evidence": {"channel_or_thread_ref": "C123", "messages": [{"id": "a", "author": "x", "timestamp": "2026-09-29T00:00:00Z"}]},
        }
    )
    assert complete["report"]["status"] == "ready"


@pytest.mark.asyncio
async def test_slack_archaeologist_catches_every_real_defect_and_orders_the_timeline():
    agent = SlackArchaeologist()
    messages = [
        {"id": "m1", "author": "alice", "timestamp": "2026-09-29T10:00:00Z", "text": "incident started"},
        {"id": "m2", "author": "bob", "timestamp": "2026-09-29T09:59:00Z", "text": "earlier reply", "thread_id": "m1"},
        {"id": "m3", "author": "", "timestamp": "2026-09-29T10:01:00Z", "text": "no author"},
        {"id": "m1", "author": "dup", "timestamp": "2026-09-29T10:02:00Z", "text": "dup id"},
        {"id": "m4", "author": "carol", "timestamp": "bad-ts", "text": "bad ts"},
        {"id": "m5", "author": "dave", "timestamp": "2026-09-29T10:03:00Z", "text": "dangling", "thread_id": "ghost"},
    ]
    result = await agent.run(
        {"type": "slack_archaeology_check", "evidence": {"channel_or_thread_ref": "C123", "messages": messages}}
    )
    report = result["report"]
    assert report["status"] == "needs_human"
    failed = {c["name"] for c in report["checks"] if not c["passed"]}
    assert failed == {
        "no_duplicate_message_ids",
        "every_message_has_author_and_timestamp",
        "every_timestamp_parses",
        "no_dangling_thread_references",
    }
    assert report["duplicate_ids"] == ["m1"]
    assert report["dangling_thread_references"] == ["m5"]

    clean = await agent.run(
        {
            "type": "slack_archaeology_check",
            "evidence": {
                "channel_or_thread_ref": "C123",
                "messages": [
                    {"id": "a", "author": "alice", "timestamp": "2026-09-29T10:00:00Z", "text": "second"},
                    {"id": "b", "author": "bob", "timestamp": "2026-09-29T09:59:00Z", "text": "first", "thread_id": "a"},
                ],
            },
        }
    )
    assert clean["report"]["status"] == "passed"
    assert [t["id"] for t in clean["report"]["timeline"]] == ["b", "a"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
