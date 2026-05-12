import sys
import uuid
import asyncio
import subprocess
import json
from pathlib import Path
from typing import Optional
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class HermesAdapter(AgentBase):
    """
    RULE 10 — Hermes is NOT rebuilt. This adapter manages the Hermes gateway
    process and routes all VECTOR communications through it.

    Start order:
      1. _ensure_running() — ping /health; start process from repo_path if down
      2. send_notification() / receive_messages() — all go via Hermes HTTP
    """

    PRIORITY_LEVELS = {
        "low": 0,
        "normal": 1,
        "high": 2,
        "urgent": 3,
        "critical": 4,
    }

    KNOWN_PLATFORMS = {
        "telegram", "discord", "slack", "whatsapp", "signal",
        "matrix", "mattermost", "homeassistant", "dingtalk", "feishu",
        "wecom", "sms", "email", "webhook",
    }

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "HermesAdapter", "communications")
        if ghost:
            self.inherit_ghost(ghost)

        hermes_cfg = CONFIG.get("hermes", {})
        self._hermes_url: str = hermes_cfg.get("local_url", "http://127.0.0.1:8080")
        self._repo_path: str = hermes_cfg.get(
            "repo_path",
            "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/NousResearch_hermes-agent/repo",
        )
        self._connected: bool = False
        self._message_history: list[dict] = []
        self._pending_messages: list[dict] = []
        self._hermes_proc: Optional[subprocess.Popen] = None
        # Internal counters updated by receive_messages()
        self._urgent_count: int = 0
        self._unread_count: int = 0
        logger.info(
            f"[VECTOR][hermes_adapter] initialized — target={self._hermes_url} "
            f"repo={self._repo_path}"
        )

    # ── Process management ────────────────────────────────────────────────────

    async def _ensure_running(self) -> bool:
        """Ping Hermes health endpoint; attempt process start from repo if down."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{self._hermes_url}/health")
                if r.status_code == 200:
                    self._connected = True
                    return True
        except Exception:
            pass

        # Not reachable — attempt to start from GitHub repo
        repo = Path(self._repo_path)
        if not repo.exists():
            logger.warning(
                f"[VECTOR][hermes_adapter] Hermes repo not found at {repo}. "
                "Install via: curl -fsSL https://raw.githubusercontent.com/"
                "NousResearch/hermes-agent/main/scripts/install.sh | bash"
            )
            return False

        if self._hermes_proc and self._hermes_proc.poll() is None:
            logger.info("[VECTOR][hermes_adapter] Hermes process already running")
            return False

        try:
            logger.info(f"[VECTOR][hermes_adapter] starting Hermes gateway from {repo}")
            self._hermes_proc = subprocess.Popen(
                [sys.executable, "-m", "gateway.run"],
                cwd=str(repo),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Give it a moment to bind
            await asyncio.sleep(3.0)
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._hermes_url}/health")
                if r.status_code == 200:
                    self._connected = True
                    self.award_points(20, "hermes_process_started")
                    logger.info("[VECTOR][hermes_adapter] Hermes gateway started successfully")
                    return True
        except Exception as e:
            logger.error(f"[VECTOR][hermes_adapter] process start failed: {e}")

        self._connected = False
        return False

    async def connect(self) -> bool:
        """Public connect — ensures Hermes is running."""
        return await self._ensure_running()

    # ── Notifications ─────────────────────────────────────────────────────────

    async def send_notification(self, text: str, priority: str = "normal") -> dict:
        """Send notification via Hermes. Queues locally if Hermes is down."""
        if not self._connected:
            if not await self._ensure_running():
                payload = {
                    "text": text,
                    "priority": self.PRIORITY_LEVELS.get(priority.lower(), 1),
                    "source": "vector",
                    "agent_id": self.id,
                }
                self._pending_messages.append(payload)
                return {"status": "queued", "message": "Hermes unavailable — queued locally"}

        payload = {
            "text": text,
            "priority": self.PRIORITY_LEVELS.get(priority.lower(), 1),
            "source": "vector",
            "agent_id": self.id,
            "timestamp": self._get_timestamp(),
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{self._hermes_url}/notify", json=payload)
                if response.status_code in (200, 201):
                    result = {
                        "status": "sent",
                        "priority": priority,
                        "hermes_response": response.json() if response.text else {},
                    }
                    self._message_history.append({**payload, **result})
                    self.award_points(5, "notification_sent")
                    logger.info(f"[VECTOR][hermes_adapter] sent: {text[:60]}")
                    return result
                else:
                    return {"status": "error", "message": f"Hermes {response.status_code}"}
        except Exception as e:
            logger.error(f"[VECTOR][hermes_adapter] send failed: {e}")
            self._pending_messages.append(payload)
            return {"status": "queued", "error": str(e)}

    async def receive_messages(self, limit: int = 10) -> list[dict]:
        """Poll Hermes for incoming messages, updating urgent/unread counters."""
        if not self._connected:
            if not await self._ensure_running():
                return []

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._hermes_url}/messages",
                    params={"limit": limit, "source": "vector"},
                )
                if response.status_code == 200:
                    messages = response.json()
                    for msg in messages:
                        self._message_history.append(msg)
                    # Update counters
                    self._unread_count = len(messages)
                    self._urgent_count = sum(
                        1 for m in messages
                        if m.get("priority", 0) >= self.PRIORITY_LEVELS["urgent"]
                    )
                    logger.info(f"[VECTOR][hermes_adapter] received {len(messages)} messages")
                    return messages
        except Exception as e:
            logger.error(f"[VECTOR][hermes_adapter] receive error: {e}")

        return []

    async def send_to_channel(self, channel: str, text: str, priority: str = "normal") -> dict:
        """Send message to a specific Hermes channel (Telegram/Discord/etc.)."""
        if channel.lower() not in self.KNOWN_PLATFORMS:
            logger.warning(
                f"[VECTOR][hermes_adapter] unknown platform '{channel}' — "
                f"known: {sorted(self.KNOWN_PLATFORMS)}"
            )

        if not self._connected:
            if not await self._ensure_running():
                return {"status": "error", "message": "Hermes unavailable"}

        payload = {
            "channel": channel,
            "text": text,
            "priority": self.PRIORITY_LEVELS.get(priority.lower(), 1),
            "source": "vector",
            "timestamp": self._get_timestamp(),
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._hermes_url}/channels/{channel}/send", json=payload
                )
                if response.status_code in (200, 201):
                    self.award_points(5, "channel_message_sent")
                    return {"status": "sent", "channel": channel}
                return {"status": "error", "code": response.status_code}
        except Exception as e:
            logger.error(f"[VECTOR][hermes_adapter] channel send failed: {e}")
            return {"status": "error", "message": str(e)}

    async def sync_pending_messages(self) -> dict:
        """Flush locally queued messages to Hermes."""
        if not self._pending_messages:
            return {"synced": 0, "remaining": 0}

        if not await self._ensure_running():
            return {"synced": 0, "remaining": len(self._pending_messages)}

        synced, remaining = 0, []
        for msg in self._pending_messages:
            priority_name = next(
                (k for k, v in self.PRIORITY_LEVELS.items() if v == msg.get("priority", 1)),
                "normal",
            )
            result = await self.send_notification(msg["text"], priority_name)
            if result.get("status") == "sent":
                synced += 1
            else:
                remaining.append(msg)

        self._pending_messages = remaining
        return {"synced": synced, "remaining": len(remaining)}

    async def set_away_status(self, status: str, message: str = "") -> bool:
        if not self._connected:
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{self._hermes_url}/status",
                    json={"status": status, "message": message, "agent_id": self.id},
                )
                return r.status_code in (200, 201)
        except Exception as e:
            logger.error(f"[VECTOR][hermes_adapter] status update failed: {e}")
            return False

    # ── Status helpers (used by context_engine) ───────────────────────────────

    def get_comms_status(self) -> dict:
        """
        Return Architecture.md-spec comms field: {urgent, unread, pending}.
        Called by ContextEngine.get_world_state() every tick.
        """
        return {
            "urgent": self._urgent_count,
            "unread": self._unread_count,
            "pending": len(self._pending_messages),
        }

    def get_pending_count(self) -> int:
        """Backward-compat: total pending + unread messages."""
        return self._unread_count + len(self._pending_messages)

    def get_message_history(self, limit: int = 100) -> list[dict]:
        return self._message_history[-limit:]

    def is_connected(self) -> bool:
        return self._connected

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("[VECTOR][hermes_adapter] disconnected")

    def _get_timestamp(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        adapter = HermesAdapter()
        assert adapter.name == "HermesAdapter"
        assert adapter.district == "communications"

        # connect() gracefully handles Hermes being offline
        connected = await adapter.connect()
        logger.info(f"[smoke] connected={connected}")

        # get_comms_status always returns valid structure
        status = adapter.get_comms_status()
        assert isinstance(status, dict)
        assert "urgent" in status and "unread" in status and "pending" in status

        # send_notification gracefully queues if offline
        result = await adapter.send_notification("Test from VECTOR", "normal")
        assert result.get("status") in ("sent", "queued", "error")

        print(f"✅ hermes_adapter OK — connected={connected}, status={status}")

    asyncio.run(_smoke())
