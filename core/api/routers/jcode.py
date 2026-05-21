"""Jupyter router — /vector-harness/sessions."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter
from loguru import logger

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
