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
            r = httpx.get(f"{_VECTORINTEL_HOST}/health", timeout=3.0)
            self._available = r.status_code == 200
            if self._available:
                logger.info("[VECTOR][intel] VectorIntel platform connected")
            else:
                logger.warning(f"[VECTOR][intel] VectorIntel returned {r.status_code}")
        except Exception as e:
            logger.warning(f"[VECTOR][intel] VectorIntel unavailable: {e}. Start server: cd Shadowbroker-main && docker-compose up -d")
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

    async def _command(self, commands: list[dict]) -> dict:
        """Send batch commands to VectorIntel (place pins, control map, send alerts)."""
        try:
            import httpx
            path = "/api/agent/batch"
            body = json.dumps({"commands": commands}).encode()
            headers = _sign_request("POST", path, body)
            url = f"{_VECTORINTEL_HOST}{path}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url, headers=headers, content=body)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_flights(self, lat: float | None = None, lon: float | None = None, radius_km: int = 500) -> dict:
        """Get current aircraft in the air, optionally near a location."""
        params = {}
        if lat and lon:
            params = {"lat": lat, "lon": lon, "radius": radius_km}
        return await self._query("/telemetry/flights", params)

    async def get_vessels(self, lat: float | None = None, lon: float | None = None, radius_km: int = 500) -> dict:
        """Get AIS maritime vessels."""
        params = {}
        if lat and lon:
            params = {"lat": lat, "lon": lon, "radius": radius_km}
        return await self._query("/telemetry/vessels", params)

    async def get_conflicts(self) -> dict:
        """Get current conflict events from GDELT + Ukraine frontline."""
        return await self._query("/telemetry/conflicts")

    async def get_outages(self) -> dict:
        """Get current global internet outages (Georgia Tech IODA)."""
        return await self._query("/telemetry/outages")

    async def get_fires(self) -> dict:
        """Get NASA FIRMS active fire hotspots."""
        return await self._query("/telemetry/fires")

    async def get_satellites(self) -> dict:
        """Get active satellites with current positions."""
        return await self._query("/telemetry/satellites")

    async def place_pin(self, lat: float, lon: float, label: str, category: str = "intel", color: str = "cyan") -> dict:
        """Place an intelligence pin on the VectorIntel map."""
        return await self._command([{
            "action": "place_pin",
            "lat": lat, "lon": lon,
            "label": label,
            "category": category,
            "color": color,
        }])

    async def run(self, task: dict) -> dict:
        """Main dispatch — handles intelligence queries from governor."""
        action = task.get("type", "")
        params = task.get("params", {})

        if not self._available:
            self._check_availability()
            if not self._available:
                return {"message": "VectorIntel platform offline. Start: cd Shadowbroker-main && docker-compose up -d"}

        if "flight" in action or "aircraft" in action:
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

        elif "pin" in action or "mark" in action:
            lat = float(params.get("lat", 0))
            lon = float(params.get("lon", 0))
            label = params.get("label", "VECTOR MARK")
            result = await self.place_pin(lat, lon, label)
            return {"message": f"Intelligence pin placed at {lat:.4f}, {lon:.4f}: {label}", "data": result}

        else:
            return {
                "message": "VectorIntel capabilities: flights, vessels, conflicts, outages, fires, satellites, place_pin",
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
        print("✅ vectorintel_agent OK")

    asyncio.run(_smoke())
