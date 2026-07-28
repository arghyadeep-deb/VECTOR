"""Outward-publish gate: content_scheduler.run_pending must not publish without approval.

Security fix 2026-06-21 (audit finding): this cron path called publisher.publish_all
(Dev.to/Hashnode/Medium) with zero gateway reference — the content Hand gates, this
scheduler did not. Now each publish is RED-gated and fails CLOSED.

Security fix 2026-07-23 (task #92, per-district real tool-execution audit):
districts/content/uploader.py's upload_to_youtube/instagram/tiktok/twitter had
the SAME class of gap as content_scheduler had before its 2026-06-21 fix above —
but Uploader is a DIFFERENT class (real social uploads, not the blog publisher),
so that earlier fix never covered it. Both Governor.dispatch() -> Uploader.run()
(direct district dispatch) and video_pipeline.py's create_and_upload() called
these methods with zero PermissionGateway reference at all — confirmed via code
read that a real upload_instagram/upload_youtube task could execute with no
owner approval, despite content_publish being explicitly RED-tiered in
core/config.py for exactly this ("owner approval ALWAYS"). Now gated the same
way, fails CLOSED.
"""
import asyncio
import tempfile
import types
from pathlib import Path

import core.loop.permission_gateway as pg
from districts.content.content_scheduler import ContentScheduler
from districts.content.uploader import Uploader


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


# ── Uploader (YouTube/Instagram/TikTok/Twitter) — task #92 fix ────────────

def _tmp_video() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    f.write(b"not a real video, just needs to exist")
    f.close()
    return f.name


def test_uploader_youtube_blocked_without_approval(monkeypatch):
    monkeypatch.setattr(pg, "PermissionGateway", lambda: _GW(False))
    up = Uploader()
    video = _tmp_video()
    try:
        result = asyncio.run(up.upload_to_youtube(video, "Test", "desc", []))
    finally:
        Path(video).unlink(missing_ok=True)
    assert result["status"] == "blocked", f"unapproved YouTube upload should be blocked, got: {result}"


def test_uploader_youtube_proceeds_with_approval(monkeypatch):
    # No real Google credentials configured in the test environment, so an
    # approved call still falls through to _simulate_upload — this only
    # proves the gate itself doesn't block a legitimately approved publish.
    monkeypatch.setattr(pg, "PermissionGateway", lambda: _GW(True))
    up = Uploader()
    video = _tmp_video()
    try:
        result = asyncio.run(up.upload_to_youtube(video, "Test", "desc", []))
    finally:
        Path(video).unlink(missing_ok=True)
    assert result["status"] != "blocked", f"approved YouTube upload was blocked: {result}"


def test_uploader_instagram_blocked_without_approval(monkeypatch):
    monkeypatch.setattr(pg, "PermissionGateway", lambda: _GW(False))
    up = Uploader()
    video = _tmp_video()
    try:
        result = asyncio.run(up.upload_to_instagram(video, "caption", []))
    finally:
        Path(video).unlink(missing_ok=True)
    assert result["status"] == "blocked", f"unapproved Instagram upload should be blocked, got: {result}"


def test_uploader_instagram_proceeds_with_approval(monkeypatch):
    monkeypatch.setattr(pg, "PermissionGateway", lambda: _GW(True))
    up = Uploader()
    video = _tmp_video()
    try:
        result = asyncio.run(up.upload_to_instagram(video, "caption", []))
    finally:
        Path(video).unlink(missing_ok=True)
    assert result["status"] != "blocked", f"approved Instagram upload was blocked: {result}"


def test_uploader_gate_not_reached_when_dry_run(monkeypatch):
    # TikTok/Twitter check upload_dry_run BEFORE the gate (existing 2026-07
    # behavior — real posting there is opt-in). Confirms the new gate doesn't
    # change that default: with no token configured, dry-run short-circuits
    # to a simulated upload without ever calling the gateway.
    calls = []
    monkeypatch.setattr(pg, "PermissionGateway", lambda: calls.append(1) or _GW(False))
    up = Uploader()
    video = _tmp_video()
    try:
        result = asyncio.run(up.upload_to_tiktok(video, "caption"))
    finally:
        Path(video).unlink(missing_ok=True)
    assert result["status"] == "simulated" and result.get("simulated") is True
    assert not calls, "gateway should not be consulted when dry-run short-circuits first"
