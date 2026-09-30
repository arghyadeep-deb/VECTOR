"""
VECTOR Post Job Tracker — inspired by Postiz's Temporal workflow post state machine.

Tracks content posting jobs with status, retry count, error history, and metrics.
Postiz uses Temporal for durable state; VECTOR uses a lightweight SQLite-backed
store (same design, zero-dependency, fits the single-process architecture).

State machine:
  pending → publishing → published (success)
                       ↘ failed     (max_retries exceeded)
                       ↘ retrying   (transient error, will retry)

Usage:
    tracker = PostJobTracker()
    job_id = tracker.create("youtube", "My Video", {"video_id": "dQw4w9WgXcQ"})
    tracker.mark_publishing(job_id)
    tracker.mark_published(job_id, url="https://youtube.com/watch?v=...")
    # or on failure:
    tracker.mark_failed(job_id, error="API rate limit")
    tracker.mark_retrying(job_id)
    # query
    pending = tracker.list_pending()
    job = tracker.get(job_id)
"""

from __future__ import annotations

from core.memory.db_utils import apply_pragmas, configured_db_path
__all__ = ["PostJob", "PostJobTracker", "JobStatus"]

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG

_DATA_DIR = CONFIG.get("data_dir")
# Under pytest, VECTOR_TEST_DATA_DIR keeps test jobs out of the live queue: every job
# in the real post_jobs.db was a "Test Post" written by the test suite (2026-09-24).
_TEST_DIR = os.environ.get("VECTOR_TEST_DATA_DIR")
_DB_PATH = (Path(_TEST_DIR) if _TEST_DIR else Path(str(_DATA_DIR)) if _DATA_DIR else configured_db_path().parent) / "post_jobs.db"
_MAX_RETRIES = 3

class JobStatus(str, Enum):
    PENDING = "pending"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    RETRYING = "retrying"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class PostJob:
    job_id: str
    platform: str
    title: str
    status: str                            # JobStatus value
    payload: dict[str, Any]               # platform-specific data
    attempt_count: int = 0
    max_retries: int = _MAX_RETRIES
    created_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    scheduled_for: str = ""               # ISO UTC, empty = immediate
    published_at: str = ""
    url: str = ""
    error_log: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "platform": self.platform,
            "title": self.title,
            "status": self.status,
            "payload": self.payload,
            "attempt_count": self.attempt_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "scheduled_for": self.scheduled_for,
            "published_at": self.published_at,
            "url": self.url,
            "error_log": self.error_log,
            "metrics": self.metrics,
        }

    @property
    def can_retry(self) -> bool:
        return self.attempt_count < self.max_retries

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.PUBLISHED, JobStatus.FAILED, JobStatus.CANCELLED)

class PostJobTracker:
    """
    SQLite-backed tracker for content posting jobs.
    Thread-safe (check_same_thread=False, WAL mode, RLock).
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        apply_pragmas(conn)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            with self._lock:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS post_jobs (
                        job_id       TEXT PRIMARY KEY,
                        platform     TEXT NOT NULL,
                        title        TEXT NOT NULL,
                        status       TEXT NOT NULL DEFAULT 'pending',
                        payload      TEXT NOT NULL DEFAULT '{}',
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        max_retries  INTEGER NOT NULL DEFAULT 3,
                        created_at   TEXT NOT NULL,
                        updated_at   TEXT NOT NULL,
                        scheduled_for TEXT NOT NULL DEFAULT '',
                        published_at  TEXT NOT NULL DEFAULT '',
                        url           TEXT NOT NULL DEFAULT '',
                        error_log     TEXT NOT NULL DEFAULT '[]',
                        metrics       TEXT NOT NULL DEFAULT '{}'
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_post_jobs_status
                    ON post_jobs (status, platform)
                """)

    # ── Create ─────────────────────────────────────────────────────────────────

    def create(
        self,
        platform: str,
        title: str,
        payload: dict[str, Any] | None = None,
        *,
        scheduled_for: str = "",
        max_retries: int = _MAX_RETRIES,
        dedup_window_minutes: int = 10,
    ) -> str:
        """Create a new post job. Returns the job_id.

        2026-07-30 audit fix (idempotency): this used to unconditionally
        INSERT a brand-new row with a fresh uuid every call — no check for
        an existing pending job with the same (platform, title, payload).
        A retried schedule_post() call (network retry, or the owner asking
        twice) created two independent, both-real post_jobs rows, and
        run_pending()'s own dedup only protects against publishing the SAME
        job row twice, not against two DIFFERENT rows for the same content.
        Now: if a job with identical (platform, title, payload) is still in
        a non-terminal state (pending/publishing/retrying) and was created
        within `dedup_window_minutes`, return its existing job_id instead of
        creating a duplicate. Content genuinely re-scheduled after the
        window, or with different payload/title, still gets a new job as
        before.
        """
        payload_json = json.dumps(payload or {}, sort_keys=True)
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(minutes=dedup_window_minutes)).isoformat()
        with self._lock, self._connect() as conn:
            existing = conn.execute("""
                SELECT job_id FROM post_jobs
                WHERE platform = ? AND title = ? AND payload = ?
                  AND status IN (?, ?, ?)
                  AND created_at > ?
                ORDER BY created_at DESC LIMIT 1
            """, (
                platform, title, payload_json,
                JobStatus.PENDING, JobStatus.PUBLISHING, "retrying",
                cutoff,
            )).fetchone()
            if existing:
                logger.info(
                    "[VECTOR][post-job] duplicate schedule_post suppressed — "
                    "reusing existing job {} for {} '{}'",
                    existing["job_id"][:8], platform, title[:40],
                )
                return existing["job_id"]

            job_id = str(uuid.uuid4())
            now = datetime.now(tz=timezone.utc).isoformat()
            conn.execute("""
                INSERT INTO post_jobs
                    (job_id, platform, title, status, payload, attempt_count,
                     max_retries, created_at, updated_at, scheduled_for)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """, (
                job_id, platform, title, JobStatus.PENDING,
                payload_json, max_retries, now, now, scheduled_for,
            ))
        logger.info("[VECTOR][post-job] created {} — {} '{}'", job_id[:8], platform, title[:40])
        return job_id

    # ── State transitions ──────────────────────────────────────────────────────

    def mark_publishing(self, job_id: str) -> None:
        """Atomically claim a pending/retrying job for publication."""
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """UPDATE post_jobs
                   SET status=?, attempt_count=attempt_count+1, updated_at=?
                   WHERE job_id=? AND status IN (?, ?)""",
                (
                    JobStatus.PUBLISHING,
                    now,
                    job_id,
                    JobStatus.PENDING,
                    JobStatus.RETRYING,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"post job {job_id} is not claimable")

    def mark_published(self, job_id: str, *, url: str = "", metrics: dict | None = None) -> None:
        """Transition publishing → published."""
        self._update(job_id,
                     status=JobStatus.PUBLISHED,
                     published_at=datetime.now(tz=timezone.utc).isoformat(),
                     url=url,
                     metrics=metrics or {})
        logger.info("[VECTOR][post-job] {} published → {}", job_id[:8], url[:60])

    def mark_failed(self, job_id: str, error: str = "") -> None:
        """Transition → failed (terminal)."""
        self._append_error(job_id, error)
        self._update(job_id, status=JobStatus.FAILED)
        logger.warning("[VECTOR][post-job] {} failed: {}", job_id[:8], error[:80])

    def mark_retrying(self, job_id: str, error: str = "") -> None:
        """
        Transition → retrying (will be retried later).
        If attempt_count >= max_retries, automatically transitions to failed.
        """
        job = self.get(job_id)
        if job is None:
            return
        if error:
            self._append_error(job_id, error)
        if not job.can_retry:
            self._update(job_id, status=JobStatus.FAILED)
            logger.warning("[VECTOR][post-job] {} exhausted retries → failed", job_id[:8])
        else:
            self._update(job_id, status=JobStatus.RETRYING)
            logger.info("[VECTOR][post-job] {} → retrying (attempt {}/{})",
                        job_id[:8], job.attempt_count, job.max_retries)

    def recover_stale_publishing(self, max_age_minutes: float = 30.0) -> list[str]:
        """Move jobs stuck in PUBLISHING back to retrying (or failed if out of
        retries). A crash/restart or a cancelled approval wait mid-publish left
        one job 'publishing' forever, invisible to list_pending(). Returns the
        recovered job ids."""
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(minutes=max_age_minutes)).isoformat()
        with self._lock, self._connect() as conn:
            ids = [r["job_id"] for r in conn.execute(
                "SELECT job_id FROM post_jobs WHERE status=? AND updated_at < ?",
                (JobStatus.PUBLISHING, cutoff),
            ).fetchall()]
        for job_id in ids:
            self.mark_retrying(job_id, "interrupted mid-publish (stale 'publishing' recovered)")
        return ids

    def cancel(self, job_id: str) -> None:
        """Cancel a pending/retrying job."""
        self._update(job_id, status=JobStatus.CANCELLED)

    def update_metrics(self, job_id: str, metrics: dict[str, Any]) -> None:
        """Update post metrics after analytics retrieval."""
        job = self.get(job_id)
        if job is None:
            return
        merged = {**job.metrics, **metrics}
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE post_jobs SET metrics=?, updated_at=? WHERE job_id=?",
                (json.dumps(merged), datetime.now(tz=timezone.utc).isoformat(), job_id),
            )

    # ── Queries ────────────────────────────────────────────────────────────────

    def get(self, job_id: str) -> PostJob | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM post_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return self._row_to_job(row) if row else None

    def list_pending(self) -> list[PostJob]:
        """Return all jobs that are pending or retrying (ready to publish)."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM post_jobs WHERE status IN (?, ?) ORDER BY created_at",
                (JobStatus.PENDING, JobStatus.RETRYING),
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def list_by_status(self, status: str) -> list[PostJob]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM post_jobs WHERE status=? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def list_by_platform(self, platform: str) -> list[PostJob]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM post_jobs WHERE platform=? ORDER BY created_at DESC",
                (platform,),
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def summary(self) -> dict[str, Any]:
        """Return counts per status."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM post_jobs GROUP BY status"
            ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    # ── T10: per-platform publish visibility ─────────────────────────────────

    def status_by_title(self, title: str) -> dict[str, str]:
        """T10: for a given title, map each platform to its latest job status.
        Directly answers '1 of 2 platforms published' vs '0 of 2' — the
        partial-execution state the autonomy audit flagged as invisible.
        Returns {platform: status} for the most recent job per platform."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT platform, status, updated_at FROM post_jobs "
                "WHERE title = ? ORDER BY updated_at DESC", (title,),
            ).fetchall()
        latest: dict[str, str] = {}
        for r in rows:
            if r["platform"] not in latest:  # first row per platform = most recent
                latest[r["platform"]] = r["status"]
        return latest

    def partial_publishes(self, title: str | None = None) -> list[dict[str, Any]]:
        """T10: surface titles where some platforms published and others
        failed/cancelled — the partial-execution state that needs a compensating
        action or manual review (irreversible public side effect already live on
        the published platforms). If `title` is given, checks only that title;
        otherwise scans all titles. Returns a list of
        {title, platforms: {platform: status}, published_count, total_count}."""
        results: list[dict[str, Any]] = []
        with self._lock, self._connect() as conn:
            if title is not None:
                titles = [title]
            else:
                titles = [r["title"] for r in conn.execute(
                    "SELECT DISTINCT title FROM post_jobs"
                ).fetchall()]
            for t in titles:
                rows = conn.execute(
                    "SELECT platform, status FROM post_jobs WHERE title=? "
                    "ORDER BY updated_at DESC", (t,),
                ).fetchall()
                latest: dict[str, str] = {}
                for r in rows:
                    if r["platform"] not in latest:
                        latest[r["platform"]] = r["status"]
                if not latest:
                    continue
                published = sum(1 for s in latest.values() if s == JobStatus.PUBLISHED)
                failed = sum(1 for s in latest.values() if s in (JobStatus.FAILED, JobStatus.CANCELLED))
                # Partial = at least one published AND at least one failed/cancelled
                if published > 0 and failed > 0:
                    results.append({
                        "title": t,
                        "platforms": latest,
                        "published_count": published,
                        "total_count": len(latest),
                    })
        return results

    # ── Internals ──────────────────────────────────────────────────────────────

    def _update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        attempt_count_delta: int = 0,
        published_at: str = "",
        url: str = "",
        metrics: dict | None = None,
    ) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        parts = ["updated_at=?"]
        vals: list[Any] = [now]
        if status is not None:
            parts.append("status=?")
            vals.append(status)
        if attempt_count_delta:
            parts.append("attempt_count=attempt_count+?")
            vals.append(attempt_count_delta)
        if published_at:
            parts.append("published_at=?")
            vals.append(published_at)
        if url:
            parts.append("url=?")
            vals.append(url)
        if metrics is not None:
            parts.append("metrics=?")
            vals.append(json.dumps(metrics))
        vals.append(job_id)
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE post_jobs SET {', '.join(parts)} WHERE job_id=?", vals
            )

    def _append_error(self, job_id: str, error: str) -> None:
        if not error:
            return
        job = self.get(job_id)
        if not job:
            return
        log = job.error_log + [f"{datetime.now(tz=timezone.utc).isoformat()}: {error}"]
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE post_jobs SET error_log=?, updated_at=? WHERE job_id=?",
                (json.dumps(log[-20:]), datetime.now(tz=timezone.utc).isoformat(), job_id),
            )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> PostJob:
        return PostJob(
            job_id=row["job_id"],
            platform=row["platform"],
            title=row["title"],
            status=row["status"],
            payload=json.loads(row["payload"]),
            attempt_count=row["attempt_count"],
            max_retries=row["max_retries"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            scheduled_for=row["scheduled_for"],
            published_at=row["published_at"],
            url=row["url"],
            error_log=json.loads(row["error_log"]),
            metrics=json.loads(row["metrics"]),
        )

if __name__ == "__main__":
    import tempfile
    import shutil
    d = tempfile.mkdtemp()
    try:
        tracker = PostJobTracker(db_path=Path(d) / "test_jobs.db")

        jid = tracker.create("youtube", "My Test Video", {"video_path": "/tmp/v.mp4"})
        job = tracker.get(jid)
        assert job is not None and job.status == JobStatus.PENDING

        tracker.mark_publishing(jid)
        job = tracker.get(jid)
        assert job.status == JobStatus.PUBLISHING and job.attempt_count == 1

        tracker.mark_published(jid, url="https://youtube.com/watch?v=test", metrics={"views": 0})
        job = tracker.get(jid)
        assert job.status == JobStatus.PUBLISHED and job.url != ""

        # Retry cycle
        jid2 = tracker.create("instagram", "Post 2", max_retries=2)
        tracker.mark_publishing(jid2)
        tracker.mark_retrying(jid2, error="rate limit")
        tracker.mark_publishing(jid2)
        tracker.mark_retrying(jid2, error="rate limit again")
        # attempt_count=2 == max_retries → auto fail
        job2 = tracker.get(jid2)
        assert job2.status == JobStatus.FAILED
        assert len(job2.error_log) == 2

        s = tracker.summary()
        assert s.get("published") == 1
        assert s.get("failed") == 1

        # T10: per-platform publish visibility + partial-publish detection.
        jid_yt = tracker.create("youtube", "PartialTest", {"x": 1})
        jid_med = tracker.create("medium", "PartialTest", {"x": 1})
        tracker.mark_publishing(jid_yt); tracker.mark_published(jid_yt, url="https://yt")
        tracker.mark_publishing(jid_med); tracker.mark_failed(jid_med, error="403")
        ps = tracker.status_by_title("PartialTest")
        assert ps.get("youtube") == "published" and ps.get("medium") == "failed", ps
        partials = tracker.partial_publishes(title="PartialTest")
        assert len(partials) == 1 and partials[0]["published_count"] == 1, partials

        print("OK post_job.py — state machine, retry exhaustion, error log, per-platform visibility verified")
    finally:
        shutil.rmtree(d, ignore_errors=True)
