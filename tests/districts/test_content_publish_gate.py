"""Outward-publish gate: content_scheduler.run_pending must not publish without approval.

Security fix 2026-06-21 (audit finding): this cron path called publisher.publish_all
(Dev.to/Hashnode/Medium) with zero gateway reference — the content Hand gates, this
scheduler did not. Now each publish is RED-gated and fails CLOSED.
"""
import asyncio
import types

import core.loop.permission_gateway as pg
from districts.content.content_scheduler import ContentScheduler


def _job():
    return types.SimpleNamespace(
        job_id="j1", platform="devto", title="Test Post", payload={"content": "body"}
    )


class _Tracker:
    def __init__(self):
        self.published, self.failed, self.publishing = [], [], []

    def list_pending(self):
        return [_job()]

    def mark_publishing(self, jid):
        self.publishing.append(jid)

    def mark_published(self, jid):
        self.published.append(jid)

    def mark_failed(self, jid, reason):
        self.failed.append((jid, reason))


class _Publisher:
    def __init__(self):
        self.calls = []

    def publish_all(self, title, content, platforms=None):
        self.calls.append((title, platforms))
        return []


class _Result:
    def __init__(self, approved):
        self.approved = approved
        self.reason = "test"


class _GW:
    def __init__(self, approved):
        self._approved = approved

    async def execute(self, action):
        return _Result(self._approved)


def _setup(monkeypatch, approved):
    sched = ContentScheduler()
    tr, pub = _Tracker(), _Publisher()
    monkeypatch.setattr(sched, "_get_tracker", lambda: tr)
    monkeypatch.setattr(sched, "_get_publisher", lambda: pub)
    monkeypatch.setattr(pg, "PermissionGateway", lambda: _GW(approved))
    return sched, tr, pub


def test_unapproved_publish_is_not_sent(monkeypatch):
    sched, tr, pub = _setup(monkeypatch, approved=False)
    asyncio.run(sched.run_pending())
    assert pub.calls == [], "published without owner approval"
    assert tr.failed, "unapproved job not recorded"


def test_approved_publish_proceeds(monkeypatch):
    sched, tr, pub = _setup(monkeypatch, approved=True)
    asyncio.run(sched.run_pending())
    assert pub.calls, "approved publish did not go through"
