import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG
from loguru import logger
import datetime, time, httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import ollama

# --- APP SETUP ---
app = FastAPI(title='VECTOR', version=CONFIG['version'])

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_ALLOWED_ORIGINS = CONFIG.get("allowed_origins", [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

START_TIME = datetime.datetime.now(datetime.timezone.utc)

# --- MODELS ---
class CommandRequest(BaseModel):
    text: str
    source: str = "text"
    priority: str = "normal"

class VoiceResponse(BaseModel):
    transcript: str
    response: str
    language_detected: str

class AgentAwardRequest(BaseModel):
    agent_id: str
    points: int
    reason: str

class CouncilRequest(BaseModel):
    question: str
    stakes: str = "medium"
    context_override: dict | None = None

# --- HELPER ---
def get_ollama_host() -> str:
    host = CONFIG["ollama_host"]
    from urllib.parse import urlparse
    parsed = urlparse(host)
    if not parsed.scheme:
        host = "http://" + host
    return host

def session_hydration_prompt() -> str:
    try:
        from core.loop.context_engine import ContextEngine
        return ContextEngine().session_hydration_prompt()
    except Exception:
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"You are {CONFIG['system_name']}. Owner: {CONFIG['owner_name']}. Time: {now}. "
            f"Environment: {CONFIG['env']}. "
            f"Respond as VECTOR — precise, calm, slightly dry tone."
        )

# --- STARTUP ---
@app.on_event("startup")
async def startup():
    logger.info("[VECTOR][main] Starting VECTOR...")

    host = get_ollama_host()
    logger.info(f"[DEBUG] Ollama host = {host}")

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{host}/api/tags", timeout=5)

            models = [m["name"] for m in r.json().get("models", [])]
            logger.info(f"[VECTOR][main] Ollama online. Models: {len(models)} available")

            if CONFIG["models"]["focus"] in models:
                logger.info("[VECTOR][main] vector-focus confirmed ready")
            else:
                logger.warning("[VECTOR][main] vector-focus NOT found")

    except Exception as e:
        logger.error(f"[VECTOR][main] Ollama check failed: {e}")

    logger.info("[VECTOR][main] VECTOR online at http://127.0.0.1:8000")

# --- ROUTES ---
@app.get("/health")
async def health():
    checks: dict[str, str] = {}

    # Ping Ollama
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{get_ollama_host()}/api/tags")
            checks["ollama"] = "ok" if r.status_code == 200 else f"http_{r.status_code}"
    except Exception as e:
        checks["ollama"] = f"error: {e}"

    # Ping SQLite
    try:
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        row = mem.conn.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()
        checks["sqlite"] = "ok" if row is not None else "error"
    except Exception as e:
        checks["sqlite"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if all_ok else "degraded",
            "checks": checks,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "version": CONFIG["version"],
        }
    )

@app.get("/status")
async def status():
    uptime = (datetime.datetime.now(datetime.timezone.utc) - START_TIME).seconds
    return {
        "loop_running": False,
        "uptime_seconds": uptime,
        "models": {"focus": "loaded"},
        "memory": {"episodic_rows": 0},
        "vector_version": CONFIG["version"],
    }

@app.post("/command")
@limiter.limit("60/minute")
async def command(request: Request, body: CommandRequest):
    start = time.perf_counter()

    prompt = session_hydration_prompt() + f"\n\nUser: {body.text}"

    try:
        response = ollama.chat(
            model=CONFIG["models"]["focus"],
            messages=[{"role": "user", "content": prompt}],
        )
        reply = response["message"]["content"]

    except Exception as e:
        logger.error(f"[VECTOR][main] ollama.chat failed: {e}")
        reply = "Model unavailable."

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return {
        "response": reply,
        "processing_ms": elapsed_ms,
    }

@app.post("/voice")
async def voice():
    return {
        "transcript": "Voice not implemented yet",
        "response": "Coming soon",
        "language_detected": "en",
    }

@app.post("/agent/award")
async def agent_award(body: AgentAwardRequest):
    return {
        "new_hp": 500 + body.points,
        "status": "ok",
    }

@app.post("/council")
async def council(body: CouncilRequest):
    try:
        response = ollama.chat(
            model=CONFIG["models"]["chairman"],
            messages=[{"role": "user", "content": body.question}],
        )

        return {
            "decision": response["message"]["content"],
            "confidence": 0.8,
        }

    except Exception as e:
        logger.error(f"[VECTOR][main] Council failed: {e}")
        raise HTTPException(503, "Chairman unavailable")

# --- RUN ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("core.main:app", host="127.0.0.1", port=8000, reload=False)