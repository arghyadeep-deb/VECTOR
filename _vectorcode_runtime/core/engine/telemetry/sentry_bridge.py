"""
VECTOR Sentry Bridge — error tracking and performance monitoring.

Verdict vs VECTOR's loguru:
- loguru: local structured logs (KEEP — excellent for dev)
- Sentry: cloud error aggregation, alerting, performance tracing (ADD for production)

Both coexist. Loguru handles local debug. Sentry handles cloud alerts.
Set SENTRY_DSN in .env to activate (leave empty for local-only mode).
"""
from __future__ import annotations

__all__ = [
    "init_sentry",
    "VectorSentry",
]


from loguru import logger
from core.config import CONFIG

_SENTRY_DSN = CONFIG.get("sentry_dsn", "")
_SENTRY_ENV = CONFIG.get("sentry_env", "local")
_SENTRY_RELEASE = CONFIG.get("build_sha", "dev")


class VectorSentry:
    """
    Sentry integration for VECTOR — cloud-mode error tracking.

    Local mode (no DSN): logs to loguru only.
    Cloud mode (DSN set): sends errors + performance data to Sentry.
    """

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or _SENTRY_DSN
        self._active = False
        if self._dsn:
            self._init()

    def _init(self) -> None:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.logging import LoggingIntegration
            import logging

            sentry_sdk.init(
                dsn=self._dsn,
                environment=_SENTRY_ENV,
                release=f"vector@{_SENTRY_RELEASE}",
                traces_sample_rate=0.1,        # 10% of transactions traced
                profiles_sample_rate=0.1,
                integrations=[
                    LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
                ],
                before_send=self._scrub_secrets,
                attach_stacktrace=True,
                send_default_pii=False,          # VECTOR privacy rule
            )
            self._active = True
            logger.info("[VECTOR][sentry] initialized (env={})", _SENTRY_ENV)
        except ImportError:
            logger.info("[VECTOR][sentry] sentry-sdk not installed. "
                        "Run: pip install sentry-sdk to enable cloud error tracking.")
        except Exception as e:
            logger.warning("[VECTOR][sentry] init failed: {}", e)

    @staticmethod
    def _scrub_secrets(event: dict, hint: dict) -> dict | None:
        """Remove sensitive data before sending to Sentry."""
        _SENSITIVE = {"api_key", "password", "token", "secret", "credential", "key"}
        def _scrub(obj):
            if isinstance(obj, dict):
                return {k: "[REDACTED]" if any(s in k.lower() for s in _SENSITIVE) else _scrub(v)
                        for k, v in obj.items()}
            if isinstance(obj, list):
                return [_scrub(i) for i in obj]
            return obj
        return _scrub(event)

    def capture_exception(self, error: Exception, context: dict | None = None) -> str | None:
        """Capture an exception. Returns Sentry event ID if active."""
        if self._active:
            try:
                import sentry_sdk
                with sentry_sdk.push_scope() as scope:
                    if context:
                        for k, v in context.items():
                            scope.set_extra(k, v)
                    event_id = sentry_sdk.capture_exception(error)
                    logger.error("[VECTOR][sentry] captured: {} (id={})", type(error).__name__, event_id)
                    return event_id
            except Exception: logger.debug("[VECTOR][sentry] sentry_bridge exception (suppressed)")
        logger.error("[VECTOR][sentry][local] {}: {}", type(error).__name__, error)
        return None

    def capture_message(self, message: str, level: str = "info", context: dict | None = None) -> None:
        """Capture a message event."""
        if self._active:
            try:
                import sentry_sdk
                with sentry_sdk.push_scope() as scope:
                    if context:
                        for k, v in context.items():
                            scope.set_extra(k, v)
                    sentry_sdk.capture_message(message, level=level)
            except Exception: logger.debug("[VECTOR][sentry] sentry_bridge exception (suppressed)")
        logger.log(level.upper(), "[VECTOR][sentry][local] {}", message)

    def set_user(self, user_id: str, username: str = "arghyadeep") -> None:
        """Tag events with user context."""
        if self._active:
            try:
                import sentry_sdk
                sentry_sdk.set_user({"id": user_id, "username": username})
            except Exception: logger.debug("[VECTOR][sentry] sentry_bridge exception (suppressed)")

    def set_tag(self, key: str, value: str) -> None:
        if self._active:
            try:
                import sentry_sdk
                sentry_sdk.set_tag(key, value)
            except Exception: logger.debug("[VECTOR][sentry] sentry_bridge exception (suppressed)")

    @property
    def is_active(self) -> bool:
        return self._active


_sentry: VectorSentry | None = None


def init_sentry(dsn: str | None = None) -> VectorSentry:
    global _sentry
    if _sentry is None:
        _sentry = VectorSentry(dsn=dsn)
    return _sentry


if __name__ == "__main__":
    s = VectorSentry()
    assert not s.is_active  # no DSN in test
    s.capture_message("test message")  # should log via loguru, not crash
    try:
        raise ValueError("test error")
    except ValueError as e:
        s.capture_exception(e)
    print(f"OK sentry_bridge.py — active: {s.is_active} (set SENTRY_DSN to activate)")
