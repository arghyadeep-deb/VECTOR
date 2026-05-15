# VECTOR-INGESTED MODULE
# Source: github/open-jarvis/OpenJarvis/src/openjarvis/connectors/__init__.py
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Data source connectors for Deep Research."""

from vectorcode.src.connectors._stubs import (
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
    import vector.connectors.gmail  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.gmail_imap  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.gdrive  # noqa: F401
except ImportError:
    pass  # httpx may not be installed

try:
    import vector.connectors.notion  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.granola  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.gcontacts  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.imessage  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.apple_notes  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.apple_music  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.apple_contacts  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.slack_connector  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.outlook  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.gcalendar  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.dropbox  # noqa: F401
except ImportError:
    pass  # httpx may not be installed

try:
    import vector.connectors.whatsapp  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.oura  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.apple_health  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.strava  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.spotify  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.google_tasks  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.weather  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.github_notifications  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.hackernews  # noqa: F401
except ImportError:
    pass

try:
    import vector.connectors.news_rss  # noqa: F401
except ImportError:
    pass
