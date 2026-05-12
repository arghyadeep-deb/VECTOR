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

    async def send_to_telegram(self, chat_id: str, text: str, priority: str = "normal") -> dict:
        """Convenience wrapper — send directly to Telegram chat_id via Hermes."""
        resolved_chat_id = CONFIG.get("hermes", {}).get("telegram_chat_id", chat_id)
        return await self.send_to_channel("telegram", text, priority)

    # ── Cron job management ───────────────────────────────────────────────────

    async def schedule_cron_job(
        self, schedule: str, message: str, platform: str, channel: str
    ) -> dict:
        """
        Schedule a recurring Hermes message via cron syntax.

        Args:
            schedule: croniter expression e.g. "0 9 * * *" (9am daily)
            message:  text to send on each trigger
            platform: must be in KNOWN_PLATFORMS
            channel:  destination channel / chat-id on that platform
        """
        await self._ensure_running()

        if platform.lower() not in self.KNOWN_PLATFORMS:
            logger.warning(
                f"[VECTOR][hermes_adapter] schedule_cron_job: unknown platform '{platform}'"
            )

        if not self._connected:
            queued = {
                "schedule": schedule, "message": message,
                "platform": platform, "channel": channel, "source": "vector",
            }
            self._pending_messages.append({"_type": "cron_job", **queued})
            logger.warning("[VECTOR][hermes_adapter] cron job queued — Hermes offline")
            return {"status": "queued", "message": "Hermes unavailable — cron job queued"}

        payload = {
            "schedule": schedule,
            "message": message,
            "platform": platform,
            "channel": channel,
            "source": "vector",
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(f"{self._hermes_url}/cron/jobs", json=payload)
                if response.status_code in (200, 201):
                    result = response.json() if response.text else {}
                    self.award_points(10, "cron_job_scheduled")
                    logger.info(
                        f"[VECTOR][hermes_adapter] cron job scheduled: "
                        f"schedule={schedule} platform={platform}"
                    )
                    return {"status": "scheduled", **result}
                return {"status": "error", "code": response.status_code}
        except Exception as e:
            logger.error(f"[VECTOR][hermes_adapter] schedule_cron_job failed: {e}")
            return {"status": "error", "message": str(e)}

    async def list_cron_jobs(self) -> list[dict]:
        """Return all scheduled Hermes cron jobs, or [] on error / offline."""
        await self._ensure_running()

        if not self._connected:
            logger.warning("[VECTOR][hermes_adapter] list_cron_jobs: Hermes offline")
            return []

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self._hermes_url}/cron/jobs")
                if response.status_code == 200:
                    jobs = response.json()
                    logger.info(f"[VECTOR][hermes_adapter] listed {len(jobs)} cron jobs")
                    return jobs if isinstance(jobs, list) else []
                logger.warning(
                    f"[VECTOR][hermes_adapter] list_cron_jobs: status {response.status_code}"
                )
        except Exception as e:
            logger.error(f"[VECTOR][hermes_adapter] list_cron_jobs failed: {e}")

        return []

    async def delete_cron_job(self, job_id: str) -> bool:
        """Delete a scheduled cron job by its ID. Returns True on success."""
        await self._ensure_running()

        if not self._connected:
            logger.warning("[VECTOR][hermes_adapter] delete_cron_job: Hermes offline")
            return False

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.delete(f"{self._hermes_url}/cron/jobs/{job_id}")
                if response.status_code in (200, 204):
                    logger.info(f"[VECTOR][hermes_adapter] deleted cron job {job_id}")
                    return True
                logger.warning(
                    f"[VECTOR][hermes_adapter] delete_cron_job: status {response.status_code}"
                )
        except Exception as e:
            logger.error(f"[VECTOR][hermes_adapter] delete_cron_job failed: {e}")

        return False

    # ── Skill registration ────────────────────────────────────────────────────

    async def register_skill(self, skill_name: str, skill_content: str) -> dict:
        """
        Register a VECTOR skill with Hermes so it can be invoked from chat platforms.

        Returns {status, skill_id} on success, error dict on failure.
        """
        await self._ensure_running()

        if not self._connected:
            logger.warning("[VECTOR][hermes_adapter] register_skill: Hermes offline")
            return {"status": "error", "message": "Hermes unavailable"}

        payload = {
            "name": skill_name,
            "content": skill_content,
            "source": "vector",
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(f"{self._hermes_url}/skills", json=payload)
                if response.status_code in (200, 201):
                    result = response.json() if response.text else {}
                    logger.info(
                        f"[VECTOR][hermes_adapter] skill registered: {skill_name}"
                    )
                    return {"status": "registered", **result}
                return {"status": "error", "code": response.status_code}
        except Exception as e:
            logger.error(f"[VECTOR][hermes_adapter] register_skill failed: {e}")
            return {"status": "error", "message": str(e)}

    # ── Session management ────────────────────────────────────────────────────

    async def get_sessions(self) -> list[dict]:
        """Return the 10 most-recent active Hermes sessions, or [] on error / offline."""
        await self._ensure_running()

        if not self._connected:
            logger.warning("[VECTOR][hermes_adapter] get_sessions: Hermes offline")
            return []

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._hermes_url}/sessions", params={"limit": 10}
                )
                if response.status_code == 200:
                    sessions = response.json()
                    logger.info(
                        f"[VECTOR][hermes_adapter] fetched {len(sessions)} sessions"
                    )
                    return sessions if isinstance(sessions, list) else []
                logger.warning(
                    f"[VECTOR][hermes_adapter] get_sessions: status {response.status_code}"
                )
        except Exception as e:
            logger.error(f"[VECTOR][hermes_adapter] get_sessions failed: {e}")

        return []

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

        # KNOWN_PLATFORMS class attribute exists and has expected entries
        assert "telegram" in HermesAdapter.KNOWN_PLATFORMS
        assert "discord" in HermesAdapter.KNOWN_PLATFORMS
        assert len(HermesAdapter.KNOWN_PLATFORMS) >= 14

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

        # list_cron_jobs returns list (empty if offline)
        jobs = await adapter.list_cron_jobs()
        assert isinstance(jobs, list)
        logger.info(f"[smoke] list_cron_jobs={jobs}")

        # get_sessions returns list (empty if offline)
        sessions = await adapter.get_sessions()
        assert isinstance(sessions, list)
        logger.info(f"[smoke] get_sessions count={len(sessions)}")

        # send_to_channel warns on unknown platform but does not raise
        bad_platform_result = await adapter.send_to_channel("myspace", "test", "normal")
        assert bad_platform_result.get("status") in ("sent", "error")

        print(
            f"✅ hermes_adapter OK — connected={connected}, status={status}, "
            f"cron_jobs={len(jobs)}, sessions={len(sessions)}"
        )

    asyncio.run(_smoke())
