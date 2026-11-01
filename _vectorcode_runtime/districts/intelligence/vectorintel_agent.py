"""VECTOR Intel Bridge — connects to the VectorIntel / Shadowbroker surveillance platform.

VectorIntel is VECTOR's real-time global intelligence layer powered by Shadowbroker:
- 5,000+ tracked aircraft (commercial + military + private jets)
- 25,000+ AIS maritime vessels, yacht alerts, carrier group tracking
- 2,000+ satellites (recon, SAR, SIGINT, nav)
- 11,000+ CCTV cameras globally
- GDELT conflict events, Ukraine frontline (LiveUAMap), CrowdThreat
- NASA FIRMS fires, earthquakes, wastewater pathogen monitoring
- SAR satellite imagery (Sentinel-1/Copernicus — floods, deformation, damage)
- GPS jamming detection, SIGINT/radio intercepts
- Unusual Whales prediction markets, NUFORC UAP sightings
- InfoNet mesh network, encrypted DMs, Meshtastic radio, dead drops
- AI correlation engine, analysis zones, intelligence briefings
- Alert dispatch to Discord/Telegram (20 branded signature types)

Setup: Run VectorIntel server on port 8002 (VECTOR runs on 8000).
  Option A (Windows): tools/start_shadowbroker.bat  (from V.E.C.T.O.R. Codebase root)
  Option B (Linux):   tools/start_shadowbroker.sh
  Option C (manual):  cd districts/intelligence/shadowbroker_server && PORT=8002 python main.py

Env vars:
  VECTORINTEL_HOST=http://127.0.0.1:8002      (Shadowbroker backend URL)
  VECTORINTEL_SECRET=your_hmac_secret_here     (from Shadowbroker "Connect OpenClaw" modal)
  TELEGRAM_BOT_TOKEN=...                       (for intelligence alerts)
  TELEGRAM_CHAT_ID=...
  SHADOWBROKER_DISCORD_WEBHOOK=...             (for Discord alerts)
"""

import sys
import os
import uuid
import asyncio
from pathlib import Path

from loguru import logger
from core.city.agent_base import AgentBase

_VECTORINTEL_HOST   = os.environ.get("VECTORINTEL_HOST", "http://127.0.0.1:8002")
_VECTORINTEL_SECRET = os.environ.get("VECTORINTEL_SECRET", "")
_SKILL_PATH         = Path(__file__).parent / "shadowbroker" / "SKILL.md"


def _load_skill() -> str:
    if _SKILL_PATH.exists():
        return _SKILL_PATH.read_text(encoding="utf-8")
    return ""


class VectorIntelAgent(AgentBase):
    """
    Intelligence agent that queries VECTOR's global surveillance platform (Shadowbroker).
    Delegates all API calls to ShadowBrokerClient from the absorbed SDK.
    Requires VectorIntel/Shadowbroker server running on VECTORINTEL_HOST.
    """

    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="VectorIntelAgent",
            district="intelligence",
        )
        self.capabilities = ["flights", "gdelt", "intel", "intelligence", "military_flights", "security_alert", "surveillance", "vessels"]
        self._skill_prompt = _load_skill()
        self._available    = False
        self._sb           = None
        self._init_client()
        # Phase 2B: subscribe to intelligence events
        self.subscribe_to("security_alert")
        self.subscribe_to("research_complete")

    async def handle_event(self, event: dict) -> dict:
        """Phase 2B: Cross-correlate OSINT on security/research events."""
        await super().handle_event(event)
        et = event.get("event_type", "")
        if et in ("security_alert", "research_complete"):
            try:
                data = event.get("data", {})
                logger.info(f"[VECTOR][intel] event-triggered OSINT: {et}")
                await self.run({"type": "global_intel", "params": {"context": str(data)[:200]}})
            except Exception as e:
                logger.debug(f"[VECTOR][intel] handle_event failed: {e}")
        return {"status": "handled", "agent": self.name, "event": et}

    def _init_client(self):
        """Create ShadowBrokerClient and check availability."""
        try:
            # Ensure SDK dir is on path so bare imports (from sb_signatures import sig) work
            _sdk = str(Path(__file__).parent / "shadowbroker")
            if _sdk not in sys.path:
                sys.path.insert(0, _sdk)
            from districts.intelligence.shadowbroker.sb_query import ShadowBrokerClient
            self._sb = ShadowBrokerClient(
                base_url=_VECTORINTEL_HOST,
                hmac_secret=_VECTORINTEL_SECRET,
            )
        except ImportError as e:
            logger.warning(f"[VECTOR][intel] ShadowBrokerClient import failed: {e}")
        self._check_availability()

    def _check_availability(self):
        """Quick sync check — tries /api/ai/summary to confirm server is up."""
        if self._sb is None:
            self._available = False
            return
        try:
            import httpx
            # Use the client's own signing logic via a direct GET to summary
            path = "/api/health"
            r = httpx.get(f"{_VECTORINTEL_HOST}{path}", timeout=5.0)
            self._available = r.status_code < 500
            if self._available:
                logger.info("[VECTOR][intel] VectorIntel platform connected at {}", _VECTORINTEL_HOST)
            else:
                logger.warning("[VECTOR][intel] VectorIntel returned {}", r.status_code)
        except Exception as e:
            logger.warning(
                "[VECTOR][intel] VectorIntel unavailable: {}. "
                "Start: run tools/start_shadowbroker.bat from VECTOR Codebase root", e
            )
            self._available = False

    def _get_alerts(self):
        """Build AlertDispatcher from env config."""
        from districts.intelligence.shadowbroker.sb_alerts import AlertDispatcher
        d = AlertDispatcher()
        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        tg_chat  = os.environ.get("TELEGRAM_CHAT_ID", "")
        discord  = os.environ.get("SHADOWBROKER_DISCORD_WEBHOOK", "")
        if tg_token and tg_chat:
            d.add_telegram(tg_token, tg_chat)
        if discord:
            d.add_discord(discord)
        return d

    # ── Convenience wrappers (used by API router) ─────────────────────────────
    # fast tier (/api/live-data/fast):  flights, ships, sats, SIGINT, CCTV, GPS jamming
    # slow tier (/api/live-data/slow):  GDELT, news, earthquakes, prediction markets, fires

    async def _fast(self) -> dict:
        """Fetch all fast-tier layers (flights, ships, satellites, CCTV, SIGINT)."""
        try:
            r = await self._sb._get("/api/live-data/fast")
            return r.json() if r.status_code < 400 else {}
        except Exception:
            return {}

    async def _slow(self) -> dict:
        """Fetch all slow-tier layers (GDELT, news, earthquakes, markets, fires)."""
        try:
            r = await self._sb._get("/api/live-data/slow")
            return r.json() if r.status_code < 400 else {}
        except Exception:
            return {}

    async def get_flights(self, lat=None, lon=None, radius_km: int = 500) -> dict:
        data = await self._fast()
        return {k: data.get(k, []) for k in
                ("military_flights", "commercial_flights", "tracked_flights", "private_jets")}

    async def get_vessels(self, lat=None, lon=None, radius_km: int = 500) -> dict:
        data = await self._fast()
        return {"ships": data.get("ships", [])}

    async def get_conflicts(self) -> dict:
        data = await self._slow()
        return {k: data.get(k, []) for k in ("gdelt", "liveuamap", "crowdthreat")}

    async def get_outages(self) -> dict:
        data = await self._slow()
        return {"internet_outages": data.get("internet_outages", [])}

    async def get_fires(self) -> dict:
        data = await self._slow()
        return {"firms_fires": data.get("firms_fires", [])}

    async def get_satellites(self) -> dict:
        data = await self._fast()
        return {"satellites": data.get("satellites", [])}

    async def get_cctv(self) -> dict:
        data = await self._fast()
        return {"cctv": data.get("cctv", [])}

    async def get_news_near(self, lat: float, lon: float, radius_km: int = 100) -> dict:
        return await self._sb.get_news_near(lat=lat, lng=lon, radius=radius_km)

    async def get_report(self, lat: float = 0.0, lon: float = 0.0) -> dict:
        return await self._sb.get_report()

    async def get_summary(self) -> dict:
        return await self._sb.get_summary()

    async def get_all(self) -> dict:
        fast = await self._fast()
        slow = await self._slow()
        return {**fast, **slow}

    async def place_pin(self, lat: float, lon: float, label: str,
                        category: str = "intel", color: str = "cyan") -> dict:
        return await self._sb.place_pin(lat=lat, lng=lon, label=label, category=category)

    async def place_pins_batch(self, pins: list[dict]) -> dict:
        return await self._sb.place_pins_batch(pins)

    # ── Intel alert dispatch ──────────────────────────────────────────────────

    async def send_intel_alert(self, sig_type: str, message: str) -> dict:
        alerts = self._get_alerts()
        if not alerts.channels:
            return {"ok": False, "message": "No alert channels configured. Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID or SHADOWBROKER_DISCORD_WEBHOOK."}
        results = await alerts.send(sig_type, message)
        return {"ok": True, "delivered": results}

    # ── AgentBase dispatch ────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """Main dispatch — handles intelligence queries from governor."""
        action = task.get("type", "")
        params = task.get("params", {})

        if not self._available:
            self._check_availability()
            if not self._available:
                return {
                    "message": "VectorIntel platform offline. Start: run tools/start_shadowbroker.bat from VECTOR Codebase root",
                    "available": False,
                }

        sb = self._sb

        # ── Aviation ─────────────────────────────────────────────────────────
        if "flight" in action or "aircraft" in action or "plane" in action:
            if params.get("callsign") or params.get("query"):
                q = params.get("callsign") or params.get("query")
                data = await sb.send_command("find_flights", {"query": q, "compact": True})
                return {"message": f"Flight search for '{q}'.", "data": data}
            data = await self.get_flights(params.get("lat"), params.get("lon"),
                                          int(params.get("radius_km", 500)))
            return {"message": "Live aircraft tracking retrieved.", "data": data}

        # ── Maritime ──────────────────────────────────────────────────────────
        elif "vessel" in action or "maritime" in action or "ship" in action:
            if params.get("query"):
                data = await sb.send_command("find_ships", {"query": params["query"], "compact": True})
                return {"message": f"Ship search for '{params['query']}'.", "data": data}
            data = await self.get_vessels()
            return {"message": "AIS maritime feed retrieved.", "data": data}

        # ── Satellites ────────────────────────────────────────────────────────
        elif "satellite" in action:
            data = await self.get_satellites()
            return {"message": "Satellite positions retrieved.", "data": data}

        # ── Conflicts / geopolitics ───────────────────────────────────────────
        elif "conflict" in action or "war" in action or "frontline" in action:
            data = await self.get_conflicts()
            return {"message": "Conflict intelligence retrieved (GDELT + LiveUAMap + CrowdThreat).", "data": data}

        # ── Internet outages ──────────────────────────────────────────────────
        elif "outage" in action or "internet" in action:
            data = await self.get_outages()
            return {"message": "Internet outage map retrieved.", "data": data}

        # ── Fires ─────────────────────────────────────────────────────────────
        elif "fire" in action or "wildfire" in action:
            data = await self.get_fires()
            return {"message": "NASA FIRMS fire hotspots retrieved.", "data": data}

        # ── CCTV ──────────────────────────────────────────────────────────────
        elif "cctv" in action or "camera" in action or "surveillance" in action:
            data = await self.get_cctv()
            return {"message": "CCTV camera index retrieved.", "data": data}

        # ── SIGINT / radio ────────────────────────────────────────────────────
        elif "sigint" in action or "radio" in action or "jamming" in action:
            data = await sb.get_layer_slice(["sigint", "kiwisdr", "gps_jamming"])
            return {"message": "SIGINT and RF intelligence retrieved.", "data": data}

        # ── Earthquakes / seismic ─────────────────────────────────────────────
        elif "earthquake" in action or "seismic" in action:
            data = await sb.get_layer_slice(["earthquakes"])
            return {"message": "Seismic activity retrieved.", "data": data}

        # ── Prediction markets / finance ──────────────────────────────────────
        elif "market" in action or "prediction" in action or "unusual_whales" in action:
            data = await sb.get_prediction_markets()
            return {"message": "Prediction markets data retrieved.", "data": data}

        # ── Correlations ──────────────────────────────────────────────────────
        elif "correlation" in action:
            data = await sb.get_correlations()
            return {"message": "Cross-layer correlations retrieved.", "data": data}

        # ── Cross-layer search ────────────────────────────────────────────────
        elif "search" in action:
            q = params.get("query", "")
            data = await sb.send_command("search_telemetry", {"query": q, "compact": True})
            return {"message": f"Cross-layer search: '{q}'.", "data": data}

        # ── Proximity scan (everything near a location) ───────────────────────
        elif "near_me" in action or "near me" in action or "proximity" in action:
            lat = float(params.get("lat", 0))
            lon = float(params.get("lon", 0))
            radius = float(params.get("radius_miles", 100))
            data = await sb.get_near_me(lat, lon, radius)
            return {"message": f"Full proximity scan within {radius} miles.", "data": data}

        # ── News / GDELT near location ────────────────────────────────────────
        elif "news" in action or "events near" in action:
            lat = float(params.get("lat", 0))
            lon = float(params.get("lon", 0))
            data = await self.get_news_near(lat, lon, int(params.get("radius_km", 100)))
            return {"message": "News and GDELT events near location.", "data": data}

        # ── Intel report ──────────────────────────────────────────────────────
        elif "report" in action or "intel report" in action:
            data = await self.get_report()
            return {"message": "Full intelligence report generated.", "data": data}

        # ── Global summary ────────────────────────────────────────────────────
        elif "summary" in action or "global" in action:
            data = await self.get_summary()
            return {"message": "Global situation summary.", "data": data}

        # ── SAR / satellite imagery ───────────────────────────────────────────
        elif "sar" in action:
            sub = params.get("sub", "status")
            if sub == "status":
                data = await sb.sar_status()
            elif sub == "anomalies":
                data = {"anomalies": await sb.sar_anomalies_recent()}
            elif sub == "near":
                data = {"near": await sb.sar_anomalies_near(
                    lat=float(params.get("lat", 0)),
                    lng=float(params.get("lon", 0)),
                    radius_km=int(params.get("radius_km", 50)),
                )}
            else:
                data = await sb.sar_status()
            return {"message": "SAR satellite intelligence.", "data": data}

        # ── Satellite imagery (Sentinel-2 optical) ────────────────────────────
        elif "satellite_image" in action or "imagery" in action:
            lat = float(params.get("lat", 0))
            lon = float(params.get("lon", 0))
            data = await sb.get_satellite_images(lat=lat, lng=lon, count=3)
            return {"message": f"Sentinel-2 imagery for {lat:.4f}, {lon:.4f}.", "data": data}

        # ── Geocode ───────────────────────────────────────────────────────────
        elif "geocode" in action:
            q = params.get("query", "")
            data = await sb.geocode(q)
            return {"message": f"Geocoded: {q}", "data": data}

        # ── Pin placement ─────────────────────────────────────────────────────
        elif "pin" in action or "mark" in action:
            lat = float(params.get("lat", 0))
            lon = float(params.get("lon", 0))
            label = params.get("label", "VECTOR MARK")
            category = params.get("category", "research")
            data = await sb.place_pin(
                lat=lat, lng=lon, label=label, category=category,
                source="VECTOR", confidence=0.9,
            )
            return {"message": f"Pin placed at {lat:.4f}, {lon:.4f}: {label}", "data": data}

        # ── Analysis zones ────────────────────────────────────────────────────
        elif "analysis_zone" in action or "zone" in action:
            sub = params.get("sub", "list")
            if sub == "list":
                data = await sb.list_analysis_zones()
            elif sub == "place":
                data = await sb.place_analysis_zone(
                    lat=float(params.get("lat", 0)),
                    lng=float(params.get("lon", 0)),
                    title=params.get("title", "VECTOR Assessment"),
                    body=params.get("body", ""),
                    category=params.get("category", "analysis"),
                    severity=params.get("severity", "medium"),
                )
            elif sub == "clear":
                data = await sb.clear_analysis_zones()
            else:
                data = await sb.list_analysis_zones()
            return {"message": "Analysis zones.", "data": data}

        # ── InfoNet mesh network ──────────────────────────────────────────────
        elif "infonet" in action or "mesh" in action:
            sub = params.get("sub", "read")
            if sub == "read":
                data = await sb.read_infonet()
            elif sub == "post":
                data = await sb.post_to_infonet(params.get("message", ""))
            elif sub == "mesh_listen":
                data = await sb.listen_mesh(params.get("region", "US"))
            elif sub == "mesh_send":
                data = await sb.send_mesh(params.get("region", "US"), params.get("message", ""))
            else:
                data = await sb.read_infonet()
            return {"message": "InfoNet / mesh network.", "data": data}

        # ── Alert dispatch ────────────────────────────────────────────────────
        elif "alert" in action:
            return await self.send_intel_alert(
                sig_type=params.get("sig_type", "intel"),
                message=params.get("message", ""),
            )

        # ── Morning/evening briefing ──────────────────────────────────────────
        elif "brief" in action or "briefing" in action or "digest" in action:
            from districts.intelligence.shadowbroker.sb_briefing import format_near_me_digest
            lat = float(params.get("lat", 0))
            lon = float(params.get("lon", 0))
            brief = await format_near_me_digest(sb, lat, lon, radius=params.get("radius_miles", 100))
            return {"message": brief}

        else:
            return {
                "message": (
                    "VectorIntel capabilities: flights, vessels, satellites, cctv, sigint, "
                    "conflicts, outages, fires, earthquakes, markets, correlations, "
                    "search, near_me, news, report, summary, sar, satellite_image, geocode, "
                    "pin, analysis_zone, infonet, alert, brief"
                ),
                "available": self._available,
                "host": _VECTORINTEL_HOST,
                "skill_loaded": bool(self._skill_prompt),
            }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = VectorIntelAgent()
        print(f"VectorIntelAgent available: {agent._available}")
        print(f"SKILL.md loaded: {len(agent._skill_prompt)} chars")
        result = await agent.run({"type": "status", "params": {}})
        print(result["message"][:100])
        print("OK vectorintel_agent.py")

    asyncio.run(_smoke())
