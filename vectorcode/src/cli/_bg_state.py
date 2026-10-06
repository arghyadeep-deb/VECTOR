"""CLI shim for _bg_state."""

from loguru import logger
try:
    from vectorcode.src.vector_cli._bg_state import *
except ImportError:
    # The real get_status()/BgStatus (a dataclass with rust_extension,
    # rust_error, models, and all_ready()) come from the wildcard import
    # above. A fallback stub here previously redefined both unconditionally
    # -- even when the import succeeded -- with get_status() returning a
    # plain dict instead of a BgStatus instance. Every real caller
    # (chat_cmd.py's render_startup_banner()/NotificationDispatcher()/
    # .diff()) expects BgStatus's attributes, so this broke chat startup
    # banners and notification diffing. Do not reintroduce a stub below
    # this point.
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")
