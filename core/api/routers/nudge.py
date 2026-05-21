"""Nudge router — /nudge endpoints."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/nudge", tags=["nudge"])


@router.get("/latest")
async def nudge_latest():
    from core.loop.nudge_engine import nudge_engine
    n = nudge_engine.latest
    if n:
        return n
    return {"text": None, "rule": None, "timestamp": None}


@router.post("/dismiss")
async def nudge_dismiss():
    from core.loop.nudge_engine import nudge_engine
    nudge_engine.dismiss()
    return {"status": "dismissed"}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK")
