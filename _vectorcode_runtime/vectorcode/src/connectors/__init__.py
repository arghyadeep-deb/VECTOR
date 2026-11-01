# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Data source connectors for Deep Research."""

from loguru import logger
from vectorcode.src.connectors._abc import (
    Attachment,
    BaseConnector,
    Document,
    SyncStatus,
)
from vectorcode.src.connectors.store import KnowledgeStore

__all__ = ["Attachment", "BaseConnector", "Document", "KnowledgeStore", "SyncStatus"]

# Auto-register built-in connectors
import vectorcode.src.connectors.obsidian  # noqa: F401

try:
    import vectorcode.src.connectors.gmail  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.gmail_imap  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.gdrive  # noqa: F401
except ImportError:
    pass  # httpx may not be installed

try:
    import vectorcode.src.connectors.notion  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.granola  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.gcontacts  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.imessage  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.apple_notes  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.apple_music  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.apple_contacts  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.slack_connector  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.outlook  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.gcalendar  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.dropbox  # noqa: F401
except ImportError:
    pass  # httpx may not be installed

try:
    import vectorcode.src.connectors.whatsapp  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.oura  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.apple_health  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.strava  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.spotify  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.google_tasks  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.weather  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.github_notifications  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.hackernews  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.connectors.news_rss  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")
