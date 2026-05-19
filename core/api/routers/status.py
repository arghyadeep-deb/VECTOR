"""Status router — /status, /health."""

import sys
import time
import datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
import httpx

from core.api.schemas import StatusResponse, HealthResponse
from core.api.crud import get_memory_stats
from core.config import CONFIG

router = APIRouter(tags=["status"])

_OLLAMA_HOST = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
if not _OLLAMA_HOST.startswith("http"):
    _OLLAMA_HOST = "http://" + _OLLAMA_HOST

START_TIME = dt.datetime.now(dt.timezone.utc)


def get_uptime_seconds() -> int:
    return int((dt.datetime.now(dt.timezone.utc) - START_TIME).total_seconds())

@router.get("/status", response_model=StatusResponse)
async def status_endpoint():
    """Get current VECTOR status."""
    try:
        memory_stats = get_memory_stats()
    except Exception as e:
        logger.warning(f"[VECTOR][api][status] memory stats failed: {e}")
        memory_stats = {"error": str(e)}

    try:
        from core.city.agent_registry import get_registry
        agents = get_registry().list_all()
        agent_count = len(agents)
        districts = sorted({a.get("district", "") for a in agents})
    except Exception as e:
        logger.warning(f"[VECTOR][api][status] agent list failed: {e}")
        agents = []
        agent_count = 0
        districts = []

    # Dynamically check Ollama models
    models_status = await _check_ollama_models()

    # Last reflect timestamp from episodic memory
    last_reflect = None
    try:
        from core.api.crud import recall_episodes
        reflect_events = recall_episodes("reflect daily review", limit=1, event_type="reflect")
        if reflect_events:
            last_reflect = reflect_events[0].get("timestamp")
    except Exception:
        pass

    _loop_running = False
    try:
        from core.loop.autonomous_loop import AutonomousLoop
        _loop = AutonomousLoop()
        _loop_running = getattr(_loop, "_running", False)
    except Exception:
        pass

    # Surface TTS engine so UI can warn about Kokoro missing
    try:
        from core.voice.tts import VoiceTTS
        _tts = VoiceTTS()
        models_status["tts_engine"] = "kokoro" if _tts._kokoro_ok else "pyttsx3"
        models_status["tts_kokoro_ok"] = _tts._kokoro_ok
    except Exception:
        models_status["tts_engine"] = "unknown"
        models_status["tts_kokoro_ok"] = False

    return StatusResponse(
        loop_running=_loop_running,
        uptime_seconds=get_uptime_seconds(),
        models=models_status,
        memory=memory_stats,
        agents={"count": agent_count, "districts": districts},
        vector_version="1.0.0",
        last_reflect=last_reflect,
    )

_prev_net = {"bytes_sent": 0, "bytes_recv": 0, "ts": 0.0}

@router.get("/system")
async def system_metrics():
    """Get real-time OS metrics via psutil."""
    import psutil as _psutil
    import time as _time
    cpu = _psutil.cpu_percent(interval=0.3)
    mem = _psutil.virtual_memory()
    disk = _psutil.disk_usage('/')
    net = _psutil.net_io_counters()
    now = _time.time()

    global _prev_net
    dt = now - _prev_net["ts"] if _prev_net["ts"] > 0 else 1
    net_sent_rate = max(0, (net.bytes_sent - _prev_net["bytes_sent"]) / dt / (1024**2)) if _prev_net["bytes_sent"] > 0 else 0
    net_recv_rate = max(0, (net.bytes_recv - _prev_net["bytes_recv"]) / dt / (1024**2)) if _prev_net["bytes_recv"] > 0 else 0
    _prev_net = {"bytes_sent": net.bytes_sent, "bytes_recv": net.bytes_recv, "ts": now}

    gpu_percent = None
    gpu_temp_c = None
    gpu_mem_percent = None
    try:
        import subprocess as _sp
        r = _sp.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split(", ")
            if len(parts) >= 4:
                gpu_percent = float(parts[0])
                gpu_mem_percent = round(float(parts[1]) / float(parts[2]) * 100, 1) if float(parts[2]) > 0 else 0
                gpu_temp_c = float(parts[3])
    except Exception:
        pass

    return {
        "cpu_percent": cpu,
        "memory_percent": mem.percent,
        "memory_used_gb": round(mem.used / (1024**3), 1),
        "memory_total_gb": round(mem.total / (1024**3), 1),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024**3), 1),
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "net_sent_mb": round(net.bytes_sent / (1024**2), 1),
        "net_recv_mb": round(net.bytes_recv / (1024**2), 1),
        "net_sent_rate_mbs": round(net_sent_rate, 2),
        "net_recv_rate_mbs": round(net_recv_rate, 2),
        "gpu_percent": gpu_percent,
        "gpu_temp_c": gpu_temp_c,
        "gpu_mem_percent": gpu_mem_percent,
        "uptime_seconds": get_uptime_seconds(),
    }

@router.get("/health", response_model=HealthResponse)
async def health_endpoint():
    """Detailed health check for monitoring."""
    import datetime
    checks = {}

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_OLLAMA_HOST}/api/tags")
            checks["ollama"] = "ok" if r.status_code == 200 else f"http_{r.status_code}"
    except Exception as e:
        checks["ollama"] = f"error: {e}"

    # Check SQLite
    try:
        memory_stats = get_memory_stats()
        checks["sqlite"] = "ok" if memory_stats and "error" not in memory_stats else "error"
    except Exception as e:
        checks["sqlite"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        checks=checks,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        version="1.0.0",
    )

async def _check_ollama_models() -> dict:
    """Dynamically check which Ollama models are loaded."""
    models_status = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                loaded = [m["name"] for m in r.json().get("models", [])]
                # Check key models
                for model_key in ["focus", "reasoning", "coder", "ambient", "deep", "chairman"]:
                    model_name = {
                        "focus": "vector-focus",
                        "reasoning": "vector-reasoning",
                        "coder": "vector-coder",
                        "ambient": "vector-ambient",
                        "deep": "vector-deep",
                        "chairman": "vector-chairman",
                    }.get(model_key, model_key)

                    models_status[model_key] = "loaded" if model_name in loaded else "unloaded"
            else:
                for key in ["focus", "reasoning", "coder", "ambient", "deep", "chairman"]:
                    models_status[key] = "error"
    except Exception as e:
        logger.warning(f"[VECTOR][api][status] Ollama check failed: {e}")
        models_status = {"focus": "unavailable", "reasoning": "unavailable"}

    if not models_status:
        models_status = {"focus": "unknown", "reasoning": "unknown"}

    return models_status


@router.get("/daily")
async def daily_info():
    """
    Daily briefing: weather, location, date, day summary.
    Uses free public APIs — no auth required.
    """
    import datetime as _dt

    now = _dt.datetime.now()
    result = {
        "date": now.strftime("%A, %d %B %Y"),
        "time": now.strftime("%H:%M"),
        "weather": None,
        "location": None,
        "sunrise": None,
        "sunset": None,
        "aqi": None,
    }

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            # Step 1: Get location from IP (free, no key)
            loc_r = await client.get("http://ip-api.com/json/?fields=city,regionName,country,lat,lon,timezone")
            if loc_r.status_code == 200:
                loc = loc_r.json()
                result["location"] = f"{loc.get('city', '?')}, {loc.get('regionName', '')}, {loc.get('country', '')}"
                lat, lon = loc.get("lat", 0), loc.get("lon", 0)

                # Step 2: Weather from Open-Meteo (free, no key)
                wx_r = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat, "longitude": lon,
                        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature",
                        "daily": "sunrise,sunset",
                        "timezone": loc.get("timezone", "auto"),
                        "forecast_days": 1,
                    }
                )
                if wx_r.status_code == 200:
                    wx = wx_r.json()
                    cur = wx.get("current", {})
                    daily = wx.get("daily", {})
                    temp = cur.get("temperature_2m")
                    feels = cur.get("apparent_temperature")
                    humidity = cur.get("relative_humidity_2m")
                    wind = cur.get("wind_speed_10m")
                    code = cur.get("weather_code", 0)

                    # WMO weather code to description
                    _WX = {
                        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                        45: "Foggy", 48: "Icy fog", 51: "Light drizzle", 53: "Drizzle",
                        55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
                        71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Rain showers",
                        81: "Heavy showers", 82: "Violent showers", 95: "Thunderstorm",
                        96: "Thunderstorm + hail", 99: "Thunderstorm + heavy hail",
                    }
                    desc = _WX.get(code, f"Code {code}")

                    result["weather"] = {
                        "temp_c": round(temp, 1) if temp is not None else None,
                        "feels_c": round(feels, 1) if feels is not None else None,
                        "humidity_pct": humidity,
                        "wind_kmh": round(wind, 1) if wind is not None else None,
                        "description": desc,
                        "code": code,
                    }

                    sunrises = daily.get("sunrise", [])
                    sunsets = daily.get("sunset", [])
                    if sunrises:
                        result["sunrise"] = sunrises[0][11:16]  # HH:MM
                    if sunsets:
                        result["sunset"] = sunsets[0][11:16]

    except Exception as e:
        logger.warning(f"[VECTOR][api][daily] fetch failed: {e}")

    return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ status.py OK")
