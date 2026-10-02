"""iMessage daemon channel shim."""

from loguru import logger
try:
    from vectorcode.src.comms.imessage_daemon import *
except ImportError as exc:
    _IMPORT_ERROR = exc
    logger.debug("[VECTOR] iMessage daemon unavailable: {}", exc)

    def _unavailable(*args, **kwargs):
        raise RuntimeError(
            "iMessage daemon is unavailable because vectorcode.src.comms.imessage_daemon "
            "could not be imported"
        ) from _IMPORT_ERROR

    poll_new_messages = _unavailable
    send_imessage = _unavailable
    run_daemon = _unavailable
    stop_daemon = _unavailable

    def is_running() -> bool:
        return False

