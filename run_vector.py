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
import threading
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


# ── Sidecar health check ───────────────────────────────────────────────────────

def _check_sidecar_health(name: str, health_url: str, delay: int = 5) -> None:
    """Check sidecar health after `delay` seconds and log the result."""
    import time
    import httpx
    time.sleep(delay)
    try:
        r = httpx.get(health_url, timeout=3)
        if r.status_code < 500:
            logger.info("[VECTOR][sidecars] {} health check OK: {}", name, r.status_code)
        else:
            logger.warning("[VECTOR][sidecars] {} health check FAILED: {}", name, r.status_code)
    except Exception as e:
        logger.warning("[VECTOR][sidecars] {} health check unreachable: {}", name, e)


# ── Sidecar services ───────────────────────────────────────────────────────────

def _start_sidecars() -> None:
    """Start optional sidecar services if available (non-blocking)."""
    import subprocess
    import os

    # Resolve sidecar paths: CONFIG["sidecars"] → env var (via Pydantic) → default GitHub location
    _github = Path(__file__).parent.parent / "GitHub"
    try:
        from core.config import CONFIG
        _sc = CONFIG.get("sidecars", {}) if isinstance(CONFIG, dict) else {}
    except Exception:
        _sc = {}

    def _sidecar_path(key: str, default_name: str) -> str:
        """Return configured path for a sidecar; fall back to GitHub/<default_name>."""
        override = _sc.get(key, "")
        return override if override else str(_github / default_name)

    sidecars = [
        {
            "name": "ComfyUI",
            "cmd": ["python", "main.py", "--port", "8188", "--listen", "127.0.0.1"],
            "cwd": _sidecar_path("comfyui_path", "ComfyUI-master"),
            "health_url": "http://127.0.0.1:8188/system_stats",
        },
        {
            "name": "hyperframes",
            "cmd": ["npx", "-y", "@hyperframes/producer", "--port", "7421"],
            "cwd": str(Path(__file__).parent),  # cwd doesn't matter for npx
            "health_url": "http://localhost:7421/health",
            # npx-based: skip cwd existence check; npx downloads on first run
            "skip_cwd_check": True,
        },
        {
            "name": "open-webui",
            "cmd": ["uvicorn", "open_webui.main:app", "--host", "127.0.0.1", "--port", "8080"],
            "cwd": str(Path(__file__).parent),  # runs from VECTOR root; open-webui installed via pip
            "health_url": "http://127.0.0.1:8080/health",
            # pip-based: only start if open_webui package is importable
            "python_module_check": "open_webui",
        },
        {
            "name": "LibreChat",
            "cmd": ["node", "api/server/index.js"],
            # No npm package — must be cloned locally.
            # Configure: set VECTOR_LIBRECHAT_PATH env var or CONFIG["sidecars"]["librechat_path"]
            "cwd": _sidecar_path("librechat_path", "LibreChat-main"),
            "env_extra": {"PORT": "3080"},
        },
        {
            "name": "UI-TARS",
            "cmd": ["npm", "run", "start"],
            # No npm package — must be cloned locally.
            # Configure: set VECTOR_UITARS_PATH env var or CONFIG["sidecars"]["ui_tars_path"]
            "cwd": str(Path(_sidecar_path("ui_tars_path", "UI-TARS-desktop-main")) / "apps" / "ui-tars"),
            # Electron app — no HTTP health endpoint; skip health check
            "health_url": "",
        },
    ]

    for sidecar in sidecars:
        cwd = sidecar["cwd"]
        # Python module check: skip if required pip package is not installed
        if sidecar.get("python_module_check"):
            import importlib.util
            if importlib.util.find_spec(sidecar["python_module_check"]) is None:
                logger.info(
                    "[VECTOR][sidecars] {} skipped — pip package '{}' not installed",
                    sidecar["name"], sidecar["python_module_check"],
                )
                continue
        # cwd check: skip if directory doesn't exist (unless skip_cwd_check is set)
        if not sidecar.get("skip_cwd_check") and not os.path.exists(cwd):
            logger.info("[VECTOR][sidecars] {} not found, skipping", sidecar["name"])
            continue
        try:
            env = None
            if sidecar.get("env_extra"):
                env = os.environ.copy()
                env.update(sidecar["env_extra"])
            proc = subprocess.Popen(
                sidecar["cmd"],
                cwd=cwd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            logger.info("[VECTOR][sidecars] Started {} (pid={})", sidecar["name"], proc.pid)
            if sidecar.get("health_url"):
                t = threading.Thread(
                    target=_check_sidecar_health,
                    args=(sidecar["name"], sidecar["health_url"], 5),
                    daemon=True,
                )
                t.start()
        except Exception as e:
            logger.warning("[VECTOR][sidecars] Failed to start {}: {}", sidecar["name"], e)


def _start_background_services() -> list[object]:
    """Start optional local background services that are safe behind consent gates."""
    services: list[object] = []
    try:
        from core.config import CONFIG
        cloud_cfg = CONFIG.get("cloud", {})
        brain_url = cloud_cfg.get("brain_url", "")
        if brain_url:
            from core.cloud.heartbeat import CloudBrainHeartbeat
            heartbeat = CloudBrainHeartbeat(
                brain_url=brain_url,
                api_key=cloud_cfg.get("api_key", ""),
            )
            if heartbeat.is_enabled():
                services.append(asyncio.create_task(heartbeat.start_loop()))
                logger.info("[VECTOR][background] CloudBrainHeartbeat started")

        voice_cfg = CONFIG.get("voice", {})
        ambient_enabled = bool(voice_cfg.get("ambient_enabled", False))
        if ambient_enabled:
            from core.voice.ambient_listener import AmbientListener, _save_consent
            listener = AmbientListener()
            if listener._consent_given:
                services.append(listener.start())
                logger.info("[VECTOR][background] AmbientListener started")
            else:
                _save_consent(False)
                logger.info("[VECTOR][background] AmbientListener skipped: consent not granted")
    except Exception as e:
        logger.warning("[VECTOR][background] optional service startup skipped: {}", e)
    return services


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
        from core.loop.permission_gateway import PermissionGateway
        app = create_app()
        # Wire the shared PermissionGateway singleton into app.state so that
        # all gateway router endpoints share the same pending-approvals queue.
        app.state.permission_gateway = PermissionGateway()
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
        _start_background_services()

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
        logger.info("[VECTOR][main] Ctrl+C received — graceful shutdown")
        # On Windows, add_signal_handler is not supported; handle shutdown here.
        # asyncio.run() has already torn down the event loop by this point, so
        # we create a fresh loop solely to run the drain coroutine.
        try:
            from core.loop.autonomous_loop import AutonomousLoop
            _shutdown_loop_instance = AutonomousLoop.__new__(AutonomousLoop)
            _shutdown_loop_instance._running = False

            async def _drain():
                await _graceful_shutdown(_shutdown_loop_instance, timeout=10.0)

            asyncio.run(_drain())
        except Exception as _se:
            logger.debug("[VECTOR][main] shutdown drain skipped: {}", _se)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
