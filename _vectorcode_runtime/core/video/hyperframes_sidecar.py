"""
Hyperframes sidecar process manager.
Manages the @hyperframes/producer HTTP server as a subprocess.
"""
from pathlib import Path
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

import asyncio
import subprocess
import httpx
from loguru import logger
from core.config import CONFIG

HYPERFRAMES_PORT = 7421
HYPERFRAMES_HEALTH_URL = f"http://localhost:{HYPERFRAMES_PORT}/health"

_proc: subprocess.Popen | None = None


def get_hyperframes_dir() -> Path | None:
    """Find the hyperframes repo directory."""
    candidates = [
        Path(__file__).parent.parent.parent.parent / "GitHub" / "hyperframes-main",
    ]
    return next((p for p in candidates if p.exists()), None)


async def is_running() -> bool:
    """Check if hyperframes sidecar is responding."""
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(HYPERFRAMES_HEALTH_URL)
            return r.status_code < 500
    except Exception:
        return False


def start_sidecar() -> bool:
    """Start the hyperframes producer sidecar. Returns True if started."""
    global _proc
    hf_dir = get_hyperframes_dir()
    if not hf_dir:
        logger.warning("[VECTOR][hyperframes_sidecar] hyperframes-main not found")
        return False

    server_js = hf_dir / "packages" / "producer" / "dist" / "server.js"
    if not server_js.exists():
        logger.warning(
            "[VECTOR][hyperframes_sidecar] server.js not built. Run: cd {} && npm run build",
            hf_dir,
        )
        return False

    import os
    try:
        _proc = subprocess.Popen(
            ["node", str(server_js), "--port", str(HYPERFRAMES_PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(hf_dir),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        logger.info("[VECTOR][hyperframes_sidecar] Started (pid={})", _proc.pid)
        return True
    except Exception as e:
        logger.warning("[VECTOR][hyperframes_sidecar] Start failed: {}", e)
        return False


def stop_sidecar() -> None:
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        logger.info("[VECTOR][hyperframes_sidecar] Stopped")
    _proc = None


async def ensure_running() -> bool:
    """Start sidecar if not already running. Returns True if available."""
    if await is_running():
        return True
    started = start_sidecar()
    if started:
        # Wait up to 5s for health check
        for _ in range(10):
            await asyncio.sleep(0.5)
            if await is_running():
                return True
    return False


if __name__ == "__main__":
    async def test():
        print("Hyperframes running:", await is_running())
        dir_ = get_hyperframes_dir()
        print("Hyperframes dir:", dir_)
        print("✅ hyperframes_sidecar OK")
    asyncio.run(test())
