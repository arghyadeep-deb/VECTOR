"""
Regression tests for the content-district fake-success-stub bug.

AgentBase.run() (core/city/agent_base.py) defines a generic fallback that
returns {"status": "ok", "agent": self.name, "task": task} without doing any
real work. Nine content-district classes had this problem in two ways:

Group A — had a run()-shaped method but keyed off task["params"]["action"]
(with a hardcoded default) instead of task["type"], so a governor dispatch
of {"type": "...", "params": {...}} either ignored the type entirely
(VideoGenerator, VideoPipelineAgent always called the same method) or had
no way to be selected via task["type"] at all (MediaStudioAgent,
WebsiteToVideoAgent):
  - MediaStudioAgent     (districts/content/media_studio_agent.py)
  - VideoGenerator       (districts/content/video_generator.py)
  - VideoPipelineAgent   (districts/content/video_pipeline.py)
  - WebsiteToVideoAgent  (districts/content/website_to_video.py)

Group B — had NO run() of its own at all, silently inheriting AgentBase's
fake-success stub:
  - CaptionGenerator     (districts/content/caption_generator.py)
  - ContentScheduler     (districts/content/content_scheduler.py)
  - Uploader             (districts/content/uploader.py)
  - VideoMerger          (districts/content/video_merger.py)
  - VoiceGenerator       (districts/content/voice_generator.py)

These tests assert that run() now branches on task["type"], dispatches to
the class's real, existing methods, and that an unrecognized type returns
a proper error shape instead of the AgentBase stub shape (which echoes back
"agent" and "task" keys).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.content.media_studio_agent import MediaStudioAgent
from districts.content.video_generator import VideoGenerator
from districts.content.video_pipeline import VideoPipelineAgent
from districts.content.website_to_video import WebsiteToVideoAgent
from districts.content.caption_generator import CaptionGenerator
from districts.content.content_scheduler import ContentScheduler
from districts.content.uploader import Uploader
from districts.content.video_merger import VideoMerger
from districts.content.voice_generator import VoiceGenerator


# ---------------------------------------------------------------------------
# Group A: MediaStudioAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_media_studio_agent_run_media_status_routes_by_type():
    agent = MediaStudioAgent()
    result = await agent.run({"type": "media_status"})
    # "muapi" integration was removed — current status contract is local + wan2gp + mode
    assert "wan2gp" in result
    assert "local" in result
    assert "mode" in result


@pytest.mark.asyncio
async def test_media_studio_agent_run_list_models_routes_by_type():
    agent = MediaStudioAgent()
    result = await agent.run({"type": "list_models", "params": {"category": "t2i"}})
    assert "cloud_models" in result


@pytest.mark.asyncio
async def test_media_studio_agent_run_unhandled_type_returns_error_shape():
    agent = MediaStudioAgent()
    result = await agent.run({"type": "totally_bogus_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_media_studio_agent_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (core/city/governor.py _dispatch_to_district /
    core/api/routers/commands.py): the governor's classifier invents a task_type per
    request and puts the user's actual free-text message in params["query"]/["content"].
    This test originally documented a LIVE BUG: MediaStudioAgent.run()
    (districts/content/media_studio_agent.py) had no query fallback after its
    structured branches, so "what image/video models do you have available?" hit the
    error stub. Fixed 2026-08-05 — routes to the READ-ONLY, no-required-argument
    list_models()/media_status() capabilities; never triggers a real GPU render job
    (generate_image/generate_video/lipsync/...) from unmatched free text. Flipped
    from documenting the bug to asserting the fix.
    """
    agent = MediaStudioAgent()
    result = await agent.run({
        "type": "ask_media_studio",
        "params": {
            "query": "What image and video generation models do you have available?",
            "content": "What image and video generation models do you have available?",
            "source": "api_command",
        },
    })
    assert "error" not in result, f"a real free-text question must not return the error stub: {result}"
    assert "cloud_models" in result


# ---------------------------------------------------------------------------
# Group A: VideoGenerator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_video_generator_run_tags_routes_to_generate_tags():
    agent = VideoGenerator()
    result = await agent.run({"type": "generate_tags", "params": {"topic": "AI tools", "count": 3}})
    assert result["status"] == "ok"
    assert "tags" in result


@pytest.mark.asyncio
async def test_video_generator_run_title_thumbnail_routes_correctly():
    agent = VideoGenerator()
    result = await agent.run({"type": "title_thumbnail", "params": {"topic": "AI tools"}})
    assert result["status"] == "ok"
    assert "options" in result or "error" in result


@pytest.mark.asyncio
async def test_video_generator_run_unhandled_type_returns_error_shape():
    agent = VideoGenerator()
    result = await agent.run({"type": "not_a_real_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_video_generator_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_media_studio_agent_run_real_dispatch_shape_with_query
    above for the full explanation). This test originally documented a LIVE BUG:
    VideoGenerator.run() (districts/content/video_generator.py) had no query fallback,
    so "can you suggest some tags for my AI tools video?" hit the error stub because
    the invented task_type didn't match title_thumbnail/generate_tags/render_html.
    Fixed 2026-08-05 — keyword-routed to generate_tags() (never render_html_to_video,
    a real GPU render job, from unmatched free text). Flipped from documenting the bug
    to asserting the fix.
    """
    agent = VideoGenerator()
    result = await agent.run({
        "type": "ask_video_generator",
        "params": {
            "query": "Can you suggest some tags for my new AI tools video?",
            "content": "Can you suggest some tags for my new AI tools video?",
            "source": "api_command",
        },
    })
    assert result.get("status") != "error", f"a real free-text question must not return the error stub: {result}"
    assert "tags" in result


# ---------------------------------------------------------------------------
# Group A: VideoPipelineAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_video_pipeline_agent_run_unhandled_type_returns_error_shape():
    agent = VideoPipelineAgent()
    result = await agent.run({"type": "nonsense_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_video_pipeline_agent_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_media_studio_agent_run_real_dispatch_shape_with_query
    above for the full explanation). This test originally documented a LIVE BUG:
    VideoPipelineAgent.run() (districts/content/video_pipeline.py) had a query
    fallback (answer_content_question) but it was gated on `task_type == ""`
    specifically (an EXACTLY empty string), not on "any unmatched/invented type". The
    real governor dispatch shape always supplies a non-empty, classifier-invented
    task_type string, so the fallback never actually fired for real chat traffic — a
    genuine "what's a good topic for my next AI video?" fell through to the error
    stub despite the fallback looking like it should have caught it. Fixed 2026-08-05
    — the gate now fires on any task_type other than the exact structured matches
    (create_and_upload/job_status/job_queue/job_history); create_and_upload (the real
    render+upload job) still only fires on an exact match, unchanged. Flipped from
    documenting the bug to asserting the fix.
    """
    agent = VideoPipelineAgent()
    result = await agent.run({
        "type": "ask_video_pipeline",
        "params": {
            "query": "What's a good topic for my next AI video?",
            "content": "What's a good topic for my next AI video?",
            "source": "api_command",
        },
    })
    assert result.get("status") != "error", f"a real free-text question must not return the error stub: {result}"
    assert "response" in result


@pytest.mark.asyncio
async def test_video_pipeline_agent_run_job_status_routes_to_get_job():
    agent = VideoPipelineAgent()
    # Seed a job directly via the agent's own persistence helper, then
    # confirm run() can retrieve it through the dispatch interface.
    job = {
        "id": "test-run-wiring-001", "topic": "test", "niche": "AI",
        "platform": "both", "status": "pending", "stage_pct": 0,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        "youtube_url": None, "instagram_url": None,
        "video_path": None, "error": None, "upload_after": None,
    }
    from districts.content.video_pipeline import _upsert_job
    _upsert_job(job)
    result = await agent.run({"type": "job_status", "params": {"job_id": "test-run-wiring-001"}})
    assert result["status"] == "ok"
    assert result["job"]["topic"] == "test"


# ---------------------------------------------------------------------------
# Group A: WebsiteToVideoAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(
    __import__("shutil").which("ffmpeg") is None or sys.platform == "win32",
    reason="ffmpeg not installed, or Windows: this suite forces "
           "WindowsSelectorEventLoopPolicy session-wide (tests/conftest.py) "
           "to avoid IOCP socket exhaustion across thousands of mocked "
           "async tests, but SelectorEventLoop cannot spawn subprocesses — "
           "render_title_card()'s real (unmocked) Playwright browser launch "
           "needs asyncio.create_subprocess_exec, which only ProactorEventLoop "
           "supports on Windows. Environment/event-loop-policy conflict, not "
           "a routing bug — routing itself is confirmed correct by reading "
           "website_to_video.py's dispatch logic.",
)
async def test_website_to_video_agent_run_title_card_routes_by_type():
    agent = WebsiteToVideoAgent()
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "title.mp4")
        result = await agent.run({
            "type": "title_card",
            "params": {"title": "Test", "subtitle": "Sub", "output": out},
        })
        assert result["status"] == "ok"
        assert result["title"] == "Test"


@pytest.mark.asyncio
async def test_website_to_video_agent_run_unhandled_type_returns_error_shape():
    agent = WebsiteToVideoAgent()
    result = await agent.run({"type": "garbage_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_website_to_video_agent_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_media_studio_agent_run_real_dispatch_shape_with_query
    above for the full explanation). This test originally documented a LIVE BUG:
    WebsiteToVideoAgent.run() (districts/content/website_to_video.py) had no query
    fallback, so "can you turn this website into a video?" hit the error stub because
    the invented task_type didn't match capture_url/title_card/data_viz/remove_bg.
    Fixed 2026-08-05: every real capability here renders video/processes media (a
    real, resource-consuming job) and there is no safe read-only capability to fall
    back to, so per the safety contract it never guesses one — it now returns a
    grounded {"status": "ok", "response": ...} explaining what's needed instead of an
    error stub. Flipped from documenting the bug to asserting the fix.
    """
    agent = WebsiteToVideoAgent()
    result = await agent.run({
        "type": "ask_website_to_video",
        "params": {
            "query": "Can you turn my landing page into a short promo video?",
            "content": "Can you turn my landing page into a short promo video?",
            "source": "api_command",
        },
    })
    assert result.get("status") == "ok", f"a real free-text question must not return the error stub: {result}"
    assert "response" in result


# ---------------------------------------------------------------------------
# Group B: CaptionGenerator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_caption_generator_run_generate_captions_routes_correctly():
    agent = CaptionGenerator()
    result = await agent.run({
        "type": "generate_captions",
        "params": {"transcript": "Hello world this is a test transcript.", "style": "standard"},
    })
    assert isinstance(result, dict)
    assert "agent" not in result
    assert result.get("status") in ("success", "error") or "blocks" in result or "transcript" in result


@pytest.mark.asyncio
async def test_caption_generator_run_unhandled_type_returns_error_shape():
    agent = CaptionGenerator()
    result = await agent.run({"type": "made_up_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_caption_generator_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_media_studio_agent_run_real_dispatch_shape_with_query
    above for the full explanation). This test originally documented a LIVE BUG:
    CaptionGenerator.run() (districts/content/caption_generator.py) had no query
    fallback, so "can you generate captions for my video transcript?" hit the error
    stub. Fixed 2026-08-05: every real capability here needs a real transcript/
    video_path/captions object we don't have from free text alone, so it never
    invents one — it now returns a grounded {"status": "ok", "response": ...}
    explaining what input it needs instead of an error stub. Flipped from documenting
    the bug to asserting the fix.
    """
    agent = CaptionGenerator()
    result = await agent.run({
        "type": "ask_caption_generator",
        "params": {
            "query": "Can you generate captions for my video transcript?",
            "content": "Can you generate captions for my video transcript?",
            "source": "api_command",
        },
    })
    assert result.get("status") == "ok", f"a real free-text question must not return the error stub: {result}"
    assert "response" in result


# ---------------------------------------------------------------------------
# Group B: ContentScheduler
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_content_scheduler_run_summary_routes_to_get_summary():
    agent = ContentScheduler()
    result = await agent.run({"type": "summary"})
    assert isinstance(result, dict)
    assert "agent" not in result


@pytest.mark.asyncio
async def test_content_scheduler_run_schedule_post_routes_correctly():
    agent = ContentScheduler()
    result = await agent.run({
        "type": "schedule_post",
        "params": {"title": "Test Post", "content": "Body text", "platforms": ["devto"]},
    })
    assert "job_ids" in result
    assert result["title"] == "Test Post"


@pytest.mark.asyncio
async def test_content_scheduler_run_unhandled_type_returns_error_shape():
    agent = ContentScheduler()
    result = await agent.run({"type": "totally_made_up"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_content_scheduler_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_media_studio_agent_run_real_dispatch_shape_with_query
    above for the full explanation). This test originally documented a LIVE BUG:
    ContentScheduler.run() (districts/content/content_scheduler.py) had no query
    fallback, so "what's currently scheduled to be posted?" hit the error stub. Fixed
    2026-08-05 — routes to the READ-ONLY, no-required-argument get_summary(); never
    triggers schedule_post() or run_pending() (a real, RED-tier publish) from
    unmatched free text. Flipped from documenting the bug to asserting the fix.
    """
    agent = ContentScheduler()
    result = await agent.run({
        "type": "ask_content_scheduler",
        "params": {
            "query": "What's currently scheduled to be posted this week?",
            "content": "What's currently scheduled to be posted this week?",
            "source": "api_command",
        },
    })
    assert "error" not in result, f"a real free-text question must not return the error stub: {result}"
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Group B: Uploader
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_uploader_run_upload_youtube_graceful_no_credentials():
    agent = Uploader()
    result = await agent.run({
        "type": "upload_youtube",
        "params": {
            "video_path": "this_file_definitely_does_not_exist.mp4",
            "title": "Test", "description": "Desc", "tags": ["a", "b"],
        },
    })
    # Real method reached, no file -> graceful error, never crashes, never the stub.
    assert result["status"] == "error"
    assert "agent" not in result


@pytest.mark.asyncio
async def test_uploader_run_history_routes_to_get_upload_history():
    agent = Uploader()
    result = await agent.run({"type": "upload_history"})
    assert isinstance(result, dict)
    assert "history" in result


@pytest.mark.asyncio
async def test_uploader_run_unhandled_type_returns_error_shape():
    agent = Uploader()
    result = await agent.run({"type": "invalid_type_xyz"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_uploader_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_media_studio_agent_run_real_dispatch_shape_with_query
    above for the full explanation). This test originally documented a LIVE BUG:
    Uploader.run() (districts/content/uploader.py) had no query fallback, so "show me
    my recent upload history" hit the error stub. Fixed 2026-08-05 — routes to the
    READ-ONLY, no-required-argument get_upload_history()/get_scheduled_uploads();
    never triggers a real upload_to_youtube/instagram/tiktok/twitter (RED-tier,
    owner-approval-gated publish) from unmatched free text. Flipped from documenting
    the bug to asserting the fix.
    """
    agent = Uploader()
    result = await agent.run({
        "type": "ask_uploader",
        "params": {
            "query": "Show me my recent upload history across platforms.",
            "content": "Show me my recent upload history across platforms.",
            "source": "api_command",
        },
    })
    assert result.get("status") != "error", f"a real free-text question must not return the error stub: {result}"
    assert "history" in result


# ---------------------------------------------------------------------------
# Group B: VideoMerger
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_video_merger_run_merge_clips_graceful_missing_dir():
    agent = VideoMerger()
    result = await agent.run({
        "type": "merge_clips",
        "params": {"clips_dir": "this_dir_does_not_exist", "output_path": "out.mp4"},
    })
    assert result["status"] == "error"
    assert "agent" not in result


@pytest.mark.asyncio
async def test_video_merger_run_unhandled_type_returns_error_shape():
    agent = VideoMerger()
    result = await agent.run({"type": "made_up_type_xyz"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_video_merger_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_media_studio_agent_run_real_dispatch_shape_with_query
    above for the full explanation). This test originally documented a LIVE BUG:
    VideoMerger.run() (districts/content/video_merger.py) had no query fallback, so
    "can you merge my clips together with transitions?" hit the error stub. Fixed
    2026-08-05: every real capability here spawns a real ffmpeg subprocess against
    real files on disk, and there is no safe read-only capability to fall back to, so
    it never guesses a clips_dir/video_path — it now returns a grounded {"status":
    "ok", "response": ...} explaining what's needed instead of an error stub. Flipped
    from documenting the bug to asserting the fix.
    """
    agent = VideoMerger()
    result = await agent.run({
        "type": "ask_video_merger",
        "params": {
            "query": "Can you merge my video clips together with smooth transitions?",
            "content": "Can you merge my video clips together with smooth transitions?",
            "source": "api_command",
        },
    })
    assert result.get("status") == "ok", f"a real free-text question must not return the error stub: {result}"
    assert "response" in result


# ---------------------------------------------------------------------------
# Group B: VoiceGenerator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voice_generator_run_get_voices_routes_to_get_available_voices():
    agent = VoiceGenerator()
    result = await agent.run({"type": "get_voices"})
    assert isinstance(result, dict)
    assert "voices" in result


@pytest.mark.asyncio
async def test_voice_generator_run_generate_voice_routes_correctly(monkeypatch):
    agent = VoiceGenerator()
    # This test is about dispatch, not about whether a TTS engine happens to be installed: since generate_voice() was
    # fixed to use the real kokoro_onnx API (2026-09-26) it succeeds wherever the local model exists, so pin the
    # engine to "unavailable" to keep the graceful-error contract deterministic. Real synthesis is covered by
    # tests/test_voice_generator_kokoro.py.
    monkeypatch.setattr(agent, "_available", True)
    monkeypatch.setattr(agent, "_load_kokoro", lambda: (_ for _ in ()).throw(RuntimeError("no loadable Kokoro model")))
    result = await agent.run({
        "type": "generate_voice",
        "params": {"text": "Hello world", "voice_name": "af_heart"},
    })
    assert isinstance(result, dict)
    assert "agent" not in result
    assert result.get("status") == "error"  # engine failure -> graceful, never crashes


@pytest.mark.asyncio
async def test_voice_generator_run_unhandled_type_returns_error_shape():
    agent = VoiceGenerator()
    result = await agent.run({"type": "made_up_type_xyz"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_voice_generator_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_media_studio_agent_run_real_dispatch_shape_with_query
    above for the full explanation). This test originally documented a LIVE BUG:
    VoiceGenerator.run() (districts/content/voice_generator.py) had no query
    fallback, so "what voices are available for narration?" hit the error stub.
    Fixed 2026-08-05 — routes to the READ-ONLY, no-required-argument
    get_available_voices(); never triggers a real TTS render, paid ElevenLabs voice
    cloning, or an ffmpeg subprocess from unmatched free text. Flipped from
    documenting the bug to asserting the fix.
    """
    agent = VoiceGenerator()
    result = await agent.run({
        "type": "ask_voice_generator",
        "params": {
            "query": "What voices are available for narrating my video?",
            "content": "What voices are available for narrating my video?",
            "source": "api_command",
        },
    })
    assert result.get("status") != "error", f"a real free-text question must not return the error stub: {result}"
    assert "voices" in result


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
