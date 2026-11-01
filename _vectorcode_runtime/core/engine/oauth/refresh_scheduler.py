"""
VECTOR OAuth Refresh Scheduler — proactive background token refresh.

Checks all stored tokens every 30 minutes and refreshes any that
will expire within the next 60 minutes. Uses APScheduler (already
in VECTOR's requirements). Non-blocking: failures are logged, never raised.
"""
from __future__ import annotations

__all__ = [
    "OAuthRefreshScheduler",
    "start_scheduler",
    "stop_scheduler",
]


from loguru import logger

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    _APSCHEDULER_AVAILABLE = True
except ImportError:
    _APSCHEDULER_AVAILABLE = False


_scheduler: "BackgroundScheduler | None" = None


def _refresh_job() -> None:
    """APScheduler job: refresh all tokens expiring within 60 minutes."""
    try:
        from core.engine.oauth.flows import OAuthFlowManager
        mgr = OAuthFlowManager()
        refreshed = mgr.refresh_expiring_tokens(threshold_minutes=60)
        if refreshed:
            logger.info("[VECTOR][oauth-scheduler] refreshed {} token(s): {}",
                        len(refreshed), refreshed)
        else:
            logger.debug("[VECTOR][oauth-scheduler] checked tokens — all valid")
    except Exception as e:
        logger.warning("[VECTOR][oauth-scheduler] refresh job error: {}", e)


class OAuthRefreshScheduler:
    """
    Wraps APScheduler to run proactive OAuth token refreshes.
    Can be used as a context manager or started/stopped manually.
    """

    def __init__(self, interval_minutes: int = 30) -> None:
        self._interval = interval_minutes
        self._scheduler: "BackgroundScheduler | None" = None

    def start(self) -> None:
        if not _APSCHEDULER_AVAILABLE:
            logger.warning("[VECTOR][oauth-scheduler] APScheduler not installed — "
                           "proactive token refresh disabled (pip install apscheduler)")
            return
        if self._scheduler and self._scheduler.running:
            return
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(
            _refresh_job,
            trigger="interval",
            minutes=self._interval,
            id="oauth_refresh",
            replace_existing=True,
            max_instances=1,
        )
        self._scheduler.start()
        logger.info("[VECTOR][oauth-scheduler] started — checking every {}min", self._interval)

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("[VECTOR][oauth-scheduler] stopped")

    def __enter__(self) -> "OAuthRefreshScheduler":
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.stop()

    def run_now(self) -> None:
        """Trigger a refresh check immediately (for testing / manual runs)."""
        _refresh_job()


_global_scheduler: OAuthRefreshScheduler | None = None


def start_scheduler(interval_minutes: int = 30) -> OAuthRefreshScheduler:
    """Start the global background refresh scheduler (idempotent)."""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = OAuthRefreshScheduler(interval_minutes)
    _global_scheduler.start()
    return _global_scheduler


def stop_scheduler() -> None:
    """Stop the global background refresh scheduler."""
    global _global_scheduler
    if _global_scheduler:
        _global_scheduler.stop()
        _global_scheduler = None


if __name__ == "__main__":
    import time
    if _APSCHEDULER_AVAILABLE:
        sched = OAuthRefreshScheduler(interval_minutes=30)
        sched.start()
        assert sched._scheduler is not None and sched._scheduler.running
        sched.stop()
        print("OK oauth/refresh_scheduler.py — scheduler start/stop verified")
    else:
        sched = OAuthRefreshScheduler()
        sched.start()   # should log warning, not crash
        print("OK oauth/refresh_scheduler.py — degraded mode (apscheduler not installed)")
