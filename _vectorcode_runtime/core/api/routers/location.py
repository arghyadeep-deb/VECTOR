"""VECTOR location router — IP geolocation for map panel."""

__all__ = [
    "current_location",
    "router",
]


from fastapi import APIRouter, HTTPException
from loguru import logger

router = APIRouter(prefix="/location", tags=["location"])


@router.get("/current")
async def current_location():
    """Return current location via IP geolocation (ip-api.com free tier)."""
    last_error = ""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("http://ip-api.com/json")
            if r.status_code == 200:
                d = r.json()
                return {
                    "lat": d.get("lat", 20.2961),
                    "lon": d.get("lon", 85.8245),
                    "city": d.get("city", "Unknown"),
                    "region": d.get("regionName", ""),
                    "country": d.get("country", ""),
                    "isp": d.get("isp", ""),
                    "timezone": d.get("timezone", ""),
                    "source": "ip-api",
                }
            last_error = f"ip-api returned HTTP {r.status_code}"
    except Exception as e:
        last_error = str(e)
        logger.warning(f"[VECTOR][location] IP geolocation failed: {e}")

    raise HTTPException(
        status_code=503,
        detail={"status": "unavailable", "source": "ip-api", "reason": last_error or "location unavailable"},
    )


if __name__ == "__main__":
    print("location.py OK")
