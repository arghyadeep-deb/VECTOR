"""Jupyter router — /vector-harness/sessions."""

import sys

__all__ = [
    "router",
    "vector_harness_sessions",
]


from fastapi import APIRouter
from loguru import logger
from pathlib import Path

router = APIRouter(prefix="/vector-harness", tags=["vector-harness"])

@router.get("/sessions")
async def vector_harness_sessions():
    """Count active Jupyter sessions."""
    try:
        sessions_dir = Path.home() / ".vector_ca" / "sessions"
        if not sessions_dir.exists():
            return {"active_sessions": 0, "sessions_dir": str(sessions_dir)}
        count = len(list(sessions_dir.glob("*.json")))
        return {"active_sessions": count, "sessions_dir": str(sessions_dir)}
    except Exception as e:
        logger.warning(f"[VECTOR][api][jcode] sessions failed: {e}")
        return {"active_sessions": 0, "sessions_dir": ""}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ jcode.py OK")
