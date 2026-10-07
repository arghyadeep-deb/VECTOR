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

from loguru import logger
import os
import sys
import json
import hmac
import time
import threading
import datetime
import subprocess
import re
import socket
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


def _parse_env(text: str) -> dict[str, str]:
    """Parse a .env file robustly: skips blank/comment lines (even indented),
    strips whitespace, removes surrounding matching quotes, and drops inline
    ``# comment`` on unquoted values. Prefers python-dotenv when available."""
    try:
        from dotenv import dotenv_values  # type: ignore
        import io
        return {k: (v or "") for k, v in dotenv_values(stream=io.StringIO(text)).items()}
    except Exception:
        logger.exception("[VECTOR] silent swallow")
        pass
    cfg: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
            v = v[1:-1]                       # quoted value — keep verbatim
        elif " #" in v:
            v = v.split(" #", 1)[0].strip()   # strip inline comment
        if k:
            cfg[k] = v
    return cfg


def _load_cfg() -> dict[str, str]:
    if _CFG_PATH.exists():
        try:
            return _parse_env(_CFG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


_cfg: dict[str, str] = _load_cfg()

BRAIN_URL     = _cfg.get("VECTOR_BRAIN_URL", "https://vector-api.arghyadeepdeb020703.workers.dev")
API_KEY       = _cfg.get("VECTOR_API_KEY", "").strip()
NODE_ID       = _cfg.get("VECTOR_NODE_ID", "phone-ambient")
HB_INTERVAL   = int(_cfg.get("HEARTBEAT_INTERVAL_SEC", "60"))
COMMAND_POLL_INTERVAL_SEC = int(_cfg.get("COMMAND_POLL_INTERVAL_SEC", "15"))
LOCAL_PORT    = int(_cfg.get("LOCAL_PORT", "7700"))
LEGION_WIFI_MAC = _cfg.get("LEGION_WIFI_MAC", "").strip()
LEGION_ETHERNET_MAC = _cfg.get("LEGION_ETHERNET_MAC", "").strip()
LEGION_WAKE_BROADCAST = _cfg.get("LEGION_WAKE_BROADCAST", "255.255.255.255").strip()
LEGION_WAKE_PORT = int(_cfg.get("LEGION_WAKE_PORT", "9"))
# Optional: Legion's LAN IP + VECTOR API port, so wake_legion() can check
# reachability first and skip a redundant WoL packet if already awake.
# Unset by default (owner hasn't configured it yet) -- falls back to the
# original always-send-WoL behavior, never breaks if absent.
LEGION_HOST = _cfg.get("LEGION_HOST", "").strip()
LEGION_API_PORT = int(_cfg.get("LEGION_API_PORT", "8000"))

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


def _can_send_upstream() -> bool:
    """Upstream brain calls require a configured API key. Without it we must not
    send unauthenticated requests (they would be rejected and leak node data)."""
    return bool(API_KEY)


def _is_usable_key(key: str) -> bool:
    """Return whether a key is strong enough to protect network mutations."""
    candidate = (key or "").strip()
    if len(candidate) < 8:
        return False
    return candidate.lower() not in {
        "changeme",
        "change-me",
        "placeholder",
        "default",
        "test",
        "secret",
    }


def _auth_ok(header_value: str | None) -> bool:
    """Fail closed unless local mutating endpoints have usable bearer auth."""
    if not _is_usable_key(API_KEY):
        return False
    return hmac.compare_digest(header_value or "", f"Bearer {API_KEY}")


def _classify_remote(text: str) -> str:
    """Delegate classification to brain server if local LLM not available."""
    if not _can_send_upstream():
        _log("classify skipped: VECTOR_API_KEY not set — staying local")
        return "info"
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


# â”€â”€ Wake-on-LAN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _normalize_mac(mac: str) -> str:
    clean = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    if len(clean) != 12:
        raise ValueError("invalid MAC address")
    return clean.lower()


def _magic_packet(mac: str) -> bytes:
    mac_bytes = bytes.fromhex(_normalize_mac(mac))
    return b"\xff" * 6 + mac_bytes * 16


def _configured_legion_mac(prefer: str = "wifi") -> str:
    if prefer == "ethernet":
        return LEGION_ETHERNET_MAC or LEGION_WIFI_MAC
    return LEGION_WIFI_MAC or LEGION_ETHERNET_MAC


def _check_legion_reachable(host: str = "", port: int = 0, timeout: float = 2.0) -> bool:
    """Real TCP probe -- no live deployment needed to exercise this: a
    closed/refused local port is a real, observable network state."""
    host = host or LEGION_HOST
    port = port or LEGION_API_PORT
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wake_legion(prefer: str = "wifi") -> dict:
    """Send a Wake-on-LAN packet for the configured Legion adapter.

    If LEGION_HOST is configured, checks reachability first and skips a
    redundant WoL packet when Legion is already awake. Falls back to the
    original always-send-WoL behavior when LEGION_HOST is unset.
    """
    if LEGION_HOST and _check_legion_reachable():
        return {"ok": True, "already_awake": True, "host": LEGION_HOST}
    mac = _configured_legion_mac(prefer)
    if not mac:
        return {"ok": False, "error": "LEGION_WIFI_MAC or LEGION_ETHERNET_MAC not configured"}
    try:
        packet = _magic_packet(mac)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (LEGION_WAKE_BROADCAST, LEGION_WAKE_PORT))
        return {
            "ok": True,
            "already_awake": False,
            "mac": _normalize_mac(mac),
            "broadcast": LEGION_WAKE_BROADCAST,
            "port": LEGION_WAKE_PORT,
        }
    except Exception as e:
        return {
            "ok": False,
            "mac": re.sub(r"[^0-9a-fA-F]", "", mac or "").lower(),
            "broadcast": LEGION_WAKE_BROADCAST,
            "port": LEGION_WAKE_PORT,
            "error": str(e),
        }


# â”€â”€ Cloud command polling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _cloud_request(path: str, payload: dict, timeout: int = 10) -> dict:
    if not _can_send_upstream():
        return {"ok": False, "error": "VECTOR_API_KEY not set"}
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{BRAIN_URL.rstrip('/')}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _post_command_result(command_id: str, status: str, result: dict | None = None, error: str = "") -> dict:
    return _cloud_request(
        f"/commands/{command_id}/result",
        {"status": status, "result": result or {}, "error": error, "node_id": NODE_ID},
    )


def _execute_cloud_command(command: dict) -> tuple[str, dict, str]:
    cmd_type = str(command.get("type") or "")
    params = command.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    try:
        if cmd_type == "wake_legion":
            result = wake_legion(prefer=str(params.get("prefer", "wifi")))
            return ("done" if result.get("ok") else "deferred", result, result.get("error", ""))

        if cmd_type == "alert":
            title = str(params.get("title", "VECTOR"))
            content = str(params.get("content", ""))
            _termux_notify(title, content)
            return "done", {"notified": True, "title": title}, ""

        if cmd_type == "classify":
            text = str(params.get("text", ""))
            return "done", {"label": classify(text), "text": text[:80]}, ""

        if cmd_type in ("ping", "status"):
            return "done", {"status": "online", "node_id": NODE_ID, "uptime_sec": _uptime()}, ""

        if cmd_type in ("echo", "command"):
            text = str(params.get("text", ""))
            return "done", {"message": text or "Termux node received command", "node_id": NODE_ID}, ""

        return "failed", {"handled": False, "type": cmd_type}, f"unsupported command type: {cmd_type}"
    except Exception as e:
        return "failed", {}, str(e)


def _command_poll_once() -> dict:
    payload = {
        "node_id": NODE_ID,
        "uptime_sec": _uptime(),
        "local_llm": _llm is not None,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    poll = _cloud_request(f"/nodes/{NODE_ID}/poll", payload)
    if not poll.get("ok"):
        return poll

    handled = 0
    for command in poll.get("commands") or []:
        command_id = str(command.get("id", ""))
        if not command_id:
            continue
        status, result, error = _execute_cloud_command(command)
        _post_command_result(command_id, status, result, error)
        handled += 1
    return {"ok": True, "commands": len(poll.get("commands") or []), "handled": handled}


def _command_poll_loop() -> None:
    while True:
        if not _can_send_upstream():
            _log("command poll skipped: VECTOR_API_KEY not set")
            time.sleep(COMMAND_POLL_INTERVAL_SEC)
            continue
        result = _command_poll_once()
        if result.get("handled"):
            _log(f"command poll handled {result.get('handled')} command(s)")
        elif not result.get("ok"):
            _log(f"command poll failed: {result.get('error')}")
        time.sleep(COMMAND_POLL_INTERVAL_SEC)


# ── Heartbeat loop ─────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    logger.info(f"[VECTOR][phone] {datetime.datetime.now().strftime('%H:%M:%S')} {msg}")


def _heartbeat_loop() -> None:
    global _last_hb_ok, _hb_count
    while True:
        if not _can_send_upstream():
            _last_hb_ok = False
            _log("heartbeat skipped: VECTOR_API_KEY not set — configure ~/.vector/phone_config.env")
            time.sleep(HB_INTERVAL)
            continue
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
        if not _auth_ok(self.headers.get("Authorization")):
            self._respond({"error": "unauthorized"}, 401)
            return

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

        elif self.path == "/wake_legion":
            prefer = body.get("prefer", "wifi")
            result = wake_legion(prefer=prefer)
            self._respond(result, 200 if result.get("ok") else 503)

        else:
            self._respond({"error": "not found"}, 404)


def _start_server() -> None:
    if not _is_usable_key(API_KEY):
        _log(
            "SECURITY WARNING: VECTOR_API_KEY is missing or unusable; "
            "this server is network-reachable and all mutating endpoints are locked. "
            "Configure a non-placeholder key before using them."
        )
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

    poll = threading.Thread(target=_command_poll_loop, daemon=True)
    poll.start()
    _log(f"command poll loop started — interval={COMMAND_POLL_INTERVAL_SEC}s")

    # Serve HTTP (blocking)
    _start_server()
