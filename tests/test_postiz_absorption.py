"""
Tests for Postiz-app-main absorption:
  - districts/content/analytics_retriever.py (AnalyticsRetriever)
  - districts/content/blog_publisher.py      (BlogPublisher)
  - districts/content/post_job.py            (PostJobTracker)

All tests run without real API credentials — graceful degradation verified throughout.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── Analytics Retriever ────────────────────────────────────────────────────────

class TestPostMetricsDataclass(unittest.TestCase):
    def test_imports(self):
        from districts.content.analytics_retriever import PostMetrics, PostRef, AnalyticsRetriever
        self.assertTrue(True)

    def test_post_metrics_defaults(self):
        from districts.content.analytics_retriever import PostMetrics
        m = PostMetrics(platform="youtube", post_id="abc")
        self.assertEqual(m.platform, "youtube")
        self.assertEqual(m.post_id, "abc")
        self.assertEqual(m.views, 0)
        self.assertEqual(m.likes, 0)
        self.assertEqual(m.comments, 0)
        self.assertEqual(m.shares, 0)
        self.assertEqual(m.impressions, 0)
        self.assertEqual(m.reach, 0)
        self.assertAlmostEqual(m.watch_time_minutes, 0.0)
        self.assertAlmostEqual(m.engagement_rate, 0.0)
        self.assertEqual(m.error, "")
        self.assertIsInstance(m.raw, dict)
        self.assertIsInstance(m.fetched_at, str)
        self.assertIn("T", m.fetched_at)  # ISO format

    def test_post_metrics_to_dict(self):
        from districts.content.analytics_retriever import PostMetrics
        m = PostMetrics(platform="instagram", post_id="xyz", views=1000, likes=50)
        d = m.to_dict()
        self.assertEqual(d["platform"], "instagram")
        self.assertEqual(d["post_id"], "xyz")
        self.assertEqual(d["views"], 1000)
        self.assertEqual(d["likes"], 50)
        self.assertIn("fetched_at", d)
        self.assertNotIn("raw", d)  # raw excluded from to_dict

    def test_post_ref_dataclass(self):
        from districts.content.analytics_retriever import PostRef
        ref = PostRef(platform="youtube", post_id="dQw4w9WgXcQ")
        self.assertEqual(ref.platform, "youtube")
        self.assertEqual(ref.post_id, "dQw4w9WgXcQ")
        self.assertIsInstance(ref.extra, dict)


class TestAnalyticsRetrieverYouTube(unittest.TestCase):
    def _retriever(self):
        from districts.content.analytics_retriever import AnalyticsRetriever
        return AnalyticsRetriever()

    def test_youtube_no_creds_returns_error(self):
        r = self._retriever()
        m = r.get_youtube_metrics("dQw4w9WgXcQ")
        self.assertEqual(m.platform, "youtube")
        self.assertEqual(m.post_id, "dQw4w9WgXcQ")
        self.assertNotEqual(m.error, "")

    def test_youtube_no_crash(self):
        r = self._retriever()
        m = r.get_youtube_metrics("any_id")
        self.assertIsNotNone(m)
        self.assertGreaterEqual(m.views, 0)

    def test_youtube_missing_creds_path_error(self):
        r = self._retriever()
        r._yt_creds_path = "/nonexistent/path.json"
        m = r.get_youtube_metrics("vid")
        self.assertNotEqual(m.error, "")

    def test_youtube_returns_post_metrics_type(self):
        from districts.content.analytics_retriever import PostMetrics
        r = self._retriever()
        m = r.get_youtube_metrics("test")
        self.assertIsInstance(m, PostMetrics)


class TestAnalyticsRetrieverInstagram(unittest.TestCase):
    def _retriever(self):
        from districts.content.analytics_retriever import AnalyticsRetriever
        return AnalyticsRetriever()

    def test_instagram_no_token_returns_error(self):
        r = self._retriever()
        r._ig_token = ""
        m = r.get_instagram_metrics("17854360229135492")
        self.assertEqual(m.platform, "instagram")
        self.assertNotEqual(m.error, "")

    def test_instagram_no_crash(self):
        r = self._retriever()
        m = r.get_instagram_metrics("media_id")
        self.assertIsNotNone(m)

    def test_instagram_with_mock_api(self):
        from districts.content.analytics_retriever import AnalyticsRetriever
        r = AnalyticsRetriever()
        r._ig_token = "fake_token"
        mock_data = {
            "data": [
                {"name": "impressions", "values": [{"value": 5000}]},
                {"name": "reach", "values": [{"value": 3000}]},
                {"name": "likes", "values": [{"value": 200}]},
                {"name": "comments", "values": [{"value": 30}]},
                {"name": "shares", "values": [{"value": 15}]},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data

        try:
            import httpx
            with patch("httpx.get", return_value=mock_resp):
                m = r.get_instagram_metrics("post_123")
            self.assertEqual(m.impressions, 5000)
            self.assertEqual(m.reach, 3000)
            self.assertEqual(m.likes, 200)
            self.assertEqual(m.comments, 30)
            self.assertEqual(m.shares, 15)
            self.assertGreater(m.engagement_rate, 0)
            self.assertEqual(m.error, "")
        except ImportError:
            self.skipTest("httpx not installed")

    def test_instagram_api_error_returns_error(self):
        from districts.content.analytics_retriever import AnalyticsRetriever
        r = AnalyticsRetriever()
        r._ig_token = "fake_token"
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        try:
            import httpx
            with patch("httpx.get", return_value=mock_resp):
                m = r.get_instagram_metrics("post_123")
            self.assertNotEqual(m.error, "")
        except ImportError:
            self.skipTest("httpx not installed")


class TestAnalyticsRetrieverBatch(unittest.TestCase):
    def _retriever(self):
        from districts.content.analytics_retriever import AnalyticsRetriever
        return AnalyticsRetriever()

    def test_batch_empty(self):
        r = self._retriever()
        result = r.get_batch_metrics([])
        self.assertEqual(result, [])

    def test_batch_youtube(self):
        from districts.content.analytics_retriever import PostRef
        r = self._retriever()
        batch = r.get_batch_metrics([PostRef("youtube", "vid1")])
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0].platform, "youtube")

    def test_batch_instagram(self):
        from districts.content.analytics_retriever import PostRef
        r = self._retriever()
        batch = r.get_batch_metrics([PostRef("instagram", "post1")])
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0].platform, "instagram")

    def test_batch_ig_alias(self):
        from districts.content.analytics_retriever import PostRef
        r = self._retriever()
        batch = r.get_batch_metrics([PostRef("ig", "post1")])
        self.assertEqual(batch[0].platform, "instagram")

    def test_batch_unsupported_platform(self):
        from districts.content.analytics_retriever import PostRef
        r = self._retriever()
        batch = r.get_batch_metrics([PostRef("tiktok", "tok1")])
        self.assertEqual(len(batch), 1)
        self.assertIn("not yet implemented", batch[0].error)

    def test_batch_mixed_platforms(self):
        from districts.content.analytics_retriever import PostRef
        r = self._retriever()
        batch = r.get_batch_metrics([
            PostRef("youtube", "vid1"),
            PostRef("instagram", "post1"),
            PostRef("linkedin", "lin1"),
        ])
        self.assertEqual(len(batch), 3)

    def test_summary_structure(self):
        from districts.content.analytics_retriever import PostRef
        r = self._retriever()
        batch = r.get_batch_metrics([
            PostRef("youtube", "vid1"),
            PostRef("instagram", "post1"),
            PostRef("tiktok", "tok1"),
        ])
        s = r.summary(batch)
        self.assertEqual(s["total_posts"], 3)
        self.assertIn("successful", s)
        self.assertIn("failed", s)
        self.assertIn("total_views", s)
        self.assertIn("total_likes", s)
        self.assertIn("total_comments", s)
        self.assertIn("total_shares", s)
        self.assertIn("avg_engagement_rate", s)
        self.assertIn("fetched_at", s)

    def test_summary_empty_list(self):
        r = self._retriever()
        s = r.summary([])
        self.assertEqual(s["total_posts"], 0)
        self.assertAlmostEqual(s["avg_engagement_rate"], 0.0)


# ── Blog Publisher ─────────────────────────────────────────────────────────────

class TestPublishResultDataclass(unittest.TestCase):
    def test_imports(self):
        from districts.content.blog_publisher import BlogPublisher, PublishResult
        self.assertTrue(True)

    def test_publish_result_defaults(self):
        from districts.content.blog_publisher import PublishResult
        r = PublishResult(platform="devto", success=True)
        self.assertEqual(r.platform, "devto")
        self.assertTrue(r.success)
        self.assertEqual(r.url, "")
        self.assertEqual(r.post_id, "")
        self.assertEqual(r.error, "")

    def test_publish_result_to_dict(self):
        from districts.content.blog_publisher import PublishResult
        r = PublishResult(platform="medium", success=False, error="token missing")
        d = r.to_dict()
        self.assertEqual(d["platform"], "medium")
        self.assertFalse(d["success"])
        self.assertEqual(d["error"], "token missing")
        self.assertIn("url", d)
        self.assertIn("post_id", d)


class TestBlogPublisherDevTo(unittest.TestCase):
    def _pub(self):
        from districts.content.blog_publisher import BlogPublisher
        return BlogPublisher()

    def test_no_key_returns_error(self):
        p = self._pub()
        p._devto_key = ""
        r = p.publish_devto("Test", "# Hello")
        self.assertEqual(r.platform, "devto")
        self.assertFalse(r.success)
        self.assertIn("DEVTO_API_KEY", r.error)

    def test_no_httpx_returns_error(self):
        p = self._pub()
        p._devto_key = "fake_key"
        import districts.content.blog_publisher as bp_mod
        orig = bp_mod._HTTPX_AVAILABLE
        try:
            bp_mod._HTTPX_AVAILABLE = False
            r = p.publish_devto("Test", "# Hello")
            self.assertFalse(r.success)
            self.assertIn("httpx", r.error)
        finally:
            bp_mod._HTTPX_AVAILABLE = orig

    def test_successful_publish_mock(self):
        p = self._pub()
        p._devto_key = "fake_key"
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 123, "url": "https://dev.to/user/article-slug"}
        try:
            import httpx
            with patch("httpx.post", return_value=mock_resp):
                r = p.publish_devto("My Title", "# Content", tags=["python", "ai"])
            self.assertTrue(r.success)
            self.assertEqual(r.platform, "devto")
            self.assertIn("dev.to", r.url)
            self.assertEqual(r.post_id, "123")
        except ImportError:
            self.skipTest("httpx not installed")

    def test_api_error_returns_error(self):
        p = self._pub()
        p._devto_key = "fake_key"
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.text = "Unprocessable"
        try:
            import httpx
            with patch("httpx.post", return_value=mock_resp):
                r = p.publish_devto("Test", "# Hello")
            self.assertFalse(r.success)
            self.assertIn("422", r.error)
        except ImportError:
            self.skipTest("httpx not installed")

    def test_tags_capped_at_4(self):
        p = self._pub()
        p._devto_key = "fake_key"
        captured = {}
        def fake_post(url, *, json=None, headers=None, timeout=None):
            captured["json"] = json
            m = MagicMock()
            m.status_code = 201
            m.json.return_value = {"id": 1, "url": "https://dev.to/x"}
            return m
        try:
            import httpx
            with patch("httpx.post", side_effect=fake_post):
                p.publish_devto("T", "c", tags=["a", "b", "c", "d", "e"])
            self.assertLessEqual(len(captured["json"]["article"]["tags"]), 4)
        except ImportError:
            self.skipTest("httpx not installed")

    def test_exception_returns_error(self):
        p = self._pub()
        p._devto_key = "fake_key"
        try:
            import httpx
            with patch("httpx.post", side_effect=Exception("network error")):
                r = p.publish_devto("Test", "# Hello")
            self.assertFalse(r.success)
            self.assertIn("network error", r.error)
        except ImportError:
            self.skipTest("httpx not installed")


class TestBlogPublisherHashnode(unittest.TestCase):
    def _pub(self):
        from districts.content.blog_publisher import BlogPublisher
        return BlogPublisher()

    def test_no_token_returns_error(self):
        p = self._pub()
        p._hashnode_token = ""
        r = p.publish_hashnode("Test", "# Hello")
        self.assertFalse(r.success)
        self.assertIn("HASHNODE_TOKEN", r.error)

    def test_no_pub_id_returns_error(self):
        p = self._pub()
        p._hashnode_token = "tok"
        p._hashnode_pub_id = ""
        r = p.publish_hashnode("Test", "# Hello")
        self.assertFalse(r.success)
        self.assertIn("HASHNODE_PUBLICATION_ID", r.error)

    def test_successful_publish_mock(self):
        p = self._pub()
        p._hashnode_token = "fake_tok"
        p._hashnode_pub_id = "pub_id_123"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"publishPost": {"post": {"id": "post_abc", "url": "https://myblog.hashnode.dev/slug", "title": "My Title"}}}
        }
        try:
            import httpx
            with patch("httpx.post", return_value=mock_resp):
                r = p.publish_hashnode("My Title", "# Content", tags=["python"])
            self.assertTrue(r.success)
            self.assertEqual(r.platform, "hashnode")
            self.assertIn("hashnode", r.url)
            self.assertEqual(r.post_id, "post_abc")
        except ImportError:
            self.skipTest("httpx not installed")

    def test_graphql_errors_returns_error(self):
        p = self._pub()
        p._hashnode_token = "tok"
        p._hashnode_pub_id = "pub"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"errors": [{"message": "Invalid token"}]}
        try:
            import httpx
            with patch("httpx.post", return_value=mock_resp):
                r = p.publish_hashnode("Test", "# Hello")
            self.assertFalse(r.success)
            self.assertIn("Invalid token", r.error)
        except ImportError:
            self.skipTest("httpx not installed")


class TestBlogPublisherMedium(unittest.TestCase):
    def _pub(self):
        from districts.content.blog_publisher import BlogPublisher
        return BlogPublisher()

    def test_no_token_returns_error(self):
        p = self._pub()
        p._medium_token = ""
        r = p.publish_medium("Test", "# Hello")
        self.assertFalse(r.success)
        self.assertIn("MEDIUM_TOKEN", r.error)

    def test_get_me_failure_returns_error(self):
        p = self._pub()
        p._medium_token = "fake_token"
        mock_me = MagicMock()
        mock_me.status_code = 401
        try:
            import httpx
            with patch("httpx.get", return_value=mock_me):
                r = p.publish_medium("Test", "# Hello")
            self.assertFalse(r.success)
            self.assertIn("user", r.error.lower())
        except ImportError:
            self.skipTest("httpx not installed")

    def test_successful_publish_mock(self):
        p = self._pub()
        p._medium_token = "fake_token"
        mock_me = MagicMock()
        mock_me.status_code = 200
        mock_me.json.return_value = {"data": {"id": "user_abc"}}
        mock_post = MagicMock()
        mock_post.status_code = 201
        mock_post.json.return_value = {"data": {"id": "post_xyz", "url": "https://medium.com/@user/slug"}}
        try:
            import httpx
            with patch("httpx.get", return_value=mock_me), \
                 patch("httpx.post", return_value=mock_post):
                r = p.publish_medium("Title", "# Content", tags=["ai"])
            self.assertTrue(r.success)
            self.assertEqual(r.platform, "medium")
            self.assertIn("medium.com", r.url)
            self.assertEqual(r.post_id, "post_xyz")
        except ImportError:
            self.skipTest("httpx not installed")

    def test_tags_capped_at_5(self):
        p = self._pub()
        p._medium_token = "tok"
        captured = {}
        def fake_post(url, *, json=None, headers=None, timeout=None):
            captured["json"] = json
            m = MagicMock()
            m.status_code = 201
            m.json.return_value = {"data": {"id": "1", "url": "https://medium.com/x"}}
            return m
        def fake_get(url, *, headers=None, timeout=None):
            m = MagicMock()
            m.status_code = 200
            m.json.return_value = {"data": {"id": "uid"}}
            return m
        try:
            import httpx
            with patch("httpx.get", side_effect=fake_get), \
                 patch("httpx.post", side_effect=fake_post):
                p.publish_medium("T", "c", tags=["a", "b", "c", "d", "e", "f"])
            self.assertLessEqual(len(captured["json"]["tags"]), 5)
        except ImportError:
            self.skipTest("httpx not installed")


class TestBlogPublisherPublishAll(unittest.TestCase):
    def _pub(self):
        from districts.content.blog_publisher import BlogPublisher
        return BlogPublisher()

    def test_no_keys_all_fail_gracefully(self):
        p = self._pub()
        p._devto_key = ""
        p._hashnode_token = ""
        p._medium_token = ""
        results = p.publish_all("Test", "# Hello", tags=["python"])
        self.assertEqual(len(results), 3)
        self.assertTrue(all(not r.success for r in results))

    def test_platform_filter(self):
        p = self._pub()
        p._devto_key = ""
        p._hashnode_token = ""
        p._medium_token = ""
        results = p.publish_all("Test", "# Hello", platforms=["devto"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].platform, "devto")

    def test_platform_filter_two(self):
        p = self._pub()
        p._devto_key = ""
        p._hashnode_token = ""
        results = p.publish_all("Test", "# Hello", platforms=["devto", "hashnode"])
        self.assertEqual(len(results), 2)
        platforms = {r.platform for r in results}
        self.assertEqual(platforms, {"devto", "hashnode"})

    def test_all_platforms_default(self):
        p = self._pub()
        p._devto_key = ""
        p._hashnode_token = ""
        p._medium_token = ""
        results = p.publish_all("Test", "# Hello")
        platforms = {r.platform for r in results}
        self.assertEqual(platforms, {"devto", "hashnode", "medium"})

    def test_partial_success_skips_unconfigured(self):
        p = self._pub()
        p._devto_key = "fake_key"
        p._hashnode_token = ""
        p._medium_token = ""
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 1, "url": "https://dev.to/x"}
        try:
            import httpx
            with patch("httpx.post", return_value=mock_resp):
                results = p.publish_all("Test", "# Hello", platforms=["devto", "hashnode"])
            devto_result = next(r for r in results if r.platform == "devto")
            hashnode_result = next(r for r in results if r.platform == "hashnode")
            self.assertTrue(devto_result.success)
            self.assertFalse(hashnode_result.success)
        except ImportError:
            self.skipTest("httpx not installed")


# ── Post Job Tracker ───────────────────────────────────────────────────────────

class TestJobStatusEnum(unittest.TestCase):
    def test_values(self):
        from districts.content.post_job import JobStatus
        self.assertEqual(JobStatus.PENDING, "pending")
        self.assertEqual(JobStatus.PUBLISHING, "publishing")
        self.assertEqual(JobStatus.PUBLISHED, "published")
        self.assertEqual(JobStatus.RETRYING, "retrying")
        self.assertEqual(JobStatus.FAILED, "failed")
        self.assertEqual(JobStatus.CANCELLED, "cancelled")


class TestPostJobDataclass(unittest.TestCase):
    def test_can_retry_true(self):
        from districts.content.post_job import PostJob, JobStatus
        job = PostJob(job_id="j1", platform="youtube", title="T", status=JobStatus.RETRYING,
                      payload={}, attempt_count=1, max_retries=3)
        self.assertTrue(job.can_retry)

    def test_can_retry_false_at_limit(self):
        from districts.content.post_job import PostJob, JobStatus
        job = PostJob(job_id="j1", platform="youtube", title="T", status=JobStatus.RETRYING,
                      payload={}, attempt_count=3, max_retries=3)
        self.assertFalse(job.can_retry)

    def test_is_terminal_published(self):
        from districts.content.post_job import PostJob, JobStatus
        job = PostJob(job_id="j1", platform="youtube", title="T",
                      status=JobStatus.PUBLISHED, payload={})
        self.assertTrue(job.is_terminal)

    def test_is_terminal_failed(self):
        from districts.content.post_job import PostJob, JobStatus
        job = PostJob(job_id="j1", platform="youtube", title="T",
                      status=JobStatus.FAILED, payload={})
        self.assertTrue(job.is_terminal)

    def test_is_terminal_cancelled(self):
        from districts.content.post_job import PostJob, JobStatus
        job = PostJob(job_id="j1", platform="youtube", title="T",
                      status=JobStatus.CANCELLED, payload={})
        self.assertTrue(job.is_terminal)

    def test_is_not_terminal_pending(self):
        from districts.content.post_job import PostJob, JobStatus
        job = PostJob(job_id="j1", platform="youtube", title="T",
                      status=JobStatus.PENDING, payload={})
        self.assertFalse(job.is_terminal)

    def test_to_dict(self):
        from districts.content.post_job import PostJob, JobStatus
        job = PostJob(job_id="j1", platform="youtube", title="T",
                      status=JobStatus.PENDING, payload={"key": "val"})
        d = job.to_dict()
        self.assertEqual(d["job_id"], "j1")
        self.assertEqual(d["platform"], "youtube")
        self.assertIn("error_log", d)
        self.assertIn("metrics", d)
        self.assertIn("created_at", d)


class TestPostJobTracker(unittest.TestCase):
    def _tracker(self):
        from districts.content.post_job import PostJobTracker
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        return PostJobTracker(db_path=Path(self._tmp.name) / "jobs.db")

    def tearDown(self):
        import gc
        gc.collect()  # flush SQLite WAL connections before cleanup (Windows WAL lock)
        if hasattr(self, "_tmp"):
            self._tmp.cleanup()

    def test_create_returns_uuid_string(self):
        t = self._tracker()
        jid = t.create("youtube", "Test Video")
        self.assertIsInstance(jid, str)
        self.assertEqual(len(jid), 36)  # UUID4 format

    def test_create_job_is_pending(self):
        from districts.content.post_job import JobStatus
        t = self._tracker()
        jid = t.create("youtube", "Test Video", {"video_id": "abc"})
        job = t.get(jid)
        self.assertIsNotNone(job)
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.platform, "youtube")
        self.assertEqual(job.title, "Test Video")
        self.assertEqual(job.payload["video_id"], "abc")

    def test_get_nonexistent_returns_none(self):
        t = self._tracker()
        self.assertIsNone(t.get("nonexistent-id"))

    def test_mark_publishing_increments_attempt(self):
        from districts.content.post_job import JobStatus
        t = self._tracker()
        jid = t.create("youtube", "Test")
        t.mark_publishing(jid)
        job = t.get(jid)
        self.assertEqual(job.status, JobStatus.PUBLISHING)
        self.assertEqual(job.attempt_count, 1)

    def test_mark_published_sets_url(self):
        from districts.content.post_job import JobStatus
        t = self._tracker()
        jid = t.create("youtube", "Test")
        t.mark_publishing(jid)
        t.mark_published(jid, url="https://youtube.com/watch?v=abc", metrics={"views": 0})
        job = t.get(jid)
        self.assertEqual(job.status, JobStatus.PUBLISHED)
        self.assertEqual(job.url, "https://youtube.com/watch?v=abc")
        self.assertNotEqual(job.published_at, "")

    def test_mark_failed_appends_error(self):
        from districts.content.post_job import JobStatus
        t = self._tracker()
        jid = t.create("instagram", "Post")
        t.mark_failed(jid, error="API rate limit exceeded")
        job = t.get(jid)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(len(job.error_log), 1)
        self.assertIn("API rate limit exceeded", job.error_log[0])

    def test_mark_retrying_transitions_state(self):
        from districts.content.post_job import JobStatus
        t = self._tracker()
        jid = t.create("instagram", "Post", max_retries=3)
        t.mark_publishing(jid)  # attempt_count=1
        t.mark_retrying(jid, error="timeout")
        job = t.get(jid)
        self.assertEqual(job.status, JobStatus.RETRYING)
        self.assertEqual(len(job.error_log), 1)

    def test_mark_retrying_auto_fails_on_exhaustion(self):
        from districts.content.post_job import JobStatus
        t = self._tracker()
        jid = t.create("instagram", "Post", max_retries=2)
        t.mark_publishing(jid)   # attempt 1
        t.mark_retrying(jid, error="error 1")
        t.mark_publishing(jid)   # attempt 2
        t.mark_retrying(jid, error="error 2")
        job = t.get(jid)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(len(job.error_log), 2)

    def test_cancel_transitions_to_cancelled(self):
        from districts.content.post_job import JobStatus
        t = self._tracker()
        jid = t.create("twitter", "Tweet")
        t.cancel(jid)
        job = t.get(jid)
        self.assertEqual(job.status, JobStatus.CANCELLED)

    def test_update_metrics_merges(self):
        t = self._tracker()
        jid = t.create("youtube", "Test")
        t.mark_publishing(jid)
        t.mark_published(jid, url="https://yt.com", metrics={"views": 0})
        t.update_metrics(jid, {"views": 1500, "likes": 50})
        job = t.get(jid)
        self.assertEqual(job.metrics["views"], 1500)
        self.assertEqual(job.metrics["likes"], 50)

    def test_list_pending_returns_pending_and_retrying(self):
        from districts.content.post_job import JobStatus
        t = self._tracker()
        jid1 = t.create("youtube", "Video 1")  # pending
        jid2 = t.create("instagram", "Post 1", max_retries=3)
        t.mark_publishing(jid2)
        t.mark_retrying(jid2)  # retrying
        jid3 = t.create("youtube", "Video 2")
        t.mark_publishing(jid3)
        t.mark_published(jid3, url="https://yt.com")  # published

        pending = t.list_pending()
        pending_ids = {j.job_id for j in pending}
        self.assertIn(jid1, pending_ids)
        self.assertIn(jid2, pending_ids)
        self.assertNotIn(jid3, pending_ids)

    def test_list_by_status_published(self):
        from districts.content.post_job import JobStatus
        t = self._tracker()
        jid = t.create("youtube", "Vid")
        t.mark_publishing(jid)
        t.mark_published(jid, url="https://yt.com")
        results = t.list_by_status(JobStatus.PUBLISHED)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].job_id, jid)

    def test_list_by_platform(self):
        t = self._tracker()
        t.create("youtube", "Vid 1")
        t.create("youtube", "Vid 2")
        t.create("instagram", "Post 1")
        yt = t.list_by_platform("youtube")
        self.assertEqual(len(yt), 2)
        ig = t.list_by_platform("instagram")
        self.assertEqual(len(ig), 1)

    def test_summary_counts(self):
        from districts.content.post_job import JobStatus
        t = self._tracker()
        jid1 = t.create("youtube", "Video")
        t.mark_publishing(jid1)
        t.mark_published(jid1, url="https://yt.com")

        jid2 = t.create("instagram", "Post", max_retries=1)
        t.mark_publishing(jid2)
        t.mark_retrying(jid2, error="fail")  # auto-fails (attempt=1 >= max=1)

        s = t.summary()
        self.assertEqual(s.get("published"), 1)
        self.assertEqual(s.get("failed"), 1)

    def test_error_log_max_20(self):
        t = self._tracker()
        jid = t.create("youtube", "Vid", max_retries=100)
        # mark_publishing() only claims a pending/retrying job (atomic claim
        # guard, 2026-09-30 race-condition fix); this test only exercises
        # _append_error()'s 20-entry cap, so append directly rather than
        # illegally re-claiming an already-PUBLISHING job.
        for i in range(25):
            t._append_error(jid, f"error {i}")
        job = t.get(jid)
        self.assertLessEqual(len(job.error_log), 20)

    def test_scheduled_for_stored(self):
        t = self._tracker()
        jid = t.create("youtube", "Scheduled Vid", scheduled_for="2026-06-01T10:00:00Z")
        job = t.get(jid)
        self.assertEqual(job.scheduled_for, "2026-06-01T10:00:00Z")

    def test_payload_stored_as_dict(self):
        t = self._tracker()
        payload = {"video_path": "/tmp/vid.mp4", "thumbnail": "/tmp/thumb.jpg"}
        jid = t.create("youtube", "Test", payload)
        job = t.get(jid)
        self.assertEqual(job.payload["video_path"], "/tmp/vid.mp4")
        self.assertEqual(job.payload["thumbnail"], "/tmp/thumb.jpg")

    def test_mark_retrying_nonexistent_no_crash(self):
        t = self._tracker()
        t.mark_retrying("nonexistent-id", error="oops")  # should not raise

    def test_multiple_jobs_independent(self):
        from districts.content.post_job import JobStatus
        t = self._tracker()
        jid1 = t.create("youtube", "Vid 1")
        jid2 = t.create("youtube", "Vid 2")
        t.mark_publishing(jid1)
        t.mark_published(jid1, url="https://yt.com/1")
        job1 = t.get(jid1)
        job2 = t.get(jid2)
        self.assertEqual(job1.status, JobStatus.PUBLISHED)
        self.assertEqual(job2.status, JobStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
