"""Sensing router — /sensing/status."""


__all__ = [
    "router",
    "sensing_health",
    "sensing_screen",
    "sensing_status",
    "sensing_system",
]


import asyncio
from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/sensing", tags=["sensing"])

@router.get("/status")
async def sensing_status():
    """Get health monitor snapshot (fatigue, energy, system load)."""
    try:
        from core.sensing.health_monitor import HealthMonitor
        monitor = HealthMonitor()
        snap = monitor.get_health_snapshot()
        camera_available = snap.get("camera_available", False)
        return {
            "fatigue_score": snap.get("fatigue_score", 0.0),
            "energy_level": snap.get("energy_level", "unknown"),
            "system_load": snap.get("system_load", {}),
            "camera_available": camera_available,
        }
    except Exception as e:
        logger.warning(f"[VECTOR][api][sensing] status failed: {e}")
        return {"fatigue_score": 0.0, "energy_level": "unknown", "system_load": {}, "camera_available": False}

@router.get("/health")
async def sensing_health():
    """Full health snapshot: fatigue, sleep, energy, camera, EAR metrics."""
    try:
        from core.sensing.health_monitor import HealthMonitor
        monitor = HealthMonitor()
        return monitor.get_health_snapshot()
    except Exception as e:
        logger.warning(f"[VECTOR][api][sensing] health failed: {e}")
        return {"error": str(e)}


@router.get("/screen")
async def sensing_screen():
    """Capture current screen text via OCR."""
    try:
        from core.sensing.screen_observer import ScreenObserver
        observer = ScreenObserver()
        return {"text": observer.get_screen_text(), "timestamp": __import__("datetime").datetime.utcnow().isoformat()}
    except Exception as e:
        logger.warning(f"[VECTOR][api][sensing] screen failed: {e}")
        return {"text": "", "error": str(e)}


@router.get("/system")
async def sensing_system():
    """CPU, RAM, GPU, disk metrics from psutil + nvidia-smi."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        cpu = await asyncio.to_thread(psutil.cpu_percent, 0.1)   # interval blocks; keep the event loop free
        disk = psutil.disk_usage("/")
        result = {
            "cpu_pct": cpu,
            "ram_used_gb": round(mem.used / 1e9, 2),
            "ram_total_gb": round(mem.total / 1e9, 2),
            "ram_pct": mem.percent,
            "disk_used_gb": round(disk.used / 1e9, 2),
            "disk_total_gb": round(disk.total / 1e9, 2),
        }
        try:
            import subprocess
            out = await asyncio.to_thread(
                subprocess.run,
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
            )
            if out.returncode == 0:
                parts = out.stdout.strip().split(",")
                result["gpu_util_pct"] = float(parts[0].strip())
                result["gpu_mem_used_mb"] = float(parts[1].strip())
                result["gpu_mem_total_mb"] = float(parts[2].strip())
        except Exception:
            logger.warning("[VECTOR] suppressed exception (fallback degraded)", exc_info=True)
        return result
    except Exception as e:
        logger.warning(f"[VECTOR][api][sensing] system failed: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    print("OK: sensing.py")
