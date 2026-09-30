"""Modular FastAPI application factory for V.E.C.T.O.R.

Usage:
    from core.api import create_app
    app = create_app()
"""

import sys

__all__ = [
    "create_app",
    "get_app",
    "lifespan",
]

from pathlib import Path

import asyncio
import datetime
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from loguru import logger

from core.config import CONFIG
from core.api import ssl_cache

ssl_cache.install()   # 2026-09-27: httpx.AsyncClient() cost ~300 ms of blocking CPU per construction; see core/api/ssl_cache.py


def _is_hardened_env() -> bool:
    return os.getenv("VECTOR_ENV", str(CONFIG.get("env", "development"))).strip().lower() in {"production", "prod", "vector"}


def _other_loop_pid(runtime: dict, my_pid: int) -> int | None:
    """Pid of ANOTHER live process that owns the autonomous loop, else None.

    A heartbeat stays "fresh" for ~10s after its owner dies, so a restart inside that
    window used to see a dead pid as a live loop and start with NO brain (2026-09-25).
    The owner must actually be alive for it to block this process's own loop.
    """
    pid = runtime.get("pid")
    if not (runtime.get("running") and pid and pid != my_pid):
        return None
    try:
        import psutil
        if not psutil.pid_exists(pid):
            return None
    except ImportError:
        pass  # can't tell: keep the old, conservative behaviour (assume it is alive)
    return pid


def _select_hud_html(hud_dir: Path) -> Path:
    """There is ONE HUD: frontend/VECTOR.html (3D city, map, camera hero, gestures, the whole subsystem dock). The
    separate "VECTOR Production" page and its build were removed 2026-09-25 (owner decision); every environment
    serves this page."""
    return hud_dir / "VECTOR.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan handler replacing deprecated on_event startup/shutdown."""
    # ── STARTUP ──
    logger.info("[VECTOR][api] Starting modular FastAPI application...")

    try:
        from run_vector import bootstrap_agents
        created = bootstrap_agents()
        logger.info(f"[VECTOR][api] Bootstrapped {created} baseline agents")
    except Exception as e:
        logger.warning(f"[VECTOR][api] Agent bootstrap failed: {e}")

    try:
        from core.loop.context_engine import ContextEngine
        app.state.context_engine = ContextEngine()
    except Exception as e:
        logger.warning(f"[VECTOR][api] context_engine failed: {e}")

    try:
        from core.loop.decision_engine import DecisionEngine
        app.state.decision_engine = DecisionEngine()
    except Exception as e:
        logger.warning(f"[VECTOR][api] decision_engine failed: {e}")

    try:
        from core.loop.permission_gateway import PermissionGateway
        app.state.permission_gateway = PermissionGateway()
    except Exception as e:
        logger.warning(f"[VECTOR][api] permission_gateway failed: {e}")

    try:
        from core.city.agent_registry import get_registry
        app.state.agent_registry = get_registry()
        logger.info(f"[VECTOR][api] agent_registry ready — {len(app.state.agent_registry.list_all())} agents")
    except Exception as e:
        logger.warning(f"[VECTOR][api] agent_registry failed: {e}")

    try:
        from vectorcode.src.vc_sessions.session import SessionStore
        app.state.session_store = SessionStore()
        logger.info("[VECTOR][api] session_store ready")
    except Exception as e:
        logger.warning(f"[VECTOR][api] session_store failed: {e}")

    try:
        from core.memory.episodic import EpisodicMemory
        app.state.episodic_memory = EpisodicMemory()
    except Exception as e:
        logger.warning(f"[VECTOR][api] episodic_memory failed: {e}")

    # 2026-07-30 audit fix: EmergencyResponseSystem existed with real
    # signal-monitoring code (health/security/system/network/disk/battery)
    # but its .start() was never called anywhere in the codebase, so its
    # module-level _emit() helper (the only external hook into it, called
    # from autonomous_loop.py's crash-signal handler) was a guaranteed
    # silent no-op. Starting it here makes the background monitoring real;
    # it's also now directly chat/API-dispatchable (see districts/emergency/
    # main.py::run()) independent of this background task.
    app.state.emergency_system = None
    try:
        from districts.emergency.main import EmergencyResponseSystem
        app.state.emergency_system = EmergencyResponseSystem()
        await app.state.emergency_system.start()
        logger.info("[VECTOR][api] EmergencyResponseSystem monitoring started")
    except Exception as e:
        logger.warning(f"[VECTOR][api] EmergencyResponseSystem failed to start: {e}")

    # Collections engine (PocketBase absorption): run pending migrations + expose engine.
    try:
        if (CONFIG.get("collections", {}) or {}).get("enabled", True):
            from core.collections.migrations import MigrationRunner
            from core.collections import CollectionEngine, AuthService, get_hooks
            MigrationRunner().apply_pending()
            app.state.collection_engine = CollectionEngine(hooks=get_hooks())
            app.state.collection_auth = AuthService(app.state.collection_engine)
            logger.info(
                f"[VECTOR][api] collections engine ready - "
                f"{len(app.state.collection_engine.list_collections())} collection(s)"
            )
    except Exception as e:
        logger.warning(f"[VECTOR][api] collections engine failed: {e}")

    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
            r = await client.get(f"{ollama_host}/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                logger.info(f"[VECTOR][api] Ollama online. {len(models)} models available")
    except Exception as e:
        logger.warning(f"[VECTOR][api] Ollama check failed: {e}")

    # OWNER ROUTING CLOSURE (2026-09-17, F3): prewarm IntentMatcher's
    # embedding bootstrap in the background at startup instead of letting
    # the first owner /command pay that cost (RGC2R_RGD2_COMBINED_REALITY_
    # GATE_REPORT.md Section 8 measured 103.90s live on a fresh process).
    # Creates the SAME singleton governor.classify_chat_intent()'s Stage 2
    # lazily creates on first use (identical `hasattr` guard), so whichever
    # runs first — this prewarm or a real command — shares one instance and
    # one background task; nothing is embedded twice.
    try:
        from core.city import governor as _governor_mod
        from core.city.intent_matcher import IntentMatcher
        if not hasattr(_governor_mod.classify_chat_intent, "_matcher"):
            _governor_mod.classify_chat_intent._matcher = IntentMatcher()
        asyncio.create_task(_governor_mod.classify_chat_intent._matcher.prewarm())
        logger.info("[VECTOR][api] IntentMatcher prewarm task started")
    except Exception as e:
        logger.warning(f"[VECTOR][api] IntentMatcher prewarm failed to start: {e}")

    # Start nudge engine cron
    nudge_task = None
    try:
        from core.loop.nudge_engine import nudge_engine

        async def _nudge_cron():
            while True:
                await asyncio.sleep(30)
                try:
                    await nudge_engine.tick()
                except Exception as e:
                    logger.warning(f"[VECTOR][nudge] tick error: {e}")

        nudge_task = asyncio.create_task(_nudge_cron())
        logger.info("[VECTOR][api] Nudge engine cron started (30s interval)")
    except Exception as e:
        logger.warning(f"[VECTOR][api] Nudge engine failed to start: {e}")

    # Schema version check
    try:
        from core.memory.db_registry import REGISTRY
        for key, entry in REGISTRY.items():
            if hasattr(entry, 'schema_version') and entry.schema_version > 0:
                # Just log — don't block startup on mismatch
                logger.info("[VECTOR][startup] DB registry: {} schema_v{}", key, entry.schema_version)
        logger.info("[VECTOR][startup] DB registry check: {} databases tracked", len(REGISTRY))
    except Exception as e:
        logger.warning("[VECTOR][startup] DB registry check failed: {}", e)

    # Register WebSocket broadcast with loop_state so permission_gateway can emit
    # UI events without a circular import (P1.4).
    try:
        from core.api.routers.websocket import broadcast_event as _bcast
        from core.loop.loop_state import register_ui_broadcast as _reg_bc
        _reg_bc(_bcast)
        logger.info("[VECTOR][api] UI broadcast registered in loop_state")
    except Exception as e:
        logger.warning(f"[VECTOR][api] UI broadcast registration failed: {e}")

    # Optionally run the FULL autonomous brain (observe→think→act→reflect) inside
    # this same process, so one `api` server = brain + LAN-accessible interface.
    # Gated by VECTOR_API_RUN_LOOP=1. Tests still don't set this (they import
    # core.api directly, never through run_vector.py's CLI), so they still don't
    # spin the loop. As of 2026-08-05, `run_vector.py api` itself now defaults
    # this to "1" via os.environ.setdefault() before create_app() is called
    # (see run_vector.py's `args.mode == "api"` branch) — autonomy no longer
    # depends on which launcher script started the process. To opt out of the
    # in-process brain for a plain-API run, set VECTOR_API_RUN_LOOP=0 explicitly.
    # Used by: python run_vector.py api --host 0.0.0.0 (LAN full-access launch).
    #
    # CRITICAL (2026-07-11): the loop runs in its OWN thread with its OWN event
    # loop — NOT asyncio.create_task on uvicorn's loop. The brain has blocking
    # sections (Whisper large-v3 load = 71s, sync LLM/DB calls) that starve the
    # HTTP server if they share one event loop (verified: /health timed out).
    # A dedicated thread isolates them so HTTP stays responsive for the phone.
    loop_thread = None
    app.state.autonomous_loop = None
    if os.environ.get("VECTOR_API_RUN_LOOP") == "1":
        # 2026-08-05: refuse to start a SECOND brain if another process is
        # already running one. Measured live: an orphaned
        # `python run_vector.py loop` (PID 44684, alive ~17h, unmanaged by
        # any script) was running concurrently with the API process, and
        # between them they held 90 simultaneous connections to an Ollama
        # backend configured OLLAMA_MAX_LOADED_MODELS=1 — i.e. dozens of
        # requests queued against something that serves one at a time. Two
        # brains also means two writers contending for the same SQLCipher
        # file and the same process-wide _write_lock.
        #
        # This became load-bearing the moment vector_watchdog.ps1 started
        # setting VECTOR_API_RUN_LOOP=1 (see that script's 2026-08-04 note):
        # before, a watchdog restart produced an API with no brain, so a
        # stray `loop` process was the ONLY brain and nothing collided.
        # After, every watchdog restart would have added a second one.
        #
        # vector_autostart.bat's own guard only checks "is port 8000
        # listening", which by construction cannot see a loop-only process
        # (it never binds a port) — that gap is exactly how the orphan
        # survived. The heartbeat file already carries a pid and a 10s
        # freshness window, so it's the cheapest correct signal available.
        _other = None
        try:
            from core.loop.loop_state import get_runtime as _get_rt

            _other = _other_loop_pid(_get_rt(), os.getpid())
        except Exception as _e:  # never let the guard itself block startup
            logger.debug("[VECTOR][api] loop-duplication check skipped: {}", _e)

        if _other:
            logger.warning(
                "[VECTOR][api] NOT starting in-process brain — another autonomous "
                "loop is already live in PID {} (fresh heartbeat). Running two "
                "brains doubles Ollama/DB contention. Stop the other process to "
                "let this one own the loop.", _other,
            )
    if os.environ.get("VECTOR_API_RUN_LOOP") == "1" and not _other:
        try:
            import threading
            # 2026-09-23: deliberate exception to "never use threading, use
            # asyncio" (.claude/rules/libraries.md) -- a real OS thread is
            # the ONLY way to host a SECOND, independent asyncio.run() event
            # loop in this process (the autonomous loop's own run_forever())
            # while the API server's own event loop keeps serving HTTP.
            # There is no asyncio-only way to run two event loops in one
            # thread.
            from core.loop.autonomous_loop import AutonomousLoop

            # Opt-in thread-stack dump on a timer (KNOWN_ISSUES.md #0: the
            # loop thread has been observed to silently deadlock with no
            # traceback). Off unless VECTOR_THREAD_DUMP_SEC is set. Enabled
            # here (not inside _run_brain) so it's armed before the thread
            # starts and covers every thread in the process, not just this one.
            try:
                from core.loop.thread_dump import enable_if_requested as _enable_thread_dump
                _enable_thread_dump()
            except Exception as _e:
                logger.warning("[VECTOR][api] thread_dump setup skipped: {}", _e)

            def _run_brain():
                try:
                    inst = AutonomousLoop()
                    app.state.autonomous_loop = inst
                    asyncio.run(inst.run_forever())
                except Exception as _e:
                    logger.warning("[VECTOR][api] brain thread exited: {}", _e)

            loop_thread = threading.Thread(target=_run_brain, name="vector-brain", daemon=True)
            loop_thread.start()
            logger.info("[VECTOR][api] Autonomous loop started in dedicated thread (brain + API, HTTP stays responsive)")
        except Exception as e:
            logger.warning("[VECTOR][api] in-process autonomous loop failed to start: {}", e)

    logger.info("[VECTOR][api] V.E.C.T.O.R. API ready")

    yield  # ── APP RUNS HERE ──

    # ── SHUTDOWN ──
    logger.info("[VECTOR][api] Shutting down...")
    if app.state.autonomous_loop is not None:
        try:
            app.state.autonomous_loop._running = False  # daemon thread exits with process
        except Exception:
            pass
    if nudge_task is not None:
        nudge_task.cancel()
    if app.state.emergency_system is not None:
        try:
            await app.state.emergency_system.stop()
        except Exception as e:
            logger.warning(f"[VECTOR][api] EmergencyResponseSystem stop error: {e}")
    # app.state.episodic_memory.conn IS the module singleton — close it once,
    # through the helper that also clears the global and resets the circuit
    # breaker. Bare conn.close() left a dead-but-"healthy" singleton behind
    # (sqlcipher ProgrammingError isn't a sqlite3 subclass) and poisoned every
    # memory op until process restart.
    try:
        from core.memory.episodic import close_db_connection
        close_db_connection()
        logger.info("[VECTOR][api] Episodic DB connection closed")
    except Exception as e:
        logger.warning("[VECTOR][api] DB cleanup error: {}", e)


def create_app() -> FastAPI:
    """Create and configure the modular FastAPI application."""
    app = FastAPI(
        title="V.E.C.T.O.R.",
        description="Virtual Entity for Cognitive Tasks & Operational Reasoning",
        version=CONFIG["version"],
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.state.context_engine = None
    app.state.goal_system = None
    app.state.decision_engine = None
    app.state.permission_gateway = None
    app.state.policy_memory = None
    app.state.reasoning_memory = None
    app.state.agent_registry = None
    app.state.episodic_memory = None

    # CORS middleware — localhost only
    # "null" origin (file:// protocol) is intentionally excluded: it would allow
    # any local HTML file to call the API. The HUD is served via /hud/ instead.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CONFIG.get("allowed_origins", [
            "https://localhost:8000", "https://127.0.0.1:8000",
            "http://localhost:8000", "http://127.0.0.1:8000",
            "http://localhost:5173", "http://127.0.0.1:5173",
        ])),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Custom middleware (order matters: last added = first executed on the way in)
    from core.api.middleware import (
        logging_middleware, timing_middleware, error_handling_middleware,
        auth_middleware, rate_limiting_middleware, security_headers_middleware,
        csrf_middleware,
    )
    app.middleware("http")(error_handling_middleware)
    app.middleware("http")(rate_limiting_middleware)
    app.middleware("http")(csrf_middleware)
    app.middleware("http")(auth_middleware)
    app.middleware("http")(logging_middleware)
    app.middleware("http")(timing_middleware)
    app.middleware("http")(security_headers_middleware)

    # CSRF token endpoint — dashboard fetches this on load
    @app.get("/csrf-token", tags=["security"])
    async def csrf_token_endpoint():
        from core.api.middleware import generate_csrf_token
        return {"csrf_token": generate_csrf_token()}

    # Include routers
    from core.api.routers import (
        a2a, commands, council, agents, status, voice, voice_ws, memory, security,
        websocket, tasks, vectorcode, nudge, loop, scheduler, inference, email, channels,
        providers, tools, network, audit, metering, jcode, sandbox, sensing, media,
        mining, mcp, video_composer, scraper, seo, oauth, research, migration,
        ads, code_intel, investment, simulation, intelligence,
        # New district routers
        health, finance, design, analytics, privacy, coding_extended, qa, projects,
        learning, interview, languages, news, patterns, reflection, relationships,
        skills, startups, karpathy, ops, chief, calls, agency, documentation,
        governance_extended,
        # Core infrastructure routers
        brain, city, control,
        # VECTOR feature routers
        camera, location, gesture, sb, ticker, queue, notifications,
        # Collections engine (PocketBase absorption)
        collections,
        # Knowledge layer (Understand-Anything-main absorption)
        knowledge,
        # Content district (postiz feedback loop)
        content,
        # HUD Approvals Panel — gateway pending/approve/reject
        gateway,
        # API key management
        keys,
        # Passkey / fingerprint / Windows Hello authentication (alternative to
        # the static VECTOR_API_KEY bearer token)
        webauthn_auth,
        # JWT authentication with access + refresh tokens (primary interactive auth)
        auth_jwt,
        # Unified world model
        world,
        # Safe autonomous execution contract
        executor,
        # Multi-step mission execution
        missions,
        # OpenAI-compatible gateway for external clients
        openai_compat,
        # Autonomous Growth Engine — public beta-signup form
        growth,
    )
    app.include_router(growth.router)
    app.include_router(a2a.router)
    app.include_router(commands.router)
    app.include_router(council.router)
    app.include_router(agents.router)
    app.include_router(agents.router_singular)
    app.include_router(status.router)
    app.include_router(voice.router)
    app.include_router(voice_ws.router)
    app.include_router(memory.router)
    app.include_router(security.router)
    app.include_router(websocket.router)
    app.include_router(tasks.router)
    app.include_router(vectorcode.router)
    app.include_router(nudge.router)
    app.include_router(loop.router)
    app.include_router(scheduler.router)
    app.include_router(inference.router)
    app.include_router(email.router)
    app.include_router(channels.router)
    app.include_router(providers.router)
    app.include_router(tools.router)
    app.include_router(network.router)
    app.include_router(audit.router)
    app.include_router(metering.router)
    app.include_router(jcode.router)
    app.include_router(sandbox.router)
    app.include_router(sensing.router)
    app.include_router(media.router)
    app.include_router(mining.router)
    app.include_router(mcp.router)
    app.include_router(video_composer.router)
    app.include_router(scraper.router)
    app.include_router(seo.router)
    app.include_router(oauth.router)
    app.include_router(research.router)
    app.include_router(migration.router)
    app.include_router(ads.router)
    app.include_router(code_intel.router)
    app.include_router(investment.router)
    app.include_router(simulation.router)
    app.include_router(intelligence.router)
    # District routers
    app.include_router(health.router)
    app.include_router(finance.router)
    app.include_router(design.router)
    app.include_router(analytics.router)
    app.include_router(privacy.router)
    app.include_router(coding_extended.router)
    app.include_router(qa.router)
    app.include_router(projects.router)
    app.include_router(learning.router)
    app.include_router(interview.router)
    app.include_router(languages.router)
    app.include_router(news.router)
    app.include_router(patterns.router)
    app.include_router(reflection.router)
    app.include_router(relationships.router)
    app.include_router(skills.router)
    app.include_router(startups.router)
    app.include_router(karpathy.router)
    app.include_router(ops.router)
    app.include_router(chief.router)
    app.include_router(calls.router)
    app.include_router(agency.router)
    app.include_router(documentation.router)
    app.include_router(governance_extended.router)
    # Core infrastructure routers
    app.include_router(brain.router)
    app.include_router(city.router)
    app.include_router(control.router)
    app.include_router(camera.router)
    app.include_router(location.router)
    app.include_router(gesture.router)
    app.include_router(sb.router)
    app.include_router(ticker.router)
    app.include_router(notifications.router)
    app.include_router(queue.router)
    app.include_router(collections.router)
    app.include_router(knowledge.router)
    app.include_router(content.router)
    app.include_router(gateway.router)
    app.include_router(keys.router)
    app.include_router(webauthn_auth.router)
    app.include_router(auth_jwt.router)
    app.include_router(world.router)
    app.include_router(executor.router)
    app.include_router(missions.router)
    app.include_router(openai_compat.router)

    # External task ingestion API — phone, cloud, ESP32
    from core.api import tasks as external_tasks
    app.include_router(external_tasks.router)

    # VECTOR browser dashboard — zero npm, served at /ui
    try:
        from core.ui.web_ui import router as ui_router
        app.include_router(ui_router)
        logger.info("[VECTOR][api] web UI mounted at /ui")
    except Exception as _ui_err:
        logger.warning(f"[VECTOR][api] web UI failed to mount: {_ui_err}")

    # ── VECTOR JARVIS HUD — vanilla JS frontend served at /hud/ ──────────────
    # Uses explicit route handlers (not StaticFiles mount) so every request
    # goes through FastAPI middleware (auth, rate-limiting, security headers).
    try:
        from fastapi.responses import RedirectResponse

        _hud_dir = Path(__file__).parent.parent.parent / "frontend"

        @app.get("/hud", include_in_schema=False)
        async def hud_redirect():
            return RedirectResponse(url="/hud/")

        # PUBLIC passkey login shell — the one page reachable without already
        # holding VECTOR_API_KEY. Deliberately separate from hud_static below:
        # /hud/* stays fully auth-gated (by design — see that handler's own
        # comment), but a keyless browser had NO way to even reach a "sign in
        # with passkey" button before this, since the HUD's own login affordance
        # lived inside the auth-gated shell. This page offers ONLY the passkey
        # LOGIN ceremony (never registration, which still correctly requires
        # the existing key — see core/api/routers/webauthn_auth.py). Must be
        # listed in middleware._PUBLIC_PATHS as "/login" for this to work.
        @app.get("/clear-site-data", include_in_schema=False)
        async def clear_site_data():
            """Recovery page for a browser that keeps showing a removed HUD from its own cache / service worker.

            The `Clear-Site-Data` response header makes the browser delete this origin's HTTP cache, cookies, service
            workers and Cache Storage. It is honoured for a navigation even when an old service worker is answering the
            other requests, because the worker never handles this path. The page then goes to the location in the URL
            fragment (kept out of any request, so an API key in it is never sent to the server), or /login."""
            from fastapi.responses import HTMLResponse

            html = (
                "<!doctype html><meta charset=utf-8><title>VECTOR</title>"
                "<body style=\"background:#000;color:#7fdcff;font:16px monospace;padding:2em\">"
                "Clearing this browser's saved VECTOR pages&hellip;"
                "<script>var n=location.hash.slice(1);"
                "if(!n||n.charAt(0)!=='/'||n.charAt(1)==='/'){n='/login';}"
                "setTimeout(function(){location.replace(n);},700);</script>"
                "<noscript><p><a href=\"/login\">Continue</a></p></noscript>"
            )
            return HTMLResponse(html, headers={
                "Clear-Site-Data": '"cache", "cookies", "storage"',
                "Cache-Control": "no-store",
            })

        @app.get("/login", include_in_schema=False)
        async def login_page():
            login_html = _hud_dir / "login.html"
            if login_html.exists():
                return FileResponse(str(login_html), media_type="text/html")
            return JSONResponse({"error": "login.html not found"}, status_code=404)

        @app.get("/hud/", include_in_schema=False)
        async def hud_root():
            hud_html = _select_hud_html(_hud_dir)
            if hud_html.exists():
                return FileResponse(str(hud_html), media_type="text/html")
            return JSONResponse({"error": f"HUD not found. Ensure {hud_html.name} exists."}, status_code=404)

        @app.get("/hud/{filepath:path}", include_in_schema=False)
        async def hud_static(filepath: str = ""):
            """Serve HUD static files — goes through auth middleware unlike StaticFiles mount."""
            if not filepath or filepath == "/":
                filepath = _select_hud_html(_hud_dir).name
            file_path = _hud_dir / filepath
            # Prevent path traversal: resolved path must stay within _hud_dir
            try:
                file_path = file_path.resolve()
                _hud_dir.resolve()
                if not str(file_path).startswith(str(_hud_dir.resolve())):
                    return JSONResponse({"error": "Forbidden"}, status_code=403)
            except Exception:
                return JSONResponse({"error": "Forbidden"}, status_code=403)
            if file_path.exists() and file_path.is_file():
                # woff2/woff aren't in every platform's mimetypes registry —
                # set explicitly so vendored fonts load with the right type.
                _ext = file_path.suffix.lower()
                _font_mt = {".woff2": "font/woff2", ".woff": "font/woff",
                            ".ttf": "font/ttf", ".otf": "font/otf"}.get(_ext)
                if _font_mt:
                    return FileResponse(str(file_path), media_type=_font_mt)
                return FileResponse(str(file_path))
            # Default to the selected HUD entrypoint for client-side routing.
            hud_html = _select_hud_html(_hud_dir)
            if hud_html.exists():
                return FileResponse(str(hud_html), media_type="text/html")
            return JSONResponse({"error": "HUD not found"}, status_code=404)

        if _hud_dir.exists():
            logger.info(f"[VECTOR][api] JARVIS HUD mounted at /hud/ from {_hud_dir} (auth-protected routes)")
        else:
            logger.warning("[VECTOR][api] frontend/ directory not found — HUD unavailable")

    except Exception as _hud_err:
        logger.warning(f"[VECTOR][api] HUD failed to mount: {_hud_err}")

    # ── JSON root (React dashboard removed — HUD is now at /hud/) ────────────
    @app.get("/", tags=["root"])
    async def root():
        return {
            "system": "V.E.C.T.O.R.",
            "version": CONFIG.get("version", "1.0.0"),
            "status": "operational",
            "hud": "/hud/",
            "docs": "/docs",
        }

    @app.get("/metrics", tags=["observability"], response_class=__import__("fastapi").responses.PlainTextResponse)
    async def prometheus_metrics(request: Request):
        """Prometheus-compatible metrics endpoint. Scrape at /metrics (localhost only)."""
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            raise __import__("fastapi").HTTPException(status_code=403, detail="Metrics available from localhost only")
        lines = []
        try:
            from core.loop.loop_state import get_runtime as _get_rt
            ticks = _get_rt()["tick_count"]
            lines.append("# HELP vector_loop_ticks_total Autonomous loop tick count")
            lines.append("# TYPE vector_loop_ticks_total counter")
            lines.append(f"vector_loop_ticks_total {ticks}")
        except Exception:
            lines.append("vector_loop_ticks_total 0")

        try:
            from core.memory.episodic import EpisodicMemory
            stats = EpisodicMemory().get_stats()
            for key, val in stats.items():
                metric_name = f"vector_memory_{key}_rows"
                lines.append(f"# HELP {metric_name} Row count for {key}")
                lines.append(f"# TYPE {metric_name} gauge")
                lines.append(f"{metric_name} {val}")
        except Exception as e:
            logger.warning(f"[VECTOR][api] metrics: episodic stats unavailable: {e}")

        try:
            from core.city.agent_registry import AgentRegistry
            agents = AgentRegistry().list_all()
            alive = sum(1 for a in agents if getattr(a, "health_points", 0) > 0)
            lines.append("# HELP vector_agents_alive_total Living agents in the city")
            lines.append("# TYPE vector_agents_alive_total gauge")
            lines.append(f"vector_agents_alive_total {alive}")
            lines.append("# HELP vector_agents_total Total registered agents")
            lines.append("# TYPE vector_agents_total gauge")
            lines.append(f"vector_agents_total {len(agents)}")
        except Exception as e:
            logger.warning(f"[VECTOR][api] metrics: agent registry unavailable: {e}")

        return "\n".join(lines) + "\n"

    return app


# Keep legacy import path working
def get_app() -> FastAPI:
    """Alias for create_app()."""
    return create_app()


if __name__ == "__main__":
    import uvicorn
    sys.stdout.reconfigure(encoding="utf-8")
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
