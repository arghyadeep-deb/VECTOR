"""
VECTOR Stealth Browser Server Manager
Manages the Node.js anti-detection browser server as a Python subprocess.

Also implements crash detection and rate-limited alerting (ported from
workers/crash-reporter/ in the original repo — repurposed to send alerts
to VECTOR's Pushover instead of external GitHub Issues).

Usage:
    server = StealthBrowserServer()
    asyncio.run(server.start())
    # ... use StealthBrowserClient ...
    asyncio.run(server.stop())

    # Or as context manager:
    async with StealthBrowserServer() as srv:
        assert srv.is_running
"""
from __future__ import annotations

__all__ = [
    "get_server",
    "StealthBrowserServer",
]


import asyncio
import collections
import hashlib
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from core.config import CONFIG
from loguru import logger

_SERVER_DIR = Path(__file__).parent / "server"
_DEFAULT_PORT = 9377
_HEALTH_URL = f"http://127.0.0.1:{_DEFAULT_PORT}/health"

# Module-level singleton — multiple callers share one server process
_instance: Optional["StealthBrowserServer"] = None
_instance_lock = threading.Lock()


# â”€â”€ Crash reporter (from workers/crash-reporter/ logic) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _CrashReporter:
    """
    Monitors server stderr for crashes and event loop stalls.
    Deduplicates by stack signature (MD5 of first 3 frames).
    Rate-limits to 10 alerts per hour — same as original crash-reporter worker.
    Sends alerts to VECTOR's Pushover instead of GitHub Issues.
    """

    MAX_PER_HOUR = 10
    _seen_signatures: dict[str, float] = {}   # signature → last_seen timestamp
    _hour_counts: collections.deque = collections.deque()  # timestamps in last hour

    @classmethod
    def _stack_signature(cls, text: str) -> str:
        """MD5 hash of the first 3 stack frame lines (same dedup as crash-reporter worker)."""
        frames = re.findall(r"at .+", text)[:3]
        return hashlib.md5("\n".join(frames).encode()).hexdigest()[:12]

    @classmethod
    def _should_alert(cls, sig: str) -> bool:
        now = time.time()
        hour_ago = now - 3600
        cls._hour_counts = collections.deque(t for t in cls._hour_counts if t > hour_ago)
        if len(cls._hour_counts) >= cls.MAX_PER_HOUR:
            return False
        last = cls._seen_signatures.get(sig, 0)
        if now - last < 300:  # 5 min cooldown per signature
            return False
        cls._seen_signatures[sig] = now
        cls._hour_counts.append(now)
        return True

    @classmethod
    def report(cls, error_text: str, source: str = "stealth_browser") -> None:
        sig = cls._stack_signature(error_text)
        if not cls._should_alert(sig):
            return
        summary = error_text[:300].strip()
        logger.error("[VECTOR][stealth] crash detected (sig={}): {}", sig, summary[:80])
        # Store in episodic memory
        try:
            from core.memory.episodic import EpisodicMemory
            EpisodicMemory().store(
                event_type="stealth_browser_crash",
                content=f"Stealth browser error (sig={sig}): {summary}",
                tags=["stealth_browser", "crash", "error"],
                source=source,
            )
        except Exception as e:
            logger.warning("[VECTOR][stealth] failed to store crash in episodic memory: {}", e)
        # Pushover notification
        try:
            import httpx
            token  = CONFIG.get("api_keys", {}).get("pushover_token", "")
            user   = CONFIG.get("api_keys", {}).get("pushover_user", "")
            if token and user:
                httpx.post(
                    "https://api.pushover.net/1/messages.json",
                    data={
                        "token": token, "user": user,
                        "title": "VECTOR Stealth Browser Crash",
                        "message": f"sig={sig}\n{summary[:200]}",
                        "priority": 0,
                    },
                    timeout=5.0,
                )
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)


# â”€â”€ Server Manager â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class StealthBrowserServer:
    """
    Manages the anti-detection browser Node.js server as a Python subprocess.
    Single instance shared across the VECTOR process.
    """

    def __init__(self) -> None:
        cfg = CONFIG.get("stealth_browser", {})
        self._port     = cfg.get("port", _DEFAULT_PORT)
        self._proc: Optional[subprocess.Popen] = None
        self._base_url = f"http://127.0.0.1:{self._port}"
        self._stderr_thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # â”€â”€ Health check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def is_healthy(self) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{self._base_url}/health")
                return r.status_code == 200
        except Exception:
            return False

    def _port_in_use(self) -> bool:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.connect(("127.0.0.1", self._port))
                return True
            except ConnectionRefusedError:
                return False

    # â”€â”€ Start / Stop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def start(self) -> bool:
        """Start the Node.js server subprocess. Returns True if started/already running."""
        if self._port_in_use():
            logger.debug("[VECTOR][stealth] server already listening on port {}", self._port)
            return True

        if not (_SERVER_DIR / "server.js").exists():
            logger.error("[VECTOR][stealth] server.js not found at {}", _SERVER_DIR)
            return False

        # Check node is available
        try:
            (await asyncio.to_thread(subprocess.run, ["node", "--version"], capture_output=True, timeout=5))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.error("[VECTOR][stealth] Node.js not found — install Node.js 18+")
            return False

        env = {
            **os.environ,
            "CAMOFOX_PORT":                  str(self._port),
            "CAMOFOX_CRASH_REPORT_ENABLED":  "false",  # VECTOR handles crash reporting
            "NODE_ENV":                       "production",
        }
        api_key = CONFIG.get("stealth_browser", {}).get("api_key", "")
        if api_key:
            env["CAMOFOX_ACCESS_KEY"] = api_key

        logger.info("[VECTOR][stealth] starting server on port {}", self._port)
        self._proc = subprocess.Popen(
            ["node", "server.js"],
            cwd=str(_SERVER_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Monitor stderr for crashes in background thread.
        # 2026-09-23: deliberate exception to "never use threading, use
        # asyncio" (.claude/rules/libraries.md) -- `subprocess.Popen`'s
        # stderr pipe (opened with the sync `subprocess` module, not
        # `asyncio.create_subprocess_exec`) is a blocking file
        # descriptor; a dedicated thread is the standard way to drain it
        # continuously without blocking this coroutine's own event loop.
        self._stderr_thread = threading.Thread(
            target=self._watch_stderr, daemon=True
        )
        self._stderr_thread.start()

        # Wait for healthy
        for _ in range(30):  # 15s timeout
            await asyncio.sleep(0.5)
            if await self.is_healthy():
                logger.info("[VECTOR][stealth] server ready at {}", self._base_url)
                return True
            if self._proc.poll() is not None:
                stderr = self._proc.stderr.read() if self._proc.stderr else ""  # type: ignore
                logger.error("[VECTOR][stealth] server exited early: {}", stderr[:200])
                return False

        logger.error("[VECTOR][stealth] server did not become healthy in 15s")
        return False

    async def stop(self) -> None:
        """Stop the server."""
        if self._proc and self._proc.poll() is None:
            try:
                import httpx
                admin_key = CONFIG.get("stealth_browser", {}).get("admin_key", "")
                async with httpx.AsyncClient(timeout=5.0) as c:
                    headers = {"Authorization": f"Bearer {admin_key}"} if admin_key else {}
                    await c.post(f"{self._base_url}/stop", headers=headers)
            except Exception as e:
                logger.warning("[VECTOR][stealth] /stop request failed: {}", e)
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None
            logger.info("[VECTOR][stealth] server stopped")

    async def ensure_running(self) -> bool:
        """Start the server if not already running."""
        if await self.is_healthy():
            return True
        return await self.start()

    def _watch_stderr(self) -> None:
        """Background thread: read stderr and report crashes."""
        if not self._proc or not self._proc.stderr:
            return
        buffer = ""
        for line in self._proc.stderr:
            buffer += line
            if len(buffer) > 2000:
                buffer = buffer[-1000:]
            # Detect uncaught exception or event loop stall patterns
            if any(p in line for p in ("UnhandledPromiseRejection", "FATAL ERROR", "Unhandled Rejection", "ERR_", "at Object.")):
                _CrashReporter.report(buffer, source="stealth_browser")
                buffer = ""

    async def __aenter__(self):
        await self.ensure_running()
        return self

    async def __aexit__(self, *_):
        # Don't stop on context exit -- server runs as long-lived service,
        # shared across callers via get_server(). This was a bare
        # `raise NotImplementedError` referencing a subclass that doesn't
        # exist anywhere in the repo (confirmed via grep) -- the class's
        # own docstring documents direct `async with StealthBrowserServer()`
        # usage, which would have crashed on every exit.
        return False


def get_server() -> StealthBrowserServer:
    """Get or create the module-level singleton server instance."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = StealthBrowserServer()
    return _instance


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        srv = StealthBrowserServer()
        healthy = await srv.is_healthy()
        print(f"OK server_manager.py — port={srv._port}")
        print(f"  server_dir={_SERVER_DIR}")
        print(f"  server.js exists: {(_SERVER_DIR / 'server.js').exists()}")
        print(f"  currently healthy: {healthy}")
        if not healthy:
            print(f"  start with: await StealthBrowserServer().start()")
            print(f"  requires: node 18+ and camoufox binary (npx camoufox fetch)")

    asyncio.run(_smoke())
