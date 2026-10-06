"""
VECTOR ADB Bridge — runs on Legion Pro 5.

Connects to the phone ambient server (either via ADB port-forward or WiFi)
and provides VECTOR with phone context:
  - Forward phone notifications → VECTOR episodic memory
  - Screenshot phone screen via ADB
  - Send alert pushes from VECTOR → phone
  - Monitor phone battery state

USB ADB setup:
  adb devices          — verify phone is listed
  adb reverse tcp:7700 tcp:7700   — optional: phone server accessible on PC

WiFi setup (preferred for ambient always-on):
  adb tcpip 5555
  adb connect <phone-ip>:5555
"""
import sys
import asyncio
import subprocess
import datetime
from pathlib import Path

from core.config import CONFIG
from core.memory.episodic import EpisodicMemory
from loguru import logger

import httpx


# ── Config ─────────────────────────────────────────────────────────────────────

_ADB_PATH    = CONFIG["control"]["adb_path"]
_DEVICE_ID   = CONFIG["control"]["phone_device_id"]  # None = first device
_PHONE_PORT  = 7700  # matches ambient_server.py LOCAL_PORT


def _adb(*args) -> str:
    """Run an ADB command, return stdout or '' on failure."""
    cmd = [_ADB_PATH]
    if _DEVICE_ID:
        cmd += ["-s", _DEVICE_ID]
    cmd += list(args)
    try:
        return subprocess.check_output(cmd, timeout=10, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"[VECTOR][adb] command failed {args}: {e}")
        return ""


# ── Phone ambient server HTTP client ──────────────────────────────────────────

async def _phone_url(path: str, via_adb: bool = True) -> str:
    """
    Build the URL to reach the phone's ambient server.
    via_adb=True: assumes 'adb forward tcp:7700 tcp:7700' has been run.
    via_adb=False: direct WiFi (set PHONE_WIFI_IP env var).
    """
    if not via_adb:
        ip = CONFIG.get("phone_wifi_ip", "192.168.1.100")
        return f"http://{ip}:{_PHONE_PORT}{path}"
    return f"http://127.0.0.1:{_PHONE_PORT}{path}"


async def phone_status() -> dict:
    """Return phone ambient server status dict or {} if unreachable."""
    try:
        url = await _phone_url("/status")
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(url)
            return r.json() if r.status_code == 200 else {}
    except Exception as e:
        logger.warning(f"[VECTOR][adb] phone status failed: {e}")
        return {}


async def send_alert(title: str, content: str) -> bool:
    """Push a Termux notification to the phone."""
    try:
        url = await _phone_url("/alert")
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.post(url, json={"title": title, "content": content})
            return r.status_code == 200
    except Exception as e:
        logger.warning(f"[VECTOR][adb] alert push failed: {e}")
        return False


# ── ADB operations ─────────────────────────────────────────────────────────────

def setup_port_forward() -> bool:
    """Forward phone's ambient server port to localhost (call once on connect)."""
    cmd = [_ADB_PATH]
    if _DEVICE_ID:
        cmd += ["-s", _DEVICE_ID]
    cmd += ["forward", f"tcp:{_PHONE_PORT}", f"tcp:{_PHONE_PORT}"]
    try:
        completed = subprocess.run(
            cmd, timeout=10, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=False,
        )
        ok = completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    logger.info(f"[VECTOR][adb] port forward :{_PHONE_PORT} → {ok}")
    return ok


def take_screenshot(save_path: Path | None = None) -> Path | None:
    """Capture phone screen via ADB screenshot."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = save_path or Path(f"./data/phone_screenshots/phone_{ts}.png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        _adb("exec-out", "screencap", "-p")
        # Write via shell → pull pattern
        _adb("shell", "screencap", "-p", "/sdcard/vector_cap.png")
        _adb("pull", "/sdcard/vector_cap.png", str(dest))
        _adb("shell", "rm", "/sdcard/vector_cap.png")
        if dest.is_file() and dest.stat().st_size > 0:
            logger.info(f"[VECTOR][adb] screenshot saved: {dest}")
            return dest
        logger.warning(f"[VECTOR][adb] screenshot pull produced no file: {dest}")
        return None
    except Exception as e:
        logger.warning(f"[VECTOR][adb] screenshot failed: {e}")
        return None


def list_devices() -> list[str]:
    """Return list of connected ADB device IDs."""
    out = _adb("devices")
    lines = [l.split()[0] for l in out.splitlines() if "\tdevice" in l]
    return lines


# ── Polling loop ───────────────────────────────────────────────────────────────

async def poll_loop(interval_sec: int = 60) -> None:
    """
    Poll phone ambient server every interval_sec.
    Stores battery / heartbeat events in episodic memory.
    RULE 2 — never crashes.
    """
    memory = EpisodicMemory()
    setup_port_forward()
    logger.info(f"[VECTOR][adb] poll loop started — interval={interval_sec}s")

    while True:
        try:
            status = await phone_status()
            if status:
                battery = status.get("battery_pct", -1)
                hb = status.get("hb_count", 0)
                logger.info(f"[VECTOR][adb] phone alive — battery={battery}% hb={hb}")

                # Store ambient heartbeat in episodic memory
                memory.store(
                    event_type="phone_heartbeat",
                    content=f"Phone node alive: battery={battery}% uptime={status.get('uptime_sec', 0):.0f}s",
                    tags=["phone", "ambient", "heartbeat"],
                    source="adb_bridge",
                )

                # Low battery alert
                if 0 < battery < 20:
                    logger.warning(f"[VECTOR][adb] phone battery low: {battery}%")
                    memory.store(
                        event_type="phone_battery_low",
                        content=f"Phone battery low: {battery}%",
                        tags=["phone", "battery", "alert"],
                        source="adb_bridge",
                    )
            else:
                logger.warning("[VECTOR][adb] phone ambient server unreachable")

        except Exception as e:
            logger.error(f"[VECTOR][adb] poll error: {e}")

        await asyncio.sleep(interval_sec)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        devices = list_devices()
        print(f"ADB devices: {devices}")

        status = await phone_status()
        print(f"Phone status: {status}")

        if status:
            print(f"Phone online: battery={status.get('battery_pct')}%  hb={status.get('hb_count')}")
            print("OK adb_bridge.py")
        else:
            print("Phone ambient server not running (expected if phone not connected)")
            print("OK adb_bridge.py — offline mode")

    asyncio.run(_smoke())
