"""Nudge router — /nudge endpoints."""

import sys

__all__ = [
    "nudge_dismiss",
    "nudge_latest",
    "router",
]


from fastapi import APIRouter

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
