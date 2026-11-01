"""Intelligence router — /intelligence/* endpoints for VectorIntel global surveillance."""


__all__ = [
    "all_layers",
    "BatchPinRequest",
    "cctv",
    "conflicts",
    "fires",
    "flights",
    "intel_status",
    "news_near",
    "outages",
    "PinRequest",
    "place_pin",
    "place_pins_batch",
    "report",
    "router",
    "satellites",
    "summary",
    "vessels",
]


from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        from districts.intelligence.vectorintel_agent import VectorIntelAgent
        _agent = VectorIntelAgent()
    return _agent


async def _safe(coro):
    """Await an agent call, degrading to a 503 JSON payload on connection
    failure instead of a raw 500.

    Every read endpoint below is a bare passthrough to the shadowbroker
    sidecar (`self._sb.get_*`) with no error handling. That sidecar is OFF BY
    DEFAULT (owner rule, 2026-07-16: single-server unless VECTOR_SIDECARS is
    set), so in normal operation EVERY one of these endpoints threw an
    unhandled httpx.ConnectError -> bare 500 (found via browser dogfood:
    GET /intelligence/summary -> 500, 2026-07-17). Mirrors the graceful
    pattern GET /sb/health already uses.
    """
    try:
        return await coro
    except Exception as e:
        import httpx
        if isinstance(e, (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError)):
            logger.debug(f"[VECTOR][api][intelligence] backend unavailable: {e}")
            return JSONResponse(
                {"status": "unavailable", "error": "VectorIntel/shadowbroker not running"},
                status_code=503,
            )
        raise


# ── Read endpoints ────────────────────────────────────────────────────────────

@router.get("/flights")
async def flights(lat: float = None, lon: float = None, radius_km: int = 500):
    """Live ADS-B aircraft positions. Optionally filter by lat/lon radius."""
    return await _safe(_get_agent().get_flights(lat, lon, radius_km))


@router.get("/vessels")
async def vessels(lat: float = None, lon: float = None, radius_km: int = 500):
    """AIS maritime vessel traffic. Optionally filter by lat/lon radius."""
    return await _safe(_get_agent().get_vessels(lat, lon, radius_km))


@router.get("/satellites")
async def satellites():
    """Active satellite positions (recon, SAR, SIGINT, nav)."""
    return await _safe(_get_agent().get_satellites())


@router.get("/conflicts")
async def conflicts():
    """GDELT conflict events + Ukraine frontline positions."""
    return await _safe(_get_agent().get_conflicts())


@router.get("/fires")
async def fires():
    """NASA FIRMS active fire hotspots."""
    return await _safe(_get_agent().get_fires())


@router.get("/outages")
async def outages():
    """Global internet outages (Georgia Tech IODA)."""
    return await _safe(_get_agent().get_outages())


@router.get("/cctv")
async def cctv():
    """Global CCTV camera index (11,000+ cameras)."""
    return await _safe(_get_agent().get_cctv())


@router.get("/summary")
async def summary():
    """Global situation summary across all data layers."""
    return await _safe(_get_agent().get_summary())


@router.get("/report")
async def report(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """Full intelligence report for a specific location."""
    return await _safe(_get_agent().get_report(lat, lon))


@router.get("/news-near")
async def news_near(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius_km: int = 100,
):
    """Breaking news/events near a lat/lon from Shadowbroker AI layer."""
    return await _safe(_get_agent().get_news_near(lat, lon, radius_km))


@router.get("/all")
async def all_layers():
    """All 35+ data layers in one payload. Use sparingly."""
    return await _safe(_get_agent().get_all())


# ── Write endpoints ───────────────────────────────────────────────────────────

class PinRequest(BaseModel):
    lat: float
    lon: float
    label: str
    category: str = "intel"
    color: str = "cyan"


class BatchPinRequest(BaseModel):
    pins: list[PinRequest]


@router.post("/pin")
async def place_pin(req: PinRequest):
    """Place an intelligence pin on the VectorIntel map."""
    return await _get_agent().place_pin(req.lat, req.lon, req.label, req.category, req.color)


@router.post("/pins/batch")
async def place_pins_batch(req: BatchPinRequest):
    """Place multiple intelligence pins at once."""
    pins = [p.model_dump() for p in req.pins]
    return await _get_agent().place_pins_batch(pins)


@router.get("/status")
async def intel_status():
    """Check VectorIntel platform connectivity."""
    agent = _get_agent()
    agent._check_availability()
    return {
        "available": agent._available,
        "host": agent.__class__.__module__,
        "capabilities": [
            "flights", "vessels", "satellites", "cctv",
            "conflicts", "outages", "fires",
            "summary", "report", "news_near", "place_pin",
        ],
    }
