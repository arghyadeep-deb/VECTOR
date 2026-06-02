"""VECTOR local launcher.

Entry-point for the local VECTOR spine. Supports three modes:
  loop  — start the autonomous loop (default)
  api   — start the FastAPI server
  smoke — one-shot startup verification

Signal handling: SIGINT/SIGTERM trigger a graceful drain (10s max) before exit.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from loguru import logger


# ── Global exception hooks ─────────────────────────────────────────────────────

def _global_excepthook(exc_type, exc_value, exc_tb):
    """Catch unhandled exceptions that escape all try/except blocks."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical(
        "[VECTOR][unhandled] {exc_type}: {exc_value}",
        exc_type=exc_type.__name__,
        exc_value=exc_value,
    )

sys.excepthook = _global_excepthook


def _asyncio_exception_handler(loop, context):
    """Catch unhandled exceptions in async tasks."""
    exc = context.get("exception")
    msg = context.get("message", "")
    if exc:
        logger.critical(
            "[VECTOR][async-unhandled] {exc_type}: {exc} — {msg}",
            exc_type=type(exc).__name__,
            exc=exc,
            msg=msg,
        )
    else:
        logger.critical("[VECTOR][async-unhandled] {msg}", msg=msg)


# ── Graceful shutdown ──────────────────────────────────────────────────────────

async def _graceful_shutdown(loop_instance, timeout: float = 10.0) -> None:
    """Drain in-flight tasks then stop the loop cleanly.

    Sets _running=False so all while-loops exit on next iteration,
    waits up to `timeout` seconds for active tasks to finish, then
    cancels any stragglers.
    """
    logger.info(
        "[VECTOR] graceful shutdown — draining active tasks (max {}s)...", timeout
    )
    loop_instance._running = False

    try:
        async with asyncio.timeout(timeout):
            while loop_instance.active_task_count() > 0:
                await asyncio.sleep(0.5)
    except asyncio.TimeoutError:
        logger.warning(
            "[VECTOR] shutdown timeout — {} tasks still active, forcing exit",
            loop_instance.active_task_count(),
        )

    # Flush episodic DB connection if available
    try:
        from core.memory.episodic import get_db_connection
        get_db_connection().close()
    except Exception as _e:
        logger.debug("[VECTOR][shutdown] db close: {}", _e)

    # Flush loguru
    try:
        logger.complete()
    except Exception:
        pass

    logger.info("[VECTOR] shutdown complete")


# ── Signal wiring ──────────────────────────────────────────────────────────────

def _setup_signal_handlers(
    event_loop: asyncio.AbstractEventLoop,
    loop_instance,
) -> None:
    """Register SIGINT/SIGTERM. Falls back on Windows (no add_signal_handler)."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            event_loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(_graceful_shutdown(loop_instance)),
            )
        except NotImplementedError:
            # Windows does not support add_signal_handler; KeyboardInterrupt handles Ctrl+C
            pass


# ── Smoke test ─────────────────────────────────────────────────────────────────

async def smoke_test() -> dict:
    """Verify the local spine can initialize and make one decision safely."""
    from core.brain.goal_system import GoalSystem
    from core.loop.context_engine import ContextEngine
    from core.loop.decision_engine import Candidate, DecisionEngine
    from core.memory.episodic import EpisodicMemory

    memory = EpisodicMemory()
    memory.store(
        event_type="startup_smoke",
        content="VECTOR smoke test started from run_vector.py",
        tags=["startup", "smoke"],
        source="run_vector",
    )

    context_prompt = ContextEngine().session_hydration_prompt({"mode": "smoke"})
    actions = GoalSystem().generate_immediate_actions(limit=4)
    candidates = [
        Candidate(
            action_type=a["action"],
            params={"goal_id": a["goal_id"], "title": a.get("title", "")},
            goal_ids=[a["goal_id"]],
            urgency={"high": 0.9, "medium": 0.5, "low": 0.2}.get(
                a.get("urgency", "low"), 0.5
            ),
            confidence=0.7,
            source="run_vector_smoke",
        )
        for a in actions
    ]
    decision = await DecisionEngine().evaluate(candidates)
    stats = memory.get_stats()

    return {
        "status": "ok",
        "hydration_chars": len(context_prompt),
        "candidates_evaluated": decision.evaluated,
        "winner": decision.winner.action_type,
        "winner_score": decision.winner.total_score,
        "memory_stats": stats,
    }


# ── Sidecar services ───────────────────────────────────────────────────────────

def _start_sidecars() -> None:
    """Start optional sidecar services if available (non-blocking)."""
    import subprocess
    import os

    sidecars = [
        {
            "name": "ComfyUI",
            "cmd": ["python", "main.py", "--port", "8188", "--listen", "127.0.0.1"],
            "cwd": str(Path(__file__).parent.parent / "GitHub" / "ComfyUI-master"),
            "health_url": "http://127.0.0.1:8188/system_stats",
        },
    ]

    for sidecar in sidecars:
        cwd = sidecar["cwd"]
        if not os.path.exists(cwd):
            logger.info("[VECTOR][sidecars] {} not found, skipping", sidecar["name"])
            continue
        try:
            proc = subprocess.Popen(
                sidecar["cmd"],
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            logger.info("[VECTOR][sidecars] Started {} (pid={})", sidecar["name"], proc.pid)
        except Exception as e:
            logger.warning("[VECTOR][sidecars] Failed to start {}: {}", sidecar["name"], e)


# ── Loop runner ────────────────────────────────────────────────────────────────

async def run_loop() -> None:
    """Start the autonomous loop. Runs until interrupted."""
    asyncio.get_running_loop().set_exception_handler(_asyncio_exception_handler)

    from core.loop.autonomous_loop import AutonomousLoop
    loop_instance = AutonomousLoop()

    _setup_signal_handlers(asyncio.get_running_loop(), loop_instance)

    await loop_instance.run_forever()


# ── API runner ─────────────────────────────────────────────────────────────────

def run_api(host: str, port: int) -> None:
    """Start the local FastAPI server."""
    try:
        import uvicorn
        from core.api import create_app
        app = create_app()
        logger.info("[VECTOR][api] Starting server at http://{}:{}", host, port)
        uvicorn.run(app, host=host, port=port, reload=False)
    except ImportError:
        logger.error(
            "[VECTOR][api] uvicorn or core.api not available — "
            "run: pip install uvicorn"
        )


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VECTOR local launcher")
    parser.add_argument(
        "mode",
        nargs="?",
        default="loop",
        choices=("loop", "api", "smoke"),
        help="Default is loop. Use smoke for a one-shot startup check.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger.info("[VECTOR][launcher] mode={}", args.mode)

    # Start optional sidecar services (ComfyUI, etc.) — non-blocking.
    # Skipped in smoke mode to keep the startup check fast.
    if args.mode != "smoke":
        _start_sidecars()

    if args.mode == "api":
        run_api(args.host, args.port)
        return 0

    if args.mode == "smoke":
        result = asyncio.run(smoke_test())
        print(result)
        return 0 if result.get("status") == "ok" else 1

    # mode == "loop"
    try:
        asyncio.run(run_loop())
        return 0
    except KeyboardInterrupt:
        logger.info("[VECTOR][launcher] stopped by owner (KeyboardInterrupt)")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
