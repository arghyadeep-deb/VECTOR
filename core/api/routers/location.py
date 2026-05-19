"""VECTOR location router — IP geolocation for map panel."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/location", tags=["location"])


@router.get("/current")
async def current_location():
    """Return current location via IP geolocation (ip-api.com free tier)."""
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
    except Exception as e:
        logger.warning(f"[VECTOR][location] IP geolocation failed: {e}")

    # Fallback: owner's known location (Bhubaneswar, KIIT)
    return {
        "lat": 20.3549,
        "lon": 85.8193,
        "city": "Bhubaneswar",
        "region": "Odisha",
        "country": "India",
        "isp": "",
        "timezone": "Asia/Kolkata",
        "source": "fallback",
    }


if __name__ == "__main__":
    print("location.py OK")
