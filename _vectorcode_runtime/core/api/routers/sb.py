"""VECTOR shadowbroker proxy — single-origin gateway to shadowbroker_server.

Shadowbroker_server runs on its own port (default 8765) at
`districts/intelligence/shadowbroker_server/main.py`. The dashboard talks to
VECTOR's main API on :8000 only, so this router proxies the SB endpoints under
`/sb/*`. HMAC signing is automatic when SHADOWBROKER_HMAC_SECRET is set.

Endpoints:
    GET  /sb/geocode?q=London          -> Nominatim proxy (lat/lon/display_name)
    GET  /sb/layer/{name}              -> a single SB data layer (flights, ships, ...)
    GET  /sb/summary                   -> cheap counts-only summary
    GET  /sb/sse                       -> SSE relay (layer_changed, alerts, tasks)
    POST /sb/cmd                       -> generic SB command dispatch
    POST /sb/pin                       -> place an AI-intel pin
    GET  /sb/pins                      -> list AI-intel pins
"""
import os

__all__ = [
    "router",
    "sb_cmd",
    "sb_geocode",
    "sb_health",
    "SB_HMAC",
    "sb_layer",
    "sb_pins",
    "sb_place_pin",
    "sb_sse",
    "sb_summary",
    "SB_TIMEOUT",
    "SB_URL",
]

import asyncio
import json


from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

router = APIRouter(prefix="/sb", tags=["shadowbroker"])

# --- Config ----------------------------------------------------------------

SB_URL = os.environ.get(
    "SHADOWBROKER_URL",
    f"http://127.0.0.1:{os.environ.get('SHADOWBROKER_PORT', '8765')}",
).rstrip("/")
SB_HMAC = os.environ.get("SHADOWBROKER_HMAC_SECRET", "")
SB_TIMEOUT = float(os.environ.get("SHADOWBROKER_TIMEOUT_S", "10.0"))

_client = None


def _get_client():
    """Lazy-init the ShadowBrokerClient SDK (or fall back to plain httpx)."""
    global _client
    if _client is not None:
        return _client
    try:
        # Prefer the absorbed SDK — it handles HMAC + retries.
        from districts.intelligence.shadowbroker import ShadowBrokerClient
        _client = ShadowBrokerClient(base_url=SB_URL, hmac_secret=SB_HMAC or None)
        logger.info(f"[VECTOR][sb] ShadowBrokerClient SDK ready at {SB_URL}")
    except Exception as e:
        logger.warning(f"[VECTOR][sb] SDK unavailable, using raw httpx: {e}")
        _client = "httpx"
    return _client


async def _proxy_get(path: str, params: dict | None = None) -> dict:
    """Plain httpx GET to shadowbroker_server (no HMAC)."""
    import httpx
    url = f"{SB_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=SB_TIMEOUT) as c:
            r = await c.get(url, params=params or {})
            if r.status_code >= 400:
                return {"error": f"sb {r.status_code}", "detail": r.text[:300]}
            try:
                return r.json()
            except Exception:
                return {"raw": r.text}
    except Exception as e:
        logger.debug(f"[VECTOR][sb] GET {path} failed: {e}")
        return {"error": "sb_unreachable", "detail": str(e), "url": url}


# --- Public endpoints ------------------------------------------------------

@router.get("/geocode")
async def sb_geocode(q: str, limit: int = 1):
    """Nominatim geocode via SB. Used by 'show me London' voice flow."""
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="q is required")
    res = await _proxy_get("/geocode", {"q": q, "limit": str(limit)})
    return JSONResponse(res)


@router.get("/summary")
async def sb_summary():
    """Cheap counts-only summary across SB layers."""
    return JSONResponse(await _proxy_get("/api/summary"))


@router.get("/layer/{name}")
async def sb_layer(name: str):
    """Single layer slice. Validates name to a known set (defence in depth)."""
    safe = {
        "flights", "ships", "satellites", "sigint", "gdelt", "news", "earthquakes",
        "fires", "gps_jamming", "uap_sightings", "wastewater",
        "datacenters", "military_bases", "plane_alert_db", "carriers",
        "ai_pins", "correlations", "liveuamap", "crowdthreat",
    }
    if name not in safe:
        raise HTTPException(status_code=400, detail=f"unknown layer: {name}")
    return JSONResponse(await _proxy_get(f"/api/layer/{name}"))


@router.post("/cmd")
async def sb_cmd(request: Request):
    """Generic SB command dispatch. Body: {cmd, args}."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")
    cmd = (body or {}).get("cmd")
    args = (body or {}).get("args", {})
    if not cmd:
        raise HTTPException(status_code=400, detail="cmd is required")

    cli = _get_client()
    if cli == "httpx":
        # Dumb POST fallback
        import httpx
        async with httpx.AsyncClient(timeout=SB_TIMEOUT) as c:
            r = await c.post(f"{SB_URL}/api/cmd", json={"cmd": cmd, "args": args})
            return JSONResponse(r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text})
    try:
        result = await cli.send_command(cmd, args)  # type: ignore[attr-defined]
        return JSONResponse(result if isinstance(result, dict) else {"result": result})
    except Exception as e:
        logger.error(f"[VECTOR][sb] cmd {cmd} failed: {e}")
        raise HTTPException(status_code=502, detail=f"sb cmd failed: {e}")


@router.get("/pins")
async def sb_pins(category: str | None = None):
    """List AI-intel pins (optionally filtered by category)."""
    params = {"category": category} if category else None
    return JSONResponse(await _proxy_get("/api/pins", params))


@router.post("/pin")
async def sb_place_pin(request: Request):
    """Place a pin. Body matches ShadowBrokerClient.place_pin signature."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")
    cli = _get_client()
    if cli == "httpx":
        import httpx
        async with httpx.AsyncClient(timeout=SB_TIMEOUT) as c:
            r = await c.post(f"{SB_URL}/api/pin", json=body)
            return JSONResponse(r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text})
    try:
        result = await cli.place_pin(**body)  # type: ignore[attr-defined]
        return JSONResponse(result if isinstance(result, dict) else {"result": result})
    except Exception as e:
        logger.error(f"[VECTOR][sb] pin failed: {e}")
        raise HTTPException(status_code=502, detail=f"sb pin failed: {e}")


@router.get("/sse")
async def sb_sse():
    """SSE relay. Streams shadowbroker layer_changed/alert/task events to the dashboard."""
    import httpx

    async def event_gen():
        url = f"{SB_URL}/sse"
        try:
            async with httpx.AsyncClient(timeout=None) as c:
                async with c.stream("GET", url) as resp:
                    if resp.status_code >= 400:
                        yield f"event: error\ndata: {json.dumps({'status': resp.status_code})}\n\n".encode()
                        return
                    async for line in resp.aiter_lines():
                        if line is None:
                            continue
                        yield (line + "\n").encode()
                        # An empty line ends an event; httpx yields '' for that.
        except asyncio.CancelledError:
            return
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n".encode()

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/health")
async def sb_health():
    """Quick reachability check. Used by start scripts."""
    payload = await _proxy_get("/api/health")
    if isinstance(payload, dict) and payload.get("error"):
        return JSONResponse(payload, status_code=503)
    return JSONResponse(payload)


if __name__ == "__main__":
    print("sb.py OK")
