"""Migration router — /migration/sources."""

import sys

__all__ = [
    "migration_sources",
    "router",
]


from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/migration", tags=["migration"])

@router.get("/sources")
async def migration_sources():
    """Get supported migration source frameworks."""
    try:
        from core.migration.importer import MigrationSource
        sources = [s.value for s in MigrationSource]
        return {"sources": sources, "total_sources": len(sources)}
    except Exception as e:
        logger.warning(f"[VECTOR][api][migration] sources failed: {e}")
        return {"sources": [], "total_sources": 0}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ migration.py OK")
