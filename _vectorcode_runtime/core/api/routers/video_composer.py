"""Video composer router — /video/compositions."""

import sys

__all__ = [
    "router",
    "video_compositions",
]


from fastapi import APIRouter
from loguru import logger
from pathlib import Path

router = APIRouter(prefix="/video", tags=["video"])

@router.get("/compositions")
async def video_compositions():
    """List HTML composition files in studio directory."""
    try:
        studio_dir = Path.home() / ".vector" / "studio"
        if not studio_dir.exists():
            return {"total_compositions": 0, "compositions": []}
        files = sorted(f.name for f in studio_dir.iterdir() if f.suffix == ".html")
        return {"total_compositions": len(files), "compositions": files}
    except Exception as e:
        logger.warning(f"[VECTOR][api][video] compositions failed: {e}")
        return {"total_compositions": 0, "compositions": []}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ video_composer.py OK")
