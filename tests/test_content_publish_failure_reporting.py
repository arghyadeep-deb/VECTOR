"""Regression coverage for honest content-publication failure reporting.

Before this fix, ContentScheduler marked a job published even when the real
publisher returned ``success=False``. Configured Instagram, TikTok, and X
uploads also fell through to a simulated result after a real API exception,
which hid the failed outward action from scheduling and retry logic.
"""
from __future__ import annotations

import asyncio
import runpy
import sys
import types
from pathlib import Path

import pytest

import core.loop.permission_gateway as permission_gateway
from districts.content.blog_publisher import PublishResult
from districts.content.comfyui_adapter import ComfyUIAdapter
from districts.content.content_scheduler import ContentScheduler
from districts.content.post_job import PostJobTracker
from districts.content.uploader import Uploader
from districts.research.news_aggregator import NewsAggregator


class _Approval:
    approved = True
    reason = "approved for regression test"


class _Gateway:
    async def execute(self, action):
        return _Approval()


class _Tracker:
    def __init__(self) -> None:
        self.published: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def recover_stale_publishing(self) -> None:
        return None

    def list_pending(self) -> list[types.SimpleNamespace]:
        return [types.SimpleNamespace(
            job_id="job-1",
            platform="devto",
            title="Failure must stay visible",
            payload={"content": "body"},
        )]

    def mark_publishing(self, job_id: str) -> None:
        return None

    def mark_published(self, job_id: str) -> None:
        self.published.append(job_id)

    def mark_failed(self, job_id: str, error: str) -> None:
        self.failed.append((job_id, error))


class _FailingPublisher:
    def publish_all(self, title: str, content: str, platforms: list[str]):
        return [PublishResult(platform=platforms[0], success=False, error="HTTP 503")]


def test_scheduler_does_not_mark_failed_platform_publish_as_published(monkeypatch):
    """The scheduler must preserve a platform failure instead of claiming publication."""
    monkeypatch.setattr(permission_gateway, "PermissionGateway", _Gateway)
    scheduler = ContentScheduler()
    tracker = _Tracker()
    monkeypatch.setattr(scheduler, "_get_tracker", lambda: tracker)
    monkeypatch.setattr(scheduler, "_get_publisher", _FailingPublisher)

    result = asyncio.run(scheduler.run_pending())

    assert tracker.published == []
    assert tracker.failed == [("job-1", "HTTP 503")]
    assert result["results"][0]["status"] == "failed"


class _Response:
    status_code = 500
    text = "upstream unavailable"


class _HTTPClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, *args, **kwargs):
        return _Response()


@pytest.mark.parametrize(
    ("platform", "credential_key"),
    [("instagram", "instagram_access_token"), ("tiktok", "tiktok_access_token"),
     ("twitter", "twitter_access_token")],
)
def test_configured_upload_api_failure_is_not_relabelled_simulated(
    monkeypatch, tmp_path: Path, platform: str, credential_key: str,
):
    """Exercise each real configured API path and require an honest error result."""
    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(AsyncClient=_HTTPClient))
    uploader = Uploader()
    uploader._api_credentials = {credential_key: "test-secret", "instagram_account_id": "acct"}
    monkeypatch.setattr(uploader, "_dry_run_enabled", lambda: False)
    async def _approved(platform_name: str, title: str) -> tuple[bool, str]:
        return True, "approved for regression test"
    monkeypatch.setattr(uploader, "_gate_publish", _approved)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")

    if platform == "instagram":
        result = asyncio.run(uploader.upload_to_instagram(str(video), "caption", []))
    elif platform == "tiktok":
        result = asyncio.run(uploader.upload_to_tiktok(str(video), "caption"))
    else:
        result = asyncio.run(uploader.upload_to_twitter(str(video), "caption"))

    assert result["status"] == "error"
    assert result["platform"] == platform
    assert result.get("simulated") is not True


def test_newsapi_key_is_not_embedded_in_request_url(monkeypatch):
    """NewsAPI credentials must travel in a header, not log-prone query parameters."""
    observed: dict = {}

    class _NewsResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"articles": []}

    class _NewsClient(_HTTPClient):
        async def get(self, url, *, params, headers):
            observed.update(url=url, params=params, headers=headers)
            return _NewsResponse()

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(AsyncClient=_NewsClient))
    aggregator = NewsAggregator()
    aggregator._newsapi_key = "super-secret"

    assert asyncio.run(aggregator.fetch_newsapi()) == []
    assert "apiKey" not in observed["params"]
    assert "super-secret" not in str(observed["params"])
    assert observed["headers"] == {"X-Api-Key": "super-secret"}


def test_post_job_claim_is_atomic(tmp_path: Path):
    """Only one scheduler may claim a pending job for real publication."""
    tracker = PostJobTracker(db_path=tmp_path / "post_jobs.db")
    job_id = tracker.create("devto", "One publish only", {"content": "body"})

    tracker.mark_publishing(job_id)
    with pytest.raises(RuntimeError, match="not claimable"):
        tracker.mark_publishing(job_id)

    claimed = tracker.get(job_id)
    assert claimed is not None
    assert claimed.status == "publishing"
    assert claimed.attempt_count == 1


def test_comfyui_output_path_cannot_escape_output_directory(tmp_path: Path):
    """Untrusted ComfyUI history fields must not select an arbitrary local file."""
    adapter = ComfyUIAdapter()
    adapter._output_dir = tmp_path / "outputs"

    class _NeverFetch:
        async def get(self, *args, **kwargs):
            raise AssertionError("path validation must happen before the download")

    with pytest.raises(ValueError, match="escapes"):
        asyncio.run(adapter._fetch_output(
            _NeverFetch(),
            {"filename": "secret.txt", "subfolder": "../../outside"},
        ))


def test_blog_publisher_self_test_never_uses_configured_credentials(monkeypatch):
    """Running the required __main__ check must never publish a real test article."""
    from core.config import CONFIG
    import districts.content.blog_publisher as blog_module

    monkeypatch.setitem(CONFIG, "blog", {
        "devto_api_key": "real-looking-devto-key",
        "hashnode_token": "real-looking-hashnode-token",
        "hashnode_publication_id": "publication-id",
        "medium_token": "real-looking-medium-token",
    })

    def _forbidden_network(*args, **kwargs):
        raise AssertionError("blog_publisher __main__ attempted a real network request")

    monkeypatch.setattr(blog_module.httpx, "get", _forbidden_network)
    monkeypatch.setattr(blog_module.httpx, "post", _forbidden_network)

    runpy.run_module("districts.content.blog_publisher", run_name="__main__")
