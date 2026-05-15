<!-- VECTOR-INGESTED ASSET
  Source: .claude/skills/SKILL.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:55+00:00
-->

---
name: fastapi-pro
description: Expert in FastAPI async APIs with Pydantic V2. Use when adding routes to core/main.py, building the cloud API layer (T6), or designing district agent HTTP interfaces.
risk: safe
source: sickn33/antigravity-awesome-skills (community)
---

# FastAPI Pro

Expert FastAPI developer specializing in high-performance, async-first API development with modern Python patterns.

## Use this skill when

- Adding new routes to `core/main.py`
- Building the cloud API layer in `api/` (T6)
- Designing health-check and district-status endpoints
- Wiring WebSocket for real-time VECTOR status dashboard
- Adding rate limiting with slowapi
- Writing async tests for VECTOR's API

## VECTOR FastAPI Stack

```python
# core/main.py pattern
from fastapi import FastAPI, HTTPException
from loguru import logger
from core.config import CONFIG

app = FastAPI(title="VECTOR", version=CONFIG["version"])

@app.get("/status")
async def status():
    return {"status": "ok", "version": CONFIG["version"]}

@app.post("/act")
async def act(task: TaskRequest):
    # Always goes through permission_gateway — RULE 3
    result = await governor.dispatch(task.dict())
    return result
```

## Key Patterns

### Lifespan for startup/shutdown
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    asyncio.create_task(autonomous_loop.run_forever())
    yield
    # Shutdown
    autonomous_loop.stop()

app = FastAPI(lifespan=lifespan)
```

### Dependency injection for shared state
```python
def get_governor() -> Governor:
    return Governor()  # singleton via _get_governor pattern

@app.post("/dispatch")
async def dispatch(task: dict, gov: Governor = Depends(get_governor)):
    return await gov.dispatch(task)
```

### Rate limiting (slowapi)
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)

@app.post("/act")
@limiter.limit("10/minute")
async def act(request: Request, task: TaskRequest):
    ...
```

### Health check with district status
```python
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "districts": governor.get_district_summary(),
        "uptime": loop.uptime_seconds,
        "ticks": loop._tick_count,
    }
```

## Current Routes (core/main.py)
- `GET /` — root info
- `GET /status` — system status
- `POST /act` — dispatch action via governor
- `GET /memory` — recent episodic memories
- `GET /goals` — active goals from goal_system
- `GET /agents` — agent registry summary

## When to Use
- Adding new API routes for VECTOR
- Building `api/` cloud layer (T6)
- Wiring WebSocket for real-time dashboard (T6)
- Testing API endpoints with httpx
