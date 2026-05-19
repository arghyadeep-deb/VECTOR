"""VECTOR Intel Bridge — connects to the VectorIntel surveillance platform.

VectorIntel is VECTOR's real-time global intelligence layer:
- 5,000+ tracked aircraft (commercial + military)
- 25,000+ AIS maritime vessels
- 2,000+ satellites (recon, SAR, SIGINT, nav)
- 11,000+ CCTV cameras globally
- Ukraine frontline, conflict events, GDELT news
- Internet outages, critical infrastructure
- NASA fire hotspots, earthquakes, environmental
- SAR ground-change detection via Sentinel-1/Copernicus
- US Navy carrier position estimation via GDELT scraping

Setup: Run VectorIntel server on port 8002 alongside VECTOR on 8000.
  cd C:\\Users\\Arghyadeep\\Desktop\\V.E.C.T.O.R\\GitHub\\Shadowbroker-main
  docker-compose up -d  OR  python backend/main.py

Then set env: VECTORINTEL_HOST=http://127.0.0.1:8002
              VECTORINTEL_SECRET=your_hmac_secret_here
"""

import sys
import hashlib
import hmac
import json
import os
import time
import uuid
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

_VECTORINTEL_HOST = os.environ.get("VECTORINTEL_HOST", "http://127.0.0.1:8002")
_VECTORINTEL_SECRET = os.environ.get("VECTORINTEL_SECRET", "")


def _sign_request(method: str, path: str, body: bytes = b"") -> dict:
    """Generate HMAC-SHA256 authentication headers for VectorIntel API."""
    timestamp = str(int(time.time()))
    nonce = hashlib.sha256(f"{timestamp}{path}".encode()).hexdigest()[:16]
    body_hash = hashlib.sha256(body).hexdigest()
    msg = f"{method}|{path}|{timestamp}|{nonce}|{body_hash}"
    sig = hmac.new(_VECTORINTEL_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return {
        "X-SB-Timestamp": timestamp,
        "X-SB-Nonce": nonce,
        "X-SB-Signature": sig,
        "Content-Type": "application/json",
    }


class VectorIntelAgent(AgentBase):
    """
    Intelligence agent that queries VECTOR's global surveillance platform.
    Can track aircraft, vessels, satellites, monitor conflicts, query CCTV.
    Requires VectorIntel server running on VECTORINTEL_HOST.
    """

    def __init__(self):
        super().__init__(
            name="VectorIntelAgent",
            role="intelligence_analyst",
            district="intelligence",
        )
        self._available = False
        self._check_availability()

    def _check_availability(self):
        try:
            import httpx
            path = "/api/data/all"
            r = httpx.get(
                f"{_VECTORINTEL_HOST}{path}",
                headers=_sign_request("GET", path),
                timeout=3.0,
            )
            self._available = r.status_code < 400
            if self._available:
                logger.info("[VECTOR][intel] VectorIntel platform connected")
            else:
                logger.warning(f"[VECTOR][intel] VectorIntel returned {r.status_code}")
        except Exception as e:
            logger.warning(
                f"[VECTOR][intel] VectorIntel unavailable: {e}. "
                "Start server: cd Shadowbroker-main && docker-compose up -d"
            )
            self._available = False

    async def _query(self, endpoint: str, params: dict | None = None) -> dict:
        """Make authenticated GET request to VectorIntel."""
        try:
            import httpx
            path = f"/api{endpoint}"
            headers = _sign_request("GET", path)
            url = f"{_VECTORINTEL_HOST}{path}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url, headers=headers, params=params or {})
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return {"error": str(e), "available": self._available}

    # ── Data layer methods ────────────────────────────────────────────────────

    async def get_flights(self, lat: float | None = None, lon: float | None = None, radius_km: int = 500) -> dict:
        """Get current aircraft in the air, optionally near a location."""
        params = {}
        if lat and lon:
            params = {"lat": lat, "lon": lon, "radius": radius_km}
        return await self._query("/data/snapshot/flights", params)

    async def get_vessels(self, lat: float | None = None, lon: float | None = None, radius_km: int = 500) -> dict:
        """Get AIS maritime vessels."""
        params = {}
        if lat and lon:
            params = {"lat": lat, "lon": lon, "radius": radius_km}
        return await self._query("/data/snapshot/vessels", params)

    async def get_conflicts(self) -> dict:
        """Get current conflict events from GDELT + Ukraine frontline."""
        return await self._query("/data/snapshot/conflicts")

    async def get_outages(self) -> dict:
        """Get current global internet outages (Georgia Tech IODA)."""
        return await self._query("/data/snapshot/outages")

    async def get_fires(self) -> dict:
        """Get NASA FIRMS active fire hotspots."""
        return await self._query("/data/snapshot/fires")

    async def get_satellites(self) -> dict:
        """Get active satellites with current positions."""
        return await self._query("/data/snapshot/satellites")

    async def get_cctv(self) -> dict:
        """Get the global CCTV camera index."""
        return await self._query("/data/snapshot/cctv")

    async def get_news_near(self, lat: float, lon: float, radius_km: int = 100) -> dict:
        """Get breaking news/events near a lat/lon via Shadowbroker AI layer."""
        return await self._query("/ai/news-near", {"lat": lat, "lon": lon, "radius": radius_km})

    async def get_report(self, lat: float, lon: float) -> dict:
        """Get a full intelligence report for a location."""
        return await self._query("/ai/report", {"lat": lat, "lon": lon})

    async def get_summary(self) -> dict:
        """Get a global situation summary across all layers."""
        return await self._query("/ai/summary")

    async def get_all(self) -> dict:
        """Returns all 35+ data layers in one call — use sparingly (large payload)."""
        return await self._query("/data/all")

    # ── Write methods ─────────────────────────────────────────────────────────

    async def place_pin(self, lat: float, lon: float, label: str, category: str = "intel", color: str = "cyan") -> dict:
        """Place an intelligence pin on the VectorIntel map."""
        try:
            import httpx
            path = "/api/ai/pins"
            body = json.dumps({
                "lat": lat, "lon": lon,
                "label": label,
                "category": category,
                "color": color,
            }).encode()
            headers = _sign_request("POST", path, body)
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.post(f"{_VECTORINTEL_HOST}{path}", headers=headers, content=body)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return {"error": str(e)}

    async def place_pins_batch(self, pins: list[dict]) -> dict:
        """Place multiple pins at once via /api/ai/pins/batch."""
        try:
            import httpx
            path = "/api/ai/pins/batch"
            body = json.dumps({"pins": pins}).encode()
            headers = _sign_request("POST", path, body)
            async with httpx.AsyncClient(timeout=20.0) as c:
                r = await c.post(f"{_VECTORINTEL_HOST}{path}", headers=headers, content=body)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return {"error": str(e)}

    # ── AgentBase dispatch ────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """Main dispatch — handles intelligence queries from governor."""
        action = task.get("type", "")
        params = task.get("params", {})

        if not self._available:
            self._check_availability()
            if not self._available:
                return {
                    "message": "VectorIntel platform offline. Start: cd Shadowbroker-main && docker-compose up -d",
                    "available": False,
                }

        if "flight" in action or "aircraft" in action or "plane" in action:
            data = await self.get_flights(**{k: v for k, v in params.items() if k in ("lat", "lon", "radius_km")})
            count = len(data.get("features", []) if isinstance(data, dict) else [])
            return {"message": f"VectorIntel tracking {count} aircraft currently in the air.", "data": data}

        elif "vessel" in action or "maritime" in action or "ship" in action:
            data = await self.get_vessels(**{k: v for k, v in params.items() if k in ("lat", "lon", "radius_km")})
            return {"message": "VectorIntel maritime feed retrieved.", "data": data}

        elif "conflict" in action or "war" in action or "frontline" in action:
            data = await self.get_conflicts()
            return {"message": "VectorIntel conflict intelligence retrieved.", "data": data}

        elif "outage" in action or "internet" in action:
            data = await self.get_outages()
            return {"message": "VectorIntel internet outage map retrieved.", "data": data}

        elif "fire" in action or "wildfire" in action:
            data = await self.get_fires()
            return {"message": "VectorIntel NASA FIRMS fire data retrieved.", "data": data}

        elif "satellite" in action:
            data = await self.get_satellites()
            return {"message": "VectorIntel satellite positions retrieved.", "data": data}

        elif "cctv" in action or "camera" in action or "surveillance" in action:
            data = await self.get_cctv()
            return {"message": "VectorIntel CCTV camera index retrieved.", "data": data}

        elif "news" in action or "events near" in action:
            lat = float(params.get("lat", 0))
            lon = float(params.get("lon", 0))
            data = await self.get_news_near(lat, lon, int(params.get("radius_km", 100)))
            return {"message": "Breaking intelligence near location.", "data": data}

        elif "report" in action or "intel report" in action:
            lat = float(params.get("lat", 0))
            lon = float(params.get("lon", 0))
            data = await self.get_report(lat, lon)
            return {"message": "Intelligence report generated.", "data": data}

        elif "summary" in action or "global" in action:
            data = await self.get_summary()
            return {"message": "Global situation summary.", "data": data}

        elif "pin" in action or "mark" in action:
            lat = float(params.get("lat", 0))
            lon = float(params.get("lon", 0))
            label = params.get("label", "VECTOR MARK")
            result = await self.place_pin(lat, lon, label,
                                          params.get("category", "intel"),
                                          params.get("color", "cyan"))
            return {"message": f"Intelligence pin placed at {lat:.4f}, {lon:.4f}: {label}", "data": result}

        else:
            return {
                "message": "VectorIntel capabilities: flights, vessels, satellites, cctv, conflicts, outages, fires, summary, report, news_near, place_pin",
                "available": self._available,
                "host": _VECTORINTEL_HOST,
            }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = VectorIntelAgent()
        print(f"VectorIntel available: {agent._available}")
        result = await agent.run({"type": "status"})
        print(result["message"])
        print("OK vectorintel_agent.py")

    asyncio.run(_smoke())
