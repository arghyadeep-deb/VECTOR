"""Slack daemon channel shim -- re-exports from comms.slack_daemon."""
from loguru import logger

try:
    from vectorcode.src.comms.slack_daemon import *
except ImportError as exc:
    _IMPORT_ERROR = exc
    logger.debug("[VECTOR] Slack daemon unavailable: {}", exc)

    def _unavailable(*args, **kwargs):
        raise RuntimeError(
            "Slack daemon is unavailable because vectorcode.src.comms.slack_daemon "
            "could not be imported"
        ) from _IMPORT_ERROR

    run_slack_daemon = _unavailable
    start_slack_daemon = _unavailable
    stop_daemon = _unavailable

    def is_running() -> bool:
        return False
