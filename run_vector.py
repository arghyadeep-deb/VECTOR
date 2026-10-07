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

# Load .env before any other import so os.environ is fully populated for
# the doctor, permission gateway, and all submodule os.environ.get() calls.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).parent / ".env", override=False)
except ImportError:
    pass

from loguru import logger

from core.runtime_paths import data_path


# ── Persistent file logging ────────────────────────────────────────────────────

def _configure_file_logging(mode: str) -> int | None:
    """Add a rotating file sink so long-running modes (loop/api) survive a
    closed terminal. Without this, even a CRITICAL unhandled-exception log
    line from `_global_excepthook`/`_asyncio_exception_handler` below was
    only ever written to stderr and lost once the process's terminal went
    away — there was nothing to inspect after the fact.

    Returns the sink ID (for `logger.remove()` in tests), or None if disabled.
    """
    if os.environ.get("VECTOR_DISABLE_FILE_LOGGING", "").lower() in {"1", "true", "yes"}:
        return None

    log_path = data_path("logs", f"vector_{mode}.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return logger.add(
        str(log_path),
        rotation="10 MB",
        retention=5,
        level="INFO",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )


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
        logger.exception("[VECTOR] silent swallow")
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

    # An empty city means governor dispatches all no-op — fail the smoke so the
    # nightly self-check cron surfaces it.
    agents_registered = bootstrap_agents()

    return {
        "status": "ok" if agents_registered > 0 else "error",
        "agents_registered": agents_registered,
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

    # ComfyUI runs from the real sibling install (<repo-parent>/ComfyUI), not the
    # GitHub/ reference clone. Config override (comfyui_path) still wins if set.
    _comfy_dir = _sc.get("comfyui_path", "") or str(_github.parent / "ComfyUI")
    _ow_back = str(Path(_sidecar_path("open_webui_path", "open-webui-main")) / "backend")

    sidecars = [
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
            "name": "shadowbroker",
            # Intelligence district — real-time geo/SIGINT/flight/ship intelligence server.
            # Health endpoint is /api/health (NOT /health). Runs in-process' own venv
            # (no isolated .venv of its own, unlike the other sidecars) -- must use
            # sys.executable, not a bare "python" that may resolve to a different or
            # missing interpreter on PATH.
            "cmd": [sys.executable, "districts/intelligence/shadowbroker_server/main.py"],
            "cwd": str(Path(__file__).parent),
            "env_extra": {"PORT": "8765"},
            "health_url": "http://127.0.0.1:8765/api/health",
            "skip_cwd_check": True,
        },
        # UI-TARS-desktop (Electron app) sidecar intentionally not used — GUI automation
        # runs natively via core/vision_control/ (GUIAgent) instead. See districts/coding/gui_automation_agent.py.
    ]

    # Owner rule (2026-07-16): no extra localhost servers by default. Sidecars
    # (ComfyUI/hyperframes/open-webui/shadowbroker) only start when explicitly
    # enabled: VECTOR_SIDECARS=1|all for everything, or a comma-list of names
    # (e.g. VECTOR_SIDECARS=comfyui,shadowbroker).
    _sidecars_env = os.environ.get("VECTOR_SIDECARS", "").strip().lower()
    if _sidecars_env in ("", "0", "off", "false", "none"):
        logger.info(
            "[VECTOR][sidecars] disabled — only the main API (8000) + MCP (9001) run. "
            "Set VECTOR_SIDECARS=1 (or a comma-list of names) to enable extras.")
        sidecars = []
    elif _sidecars_env not in ("1", "all", "on", "true"):
        _wanted = {s.strip() for s in _sidecars_env.split(",") if s.strip()}
        sidecars = [s for s in sidecars if s["name"].lower() in _wanted]
        logger.info("[VECTOR][sidecars] enabled subset: {}", [s["name"] for s in sidecars])

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

    # Opt-in thread-stack dump on a timer (KNOWN_ISSUES.md #0) — off unless
    # VECTOR_THREAD_DUMP_SEC is set. See core/loop/thread_dump.py.
    try:
        from core.loop.thread_dump import enable_if_requested as _enable_thread_dump
        _enable_thread_dump()
    except Exception as e:
        logger.warning("[VECTOR][loop] thread_dump setup skipped: {}", e)

    # Populate the agent registry before the loop starts — otherwise every
    # governor dispatch returns {"status": "no_agents"}.
    try:
        bootstrap_agents()
    except Exception as e:
        logger.error("[VECTOR][loop] bootstrap_agents failed — city starts empty: {}", e)

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
        from core.runtime.tls import uvicorn_ssl_kwargs
        app = create_app()
        # Wire the shared PermissionGateway singleton into app.state so that
        # all gateway router endpoints share the same pending-approvals queue.
        app.state.permission_gateway = PermissionGateway.get_shared()
        # TLS: VECTOR_TLS_CERTFILE/KEYFILE turn on HTTPS; VECTOR_TLS_TERMINATED=1
        # declares upstream (Tailscale/proxy) transport encryption. Without this
        # call the helper was dead code — env vars silently did nothing.
        ssl_kwargs = uvicorn_ssl_kwargs()
        scheme = "https" if ssl_kwargs else "http"
        logger.info("[VECTOR][api] Starting server at {}://{}:{}", scheme, host, port)
        uvicorn.run(app, host=host, port=port, reload=False, **ssl_kwargs)
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
        choices=("loop", "api", "smoke", "doctor", "readiness-check", "memory-repair"),
        help="Default is loop. Use smoke for a one-shot startup check.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # loop/api are the long-running, often-unattended modes — give them a
    # persistent file sink so a closed terminal doesn't lose the trail.
    if args.mode in ("loop", "api"):
        _configure_file_logging(args.mode)

    logger.info("[VECTOR][launcher] mode={}", args.mode)

    # Start optional sidecar services (ComfyUI, etc.) — non-blocking.
    # Skipped in smoke mode to keep the startup check fast.
    if args.mode not in ("smoke", "doctor", "readiness-check", "memory-repair"):
        _start_sidecars()
        _start_background_services()

    if args.mode == "api":
        # Default the autonomous brain ON for `run_vector.py api` — this is THE
        # production entry point every launcher (vector_autostart.bat,
        # vector_watchdog.ps1, or a manual start) ultimately runs, and the three
        # launch paths do not agree on setting VECTOR_API_RUN_LOOP themselves.
        # A manual/undocumented launch previously produced an API that answered
        # /health "ok" while core.loop.loop_state.get_runtime() showed no loop
        # running at all — VECTOR looked alive and was brain-dead for days.
        # setdefault (not a hard assignment) is deliberate: an explicit
        # VECTOR_API_RUN_LOOP=0 still wins, so API-only runs stay possible, and
        # launchers that already export "1" are unaffected. This must run
        # BEFORE core.api.app's lifespan reads the flag (i.e. before run_api()
        # imports/creates the app) or the gate sees the old value.
        #
        # This default does NOT belong in .env: `import core.config` loads
        # .env into os.environ as a side effect, so a .env-based default would
        # spin a real autonomous brain during `pytest` — exactly what the
        # gate in core/api/app.py exists to prevent.
        os.environ.setdefault("VECTOR_API_RUN_LOOP", "1")
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

    if args.mode == "readiness-check":
        from core.runtime.readiness_check import run_readiness_check

        report = run_readiness_check()
        print(json.dumps(report, indent=2))
        return 0 if report.get("status") != "fail" else 1

    if args.mode == "memory-repair":
        from core.memory.episodic import repair_unreadable_memory_db

        report = repair_unreadable_memory_db()
        print(json.dumps(report, indent=2))
        return 0 if report.get("status") in {"ok", "created", "migrated", "recreated"} else 1

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
            # Use the instance that actually ran (get_instance survives loop
            # teardown) — a bare __new__ instance has no _active_task_count and
            # made the drain a silent no-op via AttributeError.
            _shutdown_loop_instance = AutonomousLoop.get_instance()
            if _shutdown_loop_instance is None:
                _shutdown_loop_instance = AutonomousLoop()
            _shutdown_loop_instance._running = False

            async def _drain():
                await _graceful_shutdown(_shutdown_loop_instance, timeout=10.0)

            asyncio.run(_drain())
        except Exception as _se:
            logger.debug("[VECTOR][main] shutdown drain skipped: {}", _se)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
