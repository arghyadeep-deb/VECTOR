"""Loop router — /loop/status."""

import sys

__all__ = [
    "loop_status",
    "router",
]

import datetime as dt

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
        # Cross-process aware (2026-07-19): the loop usually runs in a separate
        # process (`run_vector.py loop`) from this API server. Instantiating a
        # private AutonomousLoop here and reading its attrs always reported
        # running=False. loop_state.get_runtime() reads the loop's heartbeat
        # file, so it works in both single- and two-process deployments.
        from core.loop.loop_state import get_runtime
        rt = get_runtime()
        running = bool(rt.get("running"))
        tick_count = int(rt.get("tick_count", 0))
        uptime = 0
        start = rt.get("start_time")
        if start:
            try:
                start_dt = dt.datetime.fromisoformat(str(start))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=dt.timezone.utc)
                uptime = int((dt.datetime.now(dt.timezone.utc) - start_dt).total_seconds())
            except (ValueError, TypeError):
                uptime = 0
        guard_violations = []
        task_queue_depth = 0
        try:
            from core.loop.task_queue import TaskQueue
            tq = TaskQueue.get()
            task_queue_depth = len(getattr(tq, "_tasks", []))
        except Exception:
            logger.warning("[VECTOR] suppressed exception (fallback degraded)", exc_info=True)
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
