"""Loop router — /loop/status."""

import sys
import datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter
from loguru import logger

from core.api.schemas import LoopStatusResponse

router = APIRouter(prefix="/loop", tags=["loop"])

_loop_instance = None

def _get_loop():
    global _loop_instance
    if _loop_instance is None:
        try:
            from core.loop.autonomous_loop import AutonomousLoop
            _loop_instance = AutonomousLoop()
        except Exception as e:
            logger.warning(f"[VECTOR][api][loop] failed to create AutonomousLoop: {e}")
    return _loop_instance

@router.get("/status", response_model=LoopStatusResponse)
async def loop_status():
    try:
        loop = _get_loop()
        if loop is None:
            return LoopStatusResponse(
                running=False, tick_count=0, uptime_seconds=0,
                guard_violations=[], task_queue_depth=0,
            )
        running = getattr(loop, "_running", False)
        tick_count = getattr(loop, "_tick_count", 0)
        uptime = 0
        start = getattr(loop, "_start_time", None)
        if start:
            uptime = int((dt.datetime.now(dt.timezone.utc) - start).total_seconds())
        guard_violations = []
        task_queue_depth = 0
        try:
            from core.loop.task_queue import TaskQueue
            tq = TaskQueue.get()
            task_queue_depth = len(getattr(tq, "_tasks", []))
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)
        return LoopStatusResponse(
            running=running, tick_count=tick_count, uptime_seconds=uptime,
            guard_violations=guard_violations, task_queue_depth=task_queue_depth,
        )
    except Exception as e:
        logger.warning(f"[VECTOR][api][loop] status failed: {e}")
        return LoopStatusResponse(
            running=False, tick_count=0, uptime_seconds=0,
            guard_violations=[], task_queue_depth=0,
        )

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ loop.py OK")
