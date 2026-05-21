"""
VECTOR Phone Node — Ambient Server
Runs on old Android phone via Termux.

Responsibilities:
  - Heartbeat to brain server every 60s (battery, uptime, ambient signal)
  - Classify ambient text/events via local llama.cpp or brain server delegation
  - Receive alert pushes from VECTOR (brain server → phone → Termux notification)
  - Monitor battery and report low-power state

Usage (Termux):
  python ambient_server.py

Config: ~/.vector/phone_config.env
"""

import os
import sys
import json
import time
import threading
import datetime
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

try:
    from loguru import logger
except ImportError:
    import logging as _logging
    logger = _logging.getLogger("vector_phone")
    if not logger.handlers:
        _logging.basicConfig(level=_logging.INFO, format="%(message)s")
        logger.info = logger.info  # noqa: already set

# ── Config ─────────────────────────────────────────────────────────────────────

_CFG_PATH = Path.home() / ".vector" / "phone_config.env"
_cfg: dict[str, str] = {}

if _CFG_PATH.exists():
    for line in _CFG_PATH.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            _cfg[k.strip()] = v.strip()

BRAIN_URL     = _cfg.get("VECTOR_BRAIN_URL", "https://vector-brain.fly.dev")
API_KEY       = _cfg.get("VECTOR_API_KEY", "")
NODE_ID       = _cfg.get("VECTOR_NODE_ID", "phone-ambient")
HB_INTERVAL   = int(_cfg.get("HEARTBEAT_INTERVAL_SEC", "60"))
LOCAL_PORT    = int(_cfg.get("LOCAL_PORT", "7700"))

_start_time   = time.time()
_last_hb_ok   = False
_hb_count     = 0


# ── Termux helpers ─────────────────────────────────────────────────────────────

def _termux_battery() -> dict:
    """Read battery info via termux-api. Returns {} if unavailable."""
    try:
        out = subprocess.check_output(["termux-battery-status"], timeout=3)
        return json.loads(out)
    except Exception:
        return {}


def _termux_notify(title: str, content: str) -> None:
    """Push a Termux notification. Silent fail if termux-api missing."""
    try:
        subprocess.run(
            ["termux-notification", "--title", title, "--content", content],
            timeout=3, check=False,
        )
    except Exception:
        logger.debug("[VECTOR] suppressed exception", exc_info=True)


def _uptime() -> float:
    return round(time.time() - _start_time, 1)


# ── Local inference (optional) ─────────────────────────────────────────────────

_llm = None


def _load_local_llm() -> None:
    global _llm
    model_path = Path.home() / ".vector" / "models" / "ambient.gguf"
    if not model_path.exists():
        return
    try:
        from llama_cpp import Llama
        _llm = Llama(model_path=str(model_path), n_ctx=512, n_threads=4, verbose=False)
        _log(f"local llm loaded: {model_path.name}")
    except Exception as e:
        _log(f"local llm failed: {e}")


def _classify_local(text: str) -> str:
    if _llm is None:
        return ""
    try:
        prompt = f"Classify this event in one word (task/alert/info/idle):\n{text}\nAnswer:"
        out = _llm(prompt, max_tokens=8, stop=["\n"])
        return out["choices"][0]["text"].strip().lower()
    except Exception:
        return ""


def _classify_remote(text: str) -> str:
    """Delegate classification to brain server if local LLM not available."""
    try:
        import urllib.request
        payload = json.dumps({"text": text}).encode()
        req = urllib.request.Request(
            f"{BRAIN_URL}/classify",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read()).get("label", "info")
    except Exception:
        return "info"


def classify(text: str) -> str:
    result = _classify_local(text)
    return result if result else _classify_remote(text)


# ── Heartbeat loop ─────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    logger.info(f"[VECTOR][phone] {datetime.datetime.now().strftime('%H:%M:%S')} {msg}")


def _heartbeat_loop() -> None:
    global _last_hb_ok, _hb_count
    while True:
        try:
            battery = _termux_battery()
            payload = json.dumps({
                "node_id": NODE_ID,
                "uptime_sec": _uptime(),
                "battery_pct": battery.get("percentage", -1),
                "battery_status": battery.get("status", "unknown"),
                "hb_count": _hb_count,
                "local_llm": _llm is not None,
                "timestamp": datetime.datetime.now().isoformat(),
            }).encode()

            req = __import__("urllib.request", fromlist=["Request", "urlopen"])
            request = req.Request(
                f"{BRAIN_URL}/heartbeat",
                data=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
                method="POST",
            )
            with req.urlopen(request, timeout=8) as r:
                _last_hb_ok = r.status == 200
                _hb_count += 1
                _log(f"heartbeat #{_hb_count} OK battery={battery.get('percentage', '?')}%")
        except Exception as e:
            _last_hb_ok = False
            _log(f"heartbeat failed: {e}")

        time.sleep(HB_INTERVAL)


# ── HTTP server (runs on phone, accepts commands from VECTOR) ──────────────────

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default access log

    def _respond(self, body: dict, status: int = 200) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == "/status":
            battery = _termux_battery()
            self._respond({
                "status": "online",
                "node_id": NODE_ID,
                "uptime_sec": _uptime(),
                "last_hb_ok": _last_hb_ok,
                "hb_count": _hb_count,
                "battery_pct": battery.get("percentage", -1),
                "local_llm": _llm is not None,
                "brain_url": BRAIN_URL,
            })
        else:
            self._respond({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")

        if self.path == "/alert":
            title = body.get("title", "VECTOR")
            content = body.get("content", "")
            _termux_notify(title, content)
            _log(f"alert: {title} — {content[:50]}")
            self._respond({"ok": True})

        elif self.path == "/classify":
            text = body.get("text", "")
            label = classify(text)
            self._respond({"label": label, "text": text[:50]})

        else:
            self._respond({"error": "not found"}, 404)


def _start_server() -> None:
    server = HTTPServer(("0.0.0.0", LOCAL_PORT), _Handler)
    _log(f"HTTP server listening on :{LOCAL_PORT}")
    server.serve_forever()


# ── Entry ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _log(f"VECTOR Phone Node starting — node_id={NODE_ID} brain={BRAIN_URL}")

    # Try loading local LLM (non-blocking — skips if model not found)
    threading.Thread(target=_load_local_llm, daemon=True).start()

    # Start heartbeat loop in background
    hb = threading.Thread(target=_heartbeat_loop, daemon=True)
    hb.start()
    _log(f"heartbeat loop started — interval={HB_INTERVAL}s")

    # Serve HTTP (blocking)
    _start_server()
