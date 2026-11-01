"""
Research Library Module - PDF Download and Management System

This module provides functionality for:
- Downloading PDFs from research sources
- Managing a local library of downloaded documents
- Tracking download status and deduplication
- Providing UI for library browsing and download management
"""

from .services.download_service import DownloadService
from .services.library_service import LibraryService
from .services.library_rag_service import LibraryRAGService

# The Flask blueprints below belong to a parallel Flask web app this absorbed
# subsystem originally shipped with (auth, UI routes) -- VECTOR never needed
# it (it has its own FastAPI app + HUD) and that `web.auth` layer was never
# rebuilt (see docs/repo_analysis/_MASTER_TODO.md §3 item 12). Guarded so the
# real, needed pieces above (DownloadService/LibraryService/LibraryRAGService)
# stay importable regardless.
try:
    from .routes.library_routes import library_bp
    from .routes.rag_routes import rag_bp
    from .deletion.routes import delete_bp
    from .search import search_bp
except ImportError:
    library_bp = rag_bp = delete_bp = search_bp = None  # type: ignore

__all__ = [
    "DownloadService",
    "LibraryService",
    "LibraryRAGService",
    "library_bp",
    "rag_bp",
    "delete_bp",
    "search_bp",
]
