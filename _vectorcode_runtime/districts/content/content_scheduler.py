"""
Content Scheduler — orchestrates post_job → publishers → analytics feedback loop.
"""

import asyncio
from datetime import datetime, timezone

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

from core.config import CONFIG
from core.city.agent_base import AgentBase

class ContentScheduler(AgentBase):
    """Schedules content posts, tracks publish status, retrieves analytics."""

    def __init__(self):
        super().__init__(
            agent_id="content_scheduler_001",
            name="ContentScheduler",
            district="content",
        )
        self.capabilities = ["content", "publish", "run_pending", "schedule", "schedule_post", "summary"]
        self._tracker = None
        self._publisher = None
        self._analytics = None

    def _get_tracker(self):
        if self._tracker is None:
            from districts.content.post_job import PostJobTracker
            self._tracker = PostJobTracker()
        return self._tracker

    def _get_publisher(self):
        if self._publisher is None:
            from districts.content.blog_publisher import BlogPublisher
            self._publisher = BlogPublisher()
        return self._publisher

    def _get_analytics(self):
        if self._analytics is None:
            from districts.content.analytics_retriever import AnalyticsRetriever
            self._analytics = AnalyticsRetriever()
        return self._analytics

    async def schedule_post(
        self,
        title: str,
        content: str,
        platforms: list[str],
        scheduled_for: str = None,
    ) -> dict:
        """Schedule a post for publishing.

        Creates one PostJob per platform so each can be tracked, retried,
        and published independently.
        """
        tracker = self._get_tracker()
        scheduled_ts = scheduled_for or datetime.now(tz=timezone.utc).isoformat()
        payload = {"content": content}
        job_ids = []
        for platform in platforms:
            job_id = tracker.create(
                platform=platform,
                title=title,
                payload=payload,
                scheduled_for=scheduled_ts,
            )
            job_ids.append(job_id)

        logger.info(
            "[VECTOR][scheduler] Scheduled '{}' → {} ({} job(s))",
            title[:40],
            platforms,
            len(job_ids),
        )
        self.award_points(5, "post_scheduled")
        return {
            "job_ids": job_ids,
            "title": title,
            "platforms": platforms,
            "scheduled_for": scheduled_ts,
        }

    async def run_pending(self) -> dict:
        """Publish all pending posts and fetch analytics.

        The state transition to PUBLISHING is attempted first.  If that fails
        (e.g. the job was already claimed by a concurrent call) the job is
        skipped entirely so we never risk a duplicate publish.
        """
        tracker = self._get_tracker()
        publisher = self._get_publisher()
        try:
            tracker.recover_stale_publishing()
        except Exception:
            logger.exception("[VECTOR][scheduler] stale-publishing recovery failed")
        pending = tracker.list_pending()
        results = []
        for job in pending:
            # Atomically transition to PUBLISHING — skip if already claimed.
            try:
                tracker.mark_publishing(job.job_id)
            except Exception as e:
                logger.warning(
                    "[VECTOR][scheduler] Could not mark publishing {} ({}): {} — skipping",
                    job.job_id,
                    job.platform,
                    e,
                )
                continue  # Skip rather than risk duplicate publish.

            try:
                content = job.payload.get("content", "") if isinstance(job.payload, dict) else ""
                # RULE 3 / outward publish: posting to Dev.to/Hashnode/Medium is a
                # real, public, irreversible action. Gate RED — owner approves each
                # publish. This cron path previously bypassed the gateway entirely
                # (the content Hand gates, this scheduler did not). Fail CLOSED.
                _approved = False
                try:
                    from core.loop.permission_gateway import PermissionGateway, Action
                    _appr = await PermissionGateway().execute(Action(
                        action_type="content_publish",
                        params={
                            "summary": f"Publish '{job.title[:60]}' to {job.platform}",
                            "platform": job.platform,
                            "title": job.title,
                        },
                        proposed_by="content_scheduler",
                    ))
                    _approved = getattr(_appr, "approved", False)
                except Exception as _gw_err:
                    logger.error(
                        "[VECTOR][scheduler] gateway unavailable — NOT publishing {} ({}): {}",
                        job.job_id, job.platform, _gw_err,
                    )
                    _approved = False
                if not _approved:
                    logger.warning(
                        "[VECTOR][scheduler] publish of {} ({}) not approved — skipping",
                        job.job_id, job.platform,
                    )
                    try:
                        tracker.mark_failed(job.job_id, "owner did not approve publish")
                    except Exception:
                        logger.exception("[VECTOR] mark_failed after non-approval failed")
                    results.append({"job_id": job.job_id, "platform": job.platform, "status": "unapproved"})
                    continue
                result = await asyncio.to_thread(
                    publisher.publish_all,
                    job.title,
                    content,
                    platforms=[job.platform],
                )
                failed = [
                    item for item in result
                    if not bool(getattr(item, "success", False))
                ]
                if not result or failed:
                    errors = [str(getattr(item, "error", "") or "publish failed") for item in failed]
                    error = "; ".join(errors) if errors else "publisher returned no result"
                    tracker.mark_failed(job.job_id, error)
                    results.append({
                        "job_id": job.job_id,
                        "platform": job.platform,
                        "status": "failed",
                        "error": error,
                    })
                    self.deduct_points(5, "publish_failed")
                    continue
                tracker.mark_published(job.job_id)
                results.append({
                    "job_id": job.job_id,
                    "platform": job.platform,
                    "result": [r.to_dict() if hasattr(r, "to_dict") else str(r) for r in result],
                })
                self.award_points(10, "post_published")
            except asyncio.CancelledError:
                # An approval wait cut short by an outer timeout must not
                # strand the job in 'publishing'.
                try:
                    tracker.mark_retrying(job.job_id, "cancelled mid-publish")
                finally:
                    raise
            except Exception as e:
                logger.error(
                    "[VECTOR][scheduler] Failed to publish {} ({}): {}",
                    job.job_id,
                    job.platform,
                    e,
                )
                try:
                    tracker.mark_failed(job.job_id, str(e))
                except Exception:
                    logger.exception(
                        "[VECTOR][scheduler] Could not record publish failure for {}",
                        job.job_id,
                    )
                    pass  # Best-effort; don't let mark_failed hide the real error.
                self.deduct_points(5, "publish_failed")
        return {"published": len(results), "results": results}

    def get_summary(self) -> dict:
        """Return per-status job counts."""
        return self._get_tracker().summary()

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = ["schedule_post", "run_pending", "summary"]

        if task_type == "schedule_post":
            return await self.schedule_post(
                p.get("title", ""), p.get("content", ""),
                p.get("platforms", []), p.get("scheduled_for"),
            )
        if task_type == "run_pending":
            return await self.run_pending()
        if task_type == "summary":
            return self.get_summary()

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "what's currently scheduled to be posted this week?" previously
        # hit the bare "unhandled type" error stub. Route it to the
        # READ-ONLY, no-required-argument get_summary() — never trigger
        # schedule_post() (creates a real job) or run_pending() (PUBLISHES
        # to Dev.to/Hashnode/Medium, a RED-tier action) from unmatched free
        # text.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            return self.get_summary()

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}

if __name__ == "__main__":
    s = ContentScheduler()
    print("✅ content_scheduler OK" if s else "❌ FAILED")
