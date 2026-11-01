"""Status router — /status, /health."""

import sys

__all__ = [
    "daily_info",
    "get_uptime_seconds",
    "health_endpoint",
    "router",
    "START_TIME",
    "status_endpoint",
    "system_metrics",
]

import asyncio
import time
import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
import httpx

from core.api.schemas import StatusResponse, HealthResponse
from core.api.crud import get_memory_stats
from core.api.cache import health_cache
from core.config import CONFIG

router = APIRouter(tags=["status"])

_OLLAMA_HOST = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
if not _OLLAMA_HOST.startswith("http"):
    _OLLAMA_HOST = "http://" + _OLLAMA_HOST

START_TIME = dt.datetime.now(dt.timezone.utc)
_STATUS_CACHE: dict[str, Any] = {
    "models": None,
    "models_ts": 0.0,
    "tts": None,
    "tts_ts": 0.0,
}
_OLLAMA_STATUS_TTL_SECONDS = 30.0
_TTS_STATUS_TTL_SECONDS = 300.0


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

    models_status = await _check_ollama_models_cached()

    # Last reflect timestamp from episodic memory
    last_reflect = None
    try:
        from core.api.crud import recall_episodes
        reflect_events = recall_episodes("reflect daily review", limit=1, event_type="reflect")
        if reflect_events:
            last_reflect = reflect_events[0].get("timestamp")
    except Exception:
        logger.warning("[VECTOR] suppressed exception (fallback degraded)", exc_info=True)

    _loop_running = _get_loop_running()

    models_status.update(_get_tts_status_cached())

    return StatusResponse(
        loop_running=_loop_running,
        uptime_seconds=get_uptime_seconds(),
        models=models_status,
        memory=memory_stats,
        agents={"count": agent_count, "districts": districts},
        vector_version="1.0.0",
        last_reflect=last_reflect,
    )


def _get_loop_running() -> bool:
    """Read loop state without constructing the expensive autonomous loop.

    Same rule /health uses. This used to be a stub that always returned False, so
    /status said the loop was down while /health showed it ticking (2026-09-25)."""
    try:
        from core.loop.loop_state import get_runtime
        rt = get_runtime()
        return bool(rt["running"] or rt["tick_count"] > 0)
    except Exception:
        return False


def _get_tts_status_cached() -> dict[str, str]:
    """Expose voice engine status without loading audio models on every poll."""
    now = time.monotonic()
    cached = _STATUS_CACHE.get("tts")
    if cached and now - float(_STATUS_CACHE.get("tts_ts") or 0.0) < _TTS_STATUS_TTL_SECONDS:
        return dict(cached)

    status = {"tts_engine": "unknown", "tts_kokoro_ok": "false"}
    try:
        from pathlib import Path

        voice_cfg = CONFIG.get("voice", {}) if isinstance(CONFIG, dict) else {}
        model_dir = Path(voice_cfg.get("kokoro_model_dir", "./models/kokoro"))
        has_kokoro_files = (
            (model_dir / "voices-v1.0.bin").exists()
            and (
                (model_dir / "kokoro-v1.0.onnx").exists()
                or (model_dir / "kokoro-v1.0.fp16-gpu.onnx").exists()
            )
        )
        status = {
            "tts_engine": "kokoro_configured" if has_kokoro_files else "pyttsx3",
            "tts_kokoro_ok": "unknown" if has_kokoro_files else "false",
        }
    except Exception:
        logger.debug("[VECTOR][api][status] tts status unavailable", exc_info=True)

    _STATUS_CACHE["tts"] = status
    _STATUS_CACHE["tts_ts"] = now
    return dict(status)

_prev_net = {"bytes_sent": 0, "bytes_recv": 0, "ts": 0.0}

@router.get("/system")
async def system_metrics():
    """Get real-time OS metrics via psutil."""
    import psutil as _psutil
    import time as _time
    cpu = await asyncio.to_thread(_psutil.cpu_percent, 0.3)   # interval blocks; keep the event loop free
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
        logger.warning("[VECTOR] suppressed exception (fallback degraded)", exc_info=True)

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

def _format_health_error(e: Exception) -> str:
    """Render an exception for a /health check field, distinguishing timeouts
    (whose str() is often empty, e.g. httpx.ReadTimeout) from real failures."""
    detail = str(e).strip() or "no details (likely a timeout)"
    return f"error: {type(e).__name__}: {detail}"


@router.get("/health", response_model=HealthResponse)
async def health_endpoint():
    """Detailed health check for monitoring. Cached briefly (health_cache TTL)
    so repeated polling — e.g. the watchdog's health loop — doesn't re-run the
    Ollama probe and the SQLite stats query on every hit."""
    cached = health_cache.get("status_health")
    if cached is not None:
        return cached

    import datetime
    checks = {}

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_OLLAMA_HOST}/api/tags")
            checks["ollama"] = "ok" if r.status_code == 200 else f"http_{r.status_code}"
    except Exception as e:
        checks["ollama"] = _format_health_error(e)

    # Check SQLite — off the event loop. get_memory_stats() constructs
    # EpisodicMemory() and runs several sequential SELECT COUNT(*) queries
    # under the shared episodic _write_lock; running it inline here would
    # block every other coroutine on this loop (including the Ollama probe
    # above) for the duration.
    try:
        memory_stats = await asyncio.to_thread(get_memory_stats)
        checks["sqlite"] = "ok" if memory_stats and "error" not in memory_stats else "error"
    except Exception as e:
        checks["sqlite"] = _format_health_error(e)

    # Check the autonomous loop heartbeat (2026-08-05, KNOWN_ISSUES.md #0):
    # the loop thread was observed to silently deadlock — process alive, 95
    # threads, 1.1GB RSS, but 0s of CPU over a 20s sample — while `/health`
    # kept answering {"status": "ok"} because nothing checked heartbeat
    # freshness. loop_state.py's heartbeat file already has a staleness rule
    # (_HEARTBEAT_MAX_AGE_SEC); this is what finally surfaces it.
    #
    # get_loop_liveness() (not loop_state.get_runtime()) is used deliberately:
    # get_runtime()'s in-process fast path returns the module-level
    # `_rt_running` flag, which is set True once and never reset when the
    # loop thread hangs — it would have reported "running" for the entire
    # ~5.5 hours this bug was live. get_loop_liveness() always reads the
    # on-disk heartbeat file directly instead, which is the one signal that
    # genuinely stops advancing the moment the loop thread hangs.
    loop_detail: dict | None = None
    try:
        from core.loop.loop_state import get_loop_liveness
        live = get_loop_liveness()
        # live["state"] is "running" | "stale" | "not_started"; the health
        # check's own vocabulary is "ok" | "stale" | "not_started" to match
        # the "ok"/"error: ..." convention the ollama/sqlite checks already use.
        checks["loop"] = {"running": "ok", "stale": "stale", "not_started": "not_started"}[live["state"]]
        loop_detail = {
            "tick_count": live["tick_count"],
            "age_sec": live["age_sec"],
            "pid": live["pid"],
            "run_loop_opt_out": live["run_loop_opt_out"],
        }
    except Exception as e:
        checks["loop"] = _format_health_error(e)

    # Whether a stale loop heartbeat flips overall `status` away from "ok":
    # YES, deliberately. The entire point of this fix is that "status: ok"
    # while the brain is dead is what let this hide for days undetected —
    # ollama/sqlite being reachable says nothing about whether the
    # observe->think->act->reflect loop is still ticking.
    # "not_started" does NOT flip status: it is indistinguishable from a
    # legitimate VECTOR_API_RUN_LOOP=0 API-only deployment (no brain by
    # design — must not report unhealthy for that) and from a loop still
    # cold-booting (observed up to ~71s for a Whisper large-v3 load before
    # the first tick). Only "stale" — a heartbeat that WAS fresh and has
    # since gone quiet — is unambiguous evidence of a hang.
    all_ok = (
        checks.get("ollama") == "ok"
        and checks.get("sqlite") == "ok"
        and checks.get("loop") != "stale"
        and not str(checks.get("loop", "")).startswith("error")
    )

    result = HealthResponse(
        status="ok" if all_ok else "degraded",
        checks=checks,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        version="1.0.0",
        loop_detail=loop_detail,
    )
    health_cache.set("status_health", result)
    return result

async def _check_ollama_models() -> dict:
    """Dynamically check which Ollama models are loaded."""
    models_status = {}
    try:
        # 0.5 s was shorter than a busy Ollama (or a busy API) needs to answer /api/tags: 78 timeouts per session, each logged
        # with an EMPTY message (httpx timeouts stringify to ''), and the HUD showed models as unreachable.
        async with httpx.AsyncClient(timeout=2.0) as client:
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
                        "deep": "vector-reasoning",
                        "chairman": "vector-reasoning",
                    }.get(model_key, model_key)

                    models_status[model_key] = "loaded" if _ollama_model_loaded(model_name, loaded) else "unloaded"
            else:
                for key in ["focus", "reasoning", "coder", "ambient", "deep", "chairman"]:
                    models_status[key] = "error"
    except Exception as e:
        logger.warning(f"[VECTOR][api][status] Ollama check failed: {type(e).__name__}: {e}")
        models_status = {"focus": "unavailable", "reasoning": "unavailable"}

    if not models_status:
        models_status = {"focus": "unknown", "reasoning": "unknown"}

    return models_status


def _ollama_model_loaded(model_name: str, loaded_names: list[str]) -> bool:
    """Match Ollama model names with or without tags, e.g. vector-focus[:latest]."""
    expected = model_name.split(":", 1)[0]
    for loaded in loaded_names:
        base = str(loaded).split(":", 1)[0]
        if loaded == model_name or base == expected:
            return True
    return False


async def _check_ollama_models_cached() -> dict[str, str]:
    now = time.monotonic()
    cached = _STATUS_CACHE.get("models")
    if cached and now - float(_STATUS_CACHE.get("models_ts") or 0.0) < _OLLAMA_STATUS_TTL_SECONDS:
        return dict(cached)

    models_status = await _check_ollama_models()
    _STATUS_CACHE["models"] = models_status
    _STATUS_CACHE["models_ts"] = now
    return dict(models_status)


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
