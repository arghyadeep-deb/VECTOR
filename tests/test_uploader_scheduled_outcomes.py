"""Regression tests: execute_scheduled_uploads must record the REAL upload outcome.

Before the fix every non-raising upload was stamped 'executed' and returned, so
errored, permission-blocked and simulated uploads looked like successful
publishes. All upload_to_* methods are monkeypatched on the Uploader instance;
no network, credential, filesystem or gateway access happens here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from districts.content.uploader import Uploader

PAST = "2020-01-01T00:00:00+00:00"
UPLOAD_METHODS = ("upload_to_youtube", "upload_to_instagram", "upload_to_tiktok", "upload_to_twitter")


def _future() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()


def _stub_returning(result):
    async def _stub(*args, **kwargs):
        return result
    return _stub


def _stub_raising(exc):
    async def _stub(*args, **kwargs):
        raise exc
    return _stub


@pytest.fixture
def uploader(monkeypatch):
    """Uploader whose every upload_to_* is replaced so nothing real can run.

    The default stub records the call and returns an error result; tests
    override the platform(s) they exercise.
    """
    up = Uploader()
    up.unstubbed_calls = []

    def _default(name):
        async def _stub(*args, **kwargs):
            up.unstubbed_calls.append(name)
            return {"status": "error", "message": f"{name} not stubbed"}
        return _stub

    for name in UPLOAD_METHODS:
        monkeypatch.setattr(up, name, _default(name))
    return up


def _add(up: Uploader, platform: str = "instagram", when: str = PAST, **metadata) -> dict:
    schedule = {
        "id": f"sched-{len(up._scheduled_uploads)}",
        "platform": platform,
        "video_path": "video.mp4",
        "scheduled_time": when,
        "metadata": {"title": "t", "caption": "c", **metadata},
        "status": "pending",
    }
    up._remember_schedule(schedule)
    return schedule


def _stub_platform(monkeypatch, up: Uploader, platform: str, stub) -> None:
    monkeypatch.setattr(up, f"upload_to_{platform}", stub)


# --------------------------------------------------------------------------
# Successful outcomes
# --------------------------------------------------------------------------

async def test_success_result_is_executed_and_returned(uploader, monkeypatch):
    result = {"status": "success", "platform": "instagram", "media_id": "m1"}
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(result))
    schedule = _add(uploader)

    returned = await uploader.execute_scheduled_uploads()

    assert schedule["status"] == "executed"
    assert schedule["result"] is result
    assert returned == [result]
    assert returned[0] is result


async def test_explicit_simulated_false_success_is_still_executed(uploader, monkeypatch):
    result = {"status": "success", "simulated": False}
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(result))
    schedule = _add(uploader)

    returned = await uploader.execute_scheduled_uploads()

    assert schedule["status"] == "executed"
    assert returned == [result]


@pytest.mark.parametrize("real_status", ["published", "uploaded", "scheduled"])
async def test_real_shaped_success_statuses_are_executed(uploader, monkeypatch, real_status):
    """'published' (IG/TikTok/X) and 'uploaded'/'scheduled' (YouTube) override the
    leading status='success' in the real upload_to_* return values."""
    result = {"status": real_status, "platform": "instagram", "id": "abc"}
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(result))
    schedule = _add(uploader)

    returned = await uploader.execute_scheduled_uploads()

    assert schedule["status"] == "executed"
    assert schedule["result"] is result
    assert returned == [result]


@pytest.mark.parametrize("platform", ["youtube", "instagram", "tiktok", "twitter"])
async def test_each_platform_dispatches_to_its_own_stub(uploader, monkeypatch, platform):
    result = {"status": "published", "platform": platform}
    _stub_platform(monkeypatch, uploader, platform, _stub_returning(result))
    schedule = _add(uploader, platform=platform)

    returned = await uploader.execute_scheduled_uploads()

    assert uploader.unstubbed_calls == []
    assert schedule["status"] == "executed"
    assert returned == [result]


# --------------------------------------------------------------------------
# Non-success outcomes: never 'executed', never returned
# --------------------------------------------------------------------------

async def test_error_result_is_failed_with_message_and_not_returned(uploader, monkeypatch):
    result = {"status": "error", "message": "Video file not found"}
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(result))
    schedule = _add(uploader)

    returned = await uploader.execute_scheduled_uploads()

    assert schedule["status"] == "failed"
    assert schedule["error"] == "Video file not found"
    assert returned == []


async def test_blocked_result_is_blocked_with_reason_and_not_returned(uploader, monkeypatch):
    result = {"status": "blocked", "platform": "instagram", "reason": "owner did not approve publish"}
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(result))
    schedule = _add(uploader)

    returned = await uploader.execute_scheduled_uploads()

    assert schedule["status"] == "blocked"
    assert schedule["reason"] == "owner did not approve publish"
    assert returned == []


async def test_simulated_result_from_simulate_upload_is_simulated_and_not_returned(uploader, monkeypatch):
    # The exact shape the real _simulate_upload produces (no network involved).
    result = uploader._simulate_upload("instagram", "video.mp4", "caption")
    assert result["simulated"] is True and result["status"] == "simulated"
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(result))
    schedule = _add(uploader)

    returned = await uploader.execute_scheduled_uploads()

    assert schedule["status"] == "simulated"
    assert schedule["result"] is result
    assert returned == []


async def test_simulated_flag_wins_even_when_status_is_success(uploader, monkeypatch):
    result = {"status": "success", "simulated": True}
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(result))
    schedule = _add(uploader)

    returned = await uploader.execute_scheduled_uploads()

    assert schedule["status"] == "simulated"
    assert returned == []


async def test_simulated_error_youtube_no_credentials_shape_is_simulated_not_failed(uploader, monkeypatch):
    result = {
        "status": "error",
        "message": "Google API credentials not configured",
        "simulated": True,
        "video_id": "sim_abc123",
    }
    _stub_platform(monkeypatch, uploader, "youtube", _stub_returning(result))
    schedule = _add(uploader, platform="youtube")

    returned = await uploader.execute_scheduled_uploads()

    assert schedule["status"] == "simulated"
    assert returned == []


async def test_unrecognised_platform_uses_real_simulate_upload_and_is_simulated(uploader):
    """'facebook' has no upload_to_* method, so the real _simulate_upload runs."""
    schedule = _add(uploader, platform="facebook")

    returned = await uploader.execute_scheduled_uploads()

    assert schedule["status"] == "simulated"
    assert returned == []
    assert uploader.unstubbed_calls == []


async def test_partial_result_fails_closed_and_keeps_error(uploader, monkeypatch):
    result = {
        "status": "partial",
        "platform": "instagram",
        "creation_id": "c-1",
        "error": "media publish failed: 500",
        "retry_with": {"creation_id": "c-1"},
    }
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(result))
    schedule = _add(uploader)

    returned = await uploader.execute_scheduled_uploads()

    assert schedule["status"] == "failed"
    assert schedule["error"] == "media publish failed: 500"
    # The raw result (with the resumable creation_id) is kept on the schedule.
    assert schedule["result"] is result
    assert returned == []


@pytest.mark.parametrize(
    "result",
    [
        {"status": "weird"},
        {"status": ""},
        {"platform": "instagram"},  # no status key at all
        {"status": None},
        None,
        "ok",
    ],
)
async def test_unknown_status_or_shape_fails_closed(uploader, monkeypatch, result):
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(result))
    schedule = _add(uploader)

    returned = await uploader.execute_scheduled_uploads()

    assert schedule["status"] == "failed"
    assert schedule["error"]
    assert returned == []


# --------------------------------------------------------------------------
# Batches, claim semantics, exception path
# --------------------------------------------------------------------------

async def test_mixed_batch_returns_only_successes_in_order_and_each_schedule_has_own_status(uploader, monkeypatch):
    ok_yt = {"status": "uploaded", "platform": "youtube", "video_id": "y1"}
    ok_tt = {"status": "published", "platform": "tiktok", "video_id": "t1"}
    _stub_platform(monkeypatch, uploader, "youtube", _stub_returning(ok_yt))
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(
        {"status": "blocked", "platform": "instagram", "reason": "denied"}))
    _stub_platform(monkeypatch, uploader, "tiktok", _stub_returning(ok_tt))
    _stub_platform(monkeypatch, uploader, "twitter", _stub_returning(
        {"status": "error", "message": "boom"}))

    s_yt = _add(uploader, platform="youtube")
    s_ig = _add(uploader, platform="instagram")
    s_sim = _add(uploader, platform="facebook")
    s_tt = _add(uploader, platform="tiktok")
    s_tw = _add(uploader, platform="twitter")

    returned = await uploader.execute_scheduled_uploads()

    assert returned == [ok_yt, ok_tt]
    assert [s["status"] for s in (s_yt, s_ig, s_sim, s_tt, s_tw)] == [
        "executed", "blocked", "simulated", "executed", "failed",
    ]
    assert s_ig["reason"] == "denied"
    assert s_tw["error"] == "boom"


async def test_one_success_and_one_blocked_returns_exactly_the_success(uploader, monkeypatch):
    success = {"status": "success", "platform": "youtube", "video_id": "y1"}
    _stub_platform(monkeypatch, uploader, "youtube", _stub_returning(success))
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(
        {"status": "blocked", "platform": "instagram", "reason": "no approval"}))
    s_ok = _add(uploader, platform="youtube")
    s_blocked = _add(uploader, platform="instagram")

    returned = await uploader.execute_scheduled_uploads()

    assert len(returned) == 1
    assert returned[0] is success
    assert s_ok["status"] == "executed"
    assert s_blocked["status"] == "blocked"
    assert s_blocked["reason"] == "no approval"


async def test_raising_stub_yields_failed_via_existing_exception_path(uploader, monkeypatch):
    exc = RuntimeError("network exploded")
    ok = {"status": "published", "platform": "tiktok"}
    _stub_platform(monkeypatch, uploader, "instagram", _stub_raising(exc))
    _stub_platform(monkeypatch, uploader, "tiktok", _stub_returning(ok))
    s_raise = _add(uploader, platform="instagram")
    s_after = _add(uploader, platform="tiktok")

    returned = await uploader.execute_scheduled_uploads()

    assert s_raise["status"] == "failed"
    assert s_raise["error"] == str(exc)
    assert "result" not in s_raise
    # A raising item does not stop later items from being processed.
    assert s_after["status"] == "executed"
    assert returned == [ok]


async def test_items_are_uploading_during_call_and_future_item_stays_pending(uploader, monkeypatch):
    due = _add(uploader)
    future = _add(uploader, when=_future())
    seen = {}

    async def _stub(*args, **kwargs):
        seen["due_status"] = due["status"]
        seen["future_status"] = future["status"]
        return {"status": "success"}

    _stub_platform(monkeypatch, uploader, "instagram", _stub)

    returned = await uploader.execute_scheduled_uploads()

    assert seen == {"due_status": "uploading", "future_status": "pending"}
    assert due["status"] == "executed"
    assert future["status"] == "pending"
    assert "result" not in future
    assert returned == [{"status": "success"}]


async def test_second_call_does_not_reprocess_settled_items(uploader, monkeypatch):
    calls = []

    async def _stub(*args, **kwargs):
        calls.append(1)
        return {"status": "blocked", "reason": "denied"}

    _stub_platform(monkeypatch, uploader, "instagram", _stub)
    schedule = _add(uploader)

    await uploader.execute_scheduled_uploads()
    await uploader.execute_scheduled_uploads()

    assert calls == [1]
    assert schedule["status"] == "blocked"


# --------------------------------------------------------------------------
# Downstream views
# --------------------------------------------------------------------------

async def test_get_scheduled_uploads_executed_excludes_error_blocked_and_simulated(uploader, monkeypatch):
    _stub_platform(monkeypatch, uploader, "youtube", _stub_returning({"status": "uploaded"}))
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning({"status": "error", "message": "x"}))
    _stub_platform(monkeypatch, uploader, "tiktok", _stub_returning({"status": "blocked", "reason": "y"}))
    _stub_platform(monkeypatch, uploader, "twitter", _stub_returning({"status": "simulated", "simulated": True}))
    s_ok = _add(uploader, platform="youtube")
    _add(uploader, platform="instagram")
    _add(uploader, platform="tiktok")
    _add(uploader, platform="twitter")

    await uploader.execute_scheduled_uploads()

    assert uploader.get_scheduled_uploads("executed") == [s_ok]
    assert len(uploader.get_scheduled_uploads("failed")) == 1
    assert len(uploader.get_scheduled_uploads("blocked")) == 1
    assert len(uploader.get_scheduled_uploads("simulated")) == 1


async def test_run_execute_scheduled_uploads_results_contain_only_genuine_successes(uploader, monkeypatch):
    success = {"status": "published", "platform": "tiktok", "video_id": "t1"}
    _stub_platform(monkeypatch, uploader, "tiktok", _stub_returning(success))
    _stub_platform(monkeypatch, uploader, "instagram", _stub_returning(
        {"status": "blocked", "reason": "denied"}))
    _stub_platform(monkeypatch, uploader, "twitter", _stub_returning(
        {"status": "error", "message": "nope"}))
    _stub_platform(monkeypatch, uploader, "youtube", _stub_returning(
        {"status": "error", "message": "no creds", "simulated": True}))
    _add(uploader, platform="instagram")
    _add(uploader, platform="tiktok")
    _add(uploader, platform="twitter")
    _add(uploader, platform="youtube")

    out = await uploader.run({"type": "execute_scheduled_uploads"})

    assert out["status"] == "ok"
    assert out["results"] == [success]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
