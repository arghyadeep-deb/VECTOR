"""Modular FastAPI application factory for V.E.C.T.O.R.

Usage:
    from core.api import create_app
    app = create_app()
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from loguru import logger

from core.config import CONFIG


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
                    logger.debug(f"[VECTOR][nudge] tick error: {e}")

        nudge_task = asyncio.create_task(_nudge_cron())
        logger.info("[VECTOR][api] Nudge engine cron started (30s interval)")
    except Exception as e:
        logger.warning(f"[VECTOR][api] Nudge engine failed to start: {e}")

    logger.info("[VECTOR][api] V.E.C.T.O.R. API ready")

    yield  # ── APP RUNS HERE ──

    # ── SHUTDOWN ──
    logger.info("[VECTOR][api] Shutting down...")
    if nudge_task is not None:
        nudge_task.cancel()
    for key in ["episodic_memory"]:
        obj = getattr(app.state, key, None)
        if obj and hasattr(obj, "conn"):
            try:
                obj.conn.close()
            except Exception:
                pass


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CONFIG.get("allowed_origins", [
            "https://localhost:8000", "https://127.0.0.1:8000",
            "http://localhost:8000", "http://127.0.0.1:8000",
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
    from core.api.routers import a2a, commands, council, agents, status, voice, voice_ws, memory, security, websocket, tasks, vectorcode, nudge, loop, scheduler, inference, email, channels, providers, tools, network, audit, metering, jcode, sandbox, sensing, media, mining, mcp, video_composer, scraper, seo, oauth, research, migration, ads, code_intel, investment, simulation
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

    # VECTOR browser dashboard — zero npm, served at /ui
    try:
        from core.ui.web_ui import router as ui_router
        app.include_router(ui_router)
        logger.info("[VECTOR][api] web UI mounted at /ui")
    except Exception as _ui_err:
        logger.warning(f"[VECTOR][api] web UI failed to mount: {_ui_err}")

    # VECTOR holographic HUD dashboard — built Vite+React app
    try:
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import HTMLResponse

        dashboard_dist = Path(__file__).parent.parent / "ui" / "dashboard" / "dist"
        if dashboard_dist.exists():
            app.mount("/assets", StaticFiles(directory=str(dashboard_dist / "assets")), name="hud_assets")
            logger.info(f"[VECTOR][api] HUD assets mounted from {dashboard_dist / 'assets'}")

            @app.get("/", include_in_schema=False)
            @app.get("/dashboard", include_in_schema=False)
            @app.get("/dashboard/", include_in_schema=False)
            async def hud_dashboard():
                return HTMLResponse(
                    (dashboard_dist / "index.html").read_text(encoding="utf-8")
                )
            logger.info("[VECTOR][api] VECTOR HUD dashboard mounted at /")
        else:
            logger.warning(f"[VECTOR][api] HUD build not found at {dashboard_dist}; run `cd core/ui/dashboard && npm run build`")
            # Fallback JSON root
            @app.get("/", tags=["root"])
            async def root():
                return {
                    "system": "V.E.C.T.O.R.",
                    "version": CONFIG["version"],
                    "status": "operational",
                    "docs": "/docs",
                }
    except Exception as _hud_err:
        logger.warning(f"[VECTOR][api] HUD dashboard failed to mount: {_hud_err}")
        # Fallback JSON root
        @app.get("/", tags=["root"])
        async def root():
            return {
                "system": "V.E.C.T.O.R.",
                "version": CONFIG["version"],
                "status": "operational",
                "docs": "/docs",
            }

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
