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
import json
import os
import signal
import sys
import threading
import tempfile
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

def bootstrap_agents() -> int:
    """Register manifest-defined VECTOR City agents for API/loop runtime.

    Specialist agents are loaded from config/agent_manifest.yaml. If optional
    dependencies prevent a specialist from importing, a baseline AgentBase is
    registered for that district so governor-routed endpoints do not run with
    an empty district.
    """
    from core.city.agent_base import AgentBase
    from core.city.agent_registry import get_registry
    from core.city.declarative_manifest import ManifestLoader

    registry = get_registry()
    loader = ManifestLoader()
    definitions = loader.load()
    registered = loader.register_all(definitions, registry)

    districts = sorted({entry.get("district", "") for entry in definitions if entry.get("district")})
    for district in districts:
        if registry.get_by_district(district):
            continue
        agent_id = f"baseline_{district}"
        if registry.get(agent_id):
            continue
        registry.register(
            AgentBase(
                agent_id=agent_id,
                name=f"{district.replace('_', ' ').title()}Baseline",
                district=district,
            )
        )
        registered += 1

    logger.info(
        "[VECTOR][bootstrap] registered {} agents across {} manifest districts",
        registered,
        len(districts),
    )
    return registered


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

    def _venv_python(base_dir: str) -> str:
        """Return the isolated venv's python for a sidecar dir, else global 'python'.
        Sidecars run in their OWN venv so their deps never collide with VECTOR's."""
        win = os.name == "nt"
        cand = Path(base_dir) / ".venv" / ("Scripts" if win else "bin") / ("python.exe" if win else "python")
        return str(cand) if cand.exists() else "python"

    _comfy_dir = _sidecar_path("comfyui_path", "ComfyUI-master")
    _ow_back = str(Path(_sidecar_path("open_webui_path", "open-webui-main")) / "backend")

    # Portable MongoDB (for LibreChat) — bundled binary under GitHub/mongodb-portable.
    _mongo_dir = _sidecar_path("mongodb_path", "mongodb-portable")
    import glob as _glob
    _mongod = next(iter(_glob.glob(str(Path(_mongo_dir) / "**" / "mongod.exe"), recursive=True)
                        or _glob.glob(str(Path(_mongo_dir) / "**" / "bin" / "mongod"), recursive=True)), "")

    sidecars = [
        {
            "name": "MongoDB",
            # Portable mongod for LibreChat — no installer/admin needed.
            "cmd": [_mongod, "--dbpath", str(Path(_mongo_dir) / "data"),
                    "--port", "27017", "--bind_ip", "127.0.0.1"],
            "cwd": _mongo_dir,
            "health_url": "",  # native protocol, no HTTP health
            "skip_cwd_check": True,
            "requires_binary": _mongod,  # skip cleanly if the portable mongod isn't present
        },
        {
            "name": "ComfyUI",
            # Runs in ComfyUI's isolated .venv (created by setup) — falls back to
            # global python if that venv isn't present.
            "cmd": [_venv_python(_comfy_dir), "main.py", "--port", "8188", "--listen", "127.0.0.1"],
            "cwd": _comfy_dir,
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
            # Runs from the cloned repo's backend dir in its OWN isolated .venv,
            # where the `open_webui` module + its deps live (no global pip install).
            "cmd": [_venv_python(_ow_back), "-m", "uvicorn", "open_webui.main:app",
                    "--host", "127.0.0.1", "--port", "8080"],
            "cwd": _ow_back,
            "health_url": "http://127.0.0.1:8080/health",
            "requires_subdir": ".venv",  # skip+warn until the venv is set up
            # open-webui prints a Unicode banner on startup; Windows' default
            # cp1252 console encoding can't render it and the process dies with
            # UnicodeEncodeError before the server ever binds to the port.
            "env_extra": {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        },
        {
            "name": "LibreChat",
            "cmd": ["node", "api/server/index.js"],
            # Cloned locally. Configure via VECTOR_LIBRECHAT_PATH / CONFIG["sidecars"]["librechat_path"].
            # One-time setup in that dir: `npm ci` then `npm run frontend` (build), plus a .env + MongoDB.
            "cwd": _sidecar_path("librechat_path", "LibreChat-main"),
            "env_extra": {"PORT": "3080"},
            "requires_subdir": "node_modules",  # skip with a clear warning if deps aren't installed
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
        # binary check: skip silently if a required executable isn't present
        if "requires_binary" in sidecar and not (sidecar["requires_binary"] and os.path.exists(sidecar["requires_binary"])):
            logger.info("[VECTOR][sidecars] {} skipped — binary not found", sidecar["name"])
            continue
        # dependency check: skip with a clear, actionable message if deps aren't installed
        if sidecar.get("requires_subdir"):
            dep = os.path.join(cwd, sidecar["requires_subdir"])
            if not os.path.exists(dep):
                logger.warning(
                    "[VECTOR][sidecars] {} skipped — '{}' missing. Run one-time setup in {} "
                    "(e.g. `npm ci`), then restart.",
                    sidecar["name"], sidecar["requires_subdir"], cwd,
                )
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
        choices=("loop", "api", "smoke", "doctor"),
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
    if args.mode not in ("smoke", "doctor"):
        _start_sidecars()
        _start_background_services()

    if args.mode == "api":
        run_api(args.host, args.port)
        return 0

    if args.mode == "smoke":
        os.environ.setdefault(
            "VECTOR_TEST_DATA_DIR",
            str(Path(tempfile.gettempdir()) / "vector_smoke_data"),
        )
        result = asyncio.run(smoke_test())
        print(result)
        return 0 if result.get("status") == "ok" else 1

    if args.mode == "doctor":
        from core.runtime.doctor import run_dependency_doctor

        report = run_dependency_doctor(include_optional=True).to_dict()
        print(json.dumps(report, indent=2))
        return 0 if report.get("required_failed", 1) == 0 else 1

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
