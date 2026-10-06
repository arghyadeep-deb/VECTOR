"""
MessagingHub — VECTOR multi-platform messaging hub.
Standalone multi-platform messaging. no external HTTP dependency.
Supports: telegram, discord (webhook), email, webhook, pushover.
Offline queue persisted to ~/.vector/messages/pending.json.
Cron scheduling via APScheduler.
"""
import json
import asyncio
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

_MSG_DIR = Path.home() / ".vector" / "messages"
_PENDING_FILE = _MSG_DIR / "pending.json"
_HISTORY_FILE = _MSG_DIR / "history.json"

class MessagingHub:
    """
    Standalone multi-platform messaging hub.
    Replaces MessagingAdapter — works standalone.

    Platform support (graceful no-op if credentials absent):
      telegram  — Bot API via httpx
      discord   — Webhook URL
      email     — SMTP (Gmail or any SMTP)
      webhook   — Generic HTTP POST
      pushover  — Pushover API

    Offline queue: pending messages saved to disk, flushed on reconnect.
    Cron: APScheduler (optional dep) for recurring messages.
    Comms status: urgent/unread/pending counters (ContextEngine feed).
    """

    KNOWN_PLATFORMS = frozenset({
        "telegram", "discord", "slack", "email", "webhook",
        "pushover", "whatsapp", "signal", "matrix",
        "mattermost", "homeassistant", "dingtalk", "feishu", "sms",
    })

    PRIORITY_LEVELS = {"low": 0, "normal": 1, "high": 2, "urgent": 3, "critical": 4}

    def __init__(self):
        _MSG_DIR.mkdir(parents=True, exist_ok=True)
        self._pending: list[dict] = self._load_pending()
        self._history: list[dict] = []
        self._urgent_count = 0
        self._unread_count = 0
        self._skill_registry: dict[str, str] = {}
        self._cron_jobs: list[dict] = []
        self._scheduler = None
        self._start_scheduler()

    # ── Scheduler ─────────────────────────────────────────────────────────────

    def _start_scheduler(self) -> None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            self._scheduler = BackgroundScheduler(daemon=True)
            self._scheduler.start()
        except ImportError:
            logger.debug("[VECTOR][comms] APScheduler not installed — cron disabled")

    # ── Pending queue persistence ──────────────────────────────────────────────

    def _load_pending(self) -> list:
        if _PENDING_FILE.exists():
            try:
                return json.loads(_PENDING_FILE.read_text(encoding="utf-8"))
            except Exception as _sve:
                logger.debug("[VECTOR][comms.messenger] pending load failed: {}", _sve)
        return []

    def _save_pending(self) -> None:
        temp_path: Path | None = None
        try:
            payload = json.dumps(self._pending, ensure_ascii=False, indent=2)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=_MSG_DIR,
                prefix=f".{_PENDING_FILE.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(payload)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, _PENDING_FILE)
        except Exception as e:
            logger.error(f"[VECTOR][comms] pending save failed: {e}")
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _queue_message(self, channel: str, text: str, priority: str) -> None:
        self._pending.append({
            "channel": channel, "text": text, "priority": priority,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        })
        self._save_pending()

    # ── Core send ─────────────────────────────────────────────────────────────

    async def send_notification(self, text: str, priority: str = "normal") -> dict:
        """Send to all configured primary channels (Telegram first, then email)."""
        errors = {}
        for platform in ("telegram", "pushover", "discord", "email"):
            result = await self.send_to_channel(platform, text, priority)
            if result.get("status") == "sent":
                return {"status": "sent", "via": platform}
            elif result.get("status") != "not_configured":
                errors[platform] = result.get("status", "error")

        self._queue_message("all", text, priority)
        if errors:
            return {
                "status": "queued",
                "reason": "all configured platforms failed",
                "errors": errors,
            }
        return {"status": "queued", "reason": "no platforms configured"}

    async def send_to_channel(self, channel: str, text: str, priority: str = "normal") -> dict:
        """Route message to the appropriate platform adapter."""
        ch = channel.lower().strip()
        if ch not in self.KNOWN_PLATFORMS:
            logger.warning(f"[VECTOR][comms] unknown platform '{ch}' — queuing")
            self._queue_message(ch, text, priority)
            return {"status": "queued", "platform": ch}

        dispatch = {
            "telegram":     self._send_telegram,
            "discord":      self._send_discord,
            "email":        self._send_email,
            "webhook":      self._send_webhook,
            "pushover":     self._send_pushover,
        }

        if ch in dispatch:
            result = await dispatch[ch](text, priority)
            if result.get("status") == "sent":
                self._history.append({
                    "platform": ch, "text": text[:200], "priority": priority,
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                })
            return result

        # Unsupported but known platform — queue for manual send
        self._queue_message(ch, text, priority)
        return {"status": "queued", "platform": ch}

    async def send_to_telegram(self, chat_id: str, text: str, priority: str = "normal") -> dict:
        """Convenience wrapper for Telegram."""
        return await self.send_to_channel("telegram", text, priority)

    # ── Platform adapters ─────────────────────────────────────────────────────

    async def _send_telegram(self, text: str, priority: str) -> dict:
        cfg = CONFIG.get("telegram", {}) if isinstance(CONFIG, dict) else {}
        token = cfg.get("bot_token") or ""
        chat_id = cfg.get("chat_id") or ""
        if not token or not chat_id:
            return {"status": "not_configured", "platform": "telegram"}

        prefix = {"urgent": "🚨 URGENT: ", "critical": "🔴 CRITICAL: "}.get(priority, "")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": prefix + text, "parse_mode": "Markdown"},
                )
                if r.status_code == 200:
                    logger.info(f"[VECTOR][comms] telegram sent: {text[:60]}")
                    return {"status": "sent", "platform": "telegram"}
                return {"status": "error", "code": r.status_code}
        except Exception as e:
            logger.error(f"[VECTOR][comms] telegram error: {e}")
            self._queue_message("telegram", text, priority)
            return {"status": "queued", "error": str(e)}

    async def _send_discord(self, text: str, priority: str) -> dict:
        try:
            from .discord_bot import DiscordWebhook
            cfg = CONFIG.get("discord", {}) if isinstance(CONFIG, dict) else {}
            webhook_url = cfg.get("webhook_url") or ""
            if not webhook_url:
                return {"status": "not_configured", "platform": "discord"}
            bot = DiscordWebhook(webhook_url=webhook_url)
            prefix = {"urgent": "**URGENT**\n", "critical": "**CRITICAL**\n"}.get(priority, "")
            result = await bot.send(prefix + text)
            if result.get("success"):
                return {"status": "sent", "platform": "discord"}
            return {"status": "error", "platform": "discord", "detail": result.get("error")}
        except ImportError:
            logger.opt(exception=True).debug("[VECTOR][comms] Discord adapter import failed")

        # Fallback: direct webhook call when discord_bot module is unavailable
        cfg = CONFIG.get("discord", {}) if isinstance(CONFIG, dict) else {}
        webhook_url = cfg.get("webhook_url") or ""
        if not webhook_url:
            return {"status": "not_configured", "platform": "discord"}

        prefix = {"urgent": "**URGENT**\n", "critical": "**CRITICAL**\n"}.get(priority, "")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(webhook_url, json={"content": prefix + text})
                if r.status_code in (200, 204):
                    return {"status": "sent", "platform": "discord"}
                return {"status": "error", "code": r.status_code}
        except Exception as e:
            self._queue_message("discord", text, priority)
            return {"status": "queued", "error": str(e)}

    async def _send_email(self, text: str, priority: str) -> dict:
        cfg = CONFIG.get("email", {}) if isinstance(CONFIG, dict) else {}
        smtp_host = cfg.get("smtp_host") or ""
        smtp_user = cfg.get("smtp_user") or ""
        smtp_pass = cfg.get("smtp_pass") or ""
        to_addr   = cfg.get("to_address") or smtp_user
        if not smtp_host or not smtp_user:
            return {"status": "not_configured", "platform": "email"}

        subject = f"[VECTOR/{priority.upper()}] Notification"
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(text)
            msg["Subject"] = subject
            msg["From"] = smtp_user
            msg["To"] = to_addr
            with smtplib.SMTP_SSL(smtp_host, 465) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            return {"status": "sent", "platform": "email"}
        except Exception as e:
            self._queue_message("email", text, priority)
            return {"status": "queued", "error": str(e)}

    async def _send_webhook(self, text: str, priority: str) -> dict:
        cfg = CONFIG.get("webhook", {}) if isinstance(CONFIG, dict) else {}
        url = cfg.get("url") or ""
        if not url:
            return {"status": "not_configured", "platform": "webhook"}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(url, json={"text": text, "priority": priority, "source": "vector"})
                return {"status": "sent" if r.is_success else "error", "code": r.status_code}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _send_pushover(self, text: str, priority: str) -> dict:
        cfg = CONFIG.get("pushover", {}) if isinstance(CONFIG, dict) else {}
        token = cfg.get("token") or ""
        user  = cfg.get("user_key") or ""
        if not token or not user:
            return {"status": "not_configured", "platform": "pushover"}
        prio_map = {"low": -1, "normal": 0, "high": 1, "urgent": 2, "critical": 2}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload = {
                    "token": token, "user": user, "message": text,
                    "title": "VECTOR", "priority": prio_map.get(priority, 0),
                }
                if prio_map.get(priority, 0) == 2:
                    payload.update({"retry": 60, "expire": 3600})
                r = await client.post("https://api.pushover.net/1/messages.json", data=payload)
                return {"status": "sent" if r.is_success else "error"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ── Cron scheduling ────────────────────────────────────────────────────────

    def schedule_cron_job(
        self, schedule: str, message: str, platform: str, channel: str = ""
    ) -> dict:
        """
        Schedule a recurring message. schedule = cron expression e.g. "0 9 * * *"
        Returns {status, job_id}.
        """
        if self._scheduler is None:
            self._cron_jobs.append({"schedule": schedule, "message": message,
                                     "platform": platform, "status": "queued"})
            return {"status": "queued", "reason": "APScheduler not available"}

        import uuid
        job_id = str(uuid.uuid4())[:8]
        parts = schedule.split()
        if len(parts) != 5:
            return {"status": "error", "message": "Invalid cron expression (need 5 fields)"}

        minute, hour, day, month, day_of_week = parts

        async def _send():
            await self.send_to_channel(platform, message)

        def _sync_send():
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(_send())
                else:
                    loop.run_until_complete(_send())
            except RuntimeError:
                asyncio.run(_send())

        try:
            from apscheduler.triggers.cron import CronTrigger
            self._scheduler.add_job(
                _sync_send, CronTrigger(
                    minute=minute, hour=hour, day=day,
                    month=month, day_of_week=day_of_week,
                ),
                id=job_id, replace_existing=True,
            )
            self._cron_jobs.append({
                "job_id": job_id, "schedule": schedule, "message": message,
                "platform": platform, "status": "scheduled",
            })
            logger.info(f"[VECTOR][comms] cron scheduled: {schedule} -> {platform} (id={job_id})")
            return {"status": "scheduled", "job_id": job_id}
        except Exception as e:
            logger.error(f"[VECTOR][comms] cron schedule failed: {e}")
            return {"status": "error", "message": str(e)}

    def list_cron_jobs(self) -> list[dict]:
        return list(self._cron_jobs)

    def delete_cron_job(self, job_id: str) -> bool:
        if self._scheduler:
            try:
                self._scheduler.remove_job(job_id)
            except Exception as _sve:
                logger.debug("[VECTOR][comms.messenger] cron removal failed: {}", _sve)
        before = len(self._cron_jobs)
        self._cron_jobs = [j for j in self._cron_jobs if j.get("job_id") != job_id]
        return len(self._cron_jobs) < before

    # ── Skill registry ─────────────────────────────────────────────────────────

    def register_skill(self, skill_name: str, skill_content: str) -> dict:
        """Register a VECTOR skill so it can be invoked from chat platforms."""
        self._skill_registry[skill_name] = skill_content
        logger.info(f"[VECTOR][comms] skill registered: {skill_name}")
        return {"status": "registered", "skill": skill_name}

    def get_skill(self, skill_name: str) -> str | None:
        return self._skill_registry.get(skill_name)

    def list_skills(self) -> list[str]:
        return list(self._skill_registry.keys())

    # ── Offline queue flush ────────────────────────────────────────────────────

    async def sync_pending_messages(self) -> dict:
        """Flush queued messages. Returns {synced, remaining}."""
        if not self._pending:
            return {"synced": 0, "remaining": 0}

        synced, remaining = 0, []
        for msg in list(self._pending):
            result = await self.send_to_channel(
                msg["channel"], msg["text"], msg.get("priority", "normal")
            )
            if result.get("status") == "sent":
                synced += 1
            else:
                remaining.append(msg)

        self._pending = remaining
        self._save_pending()
        return {"synced": synced, "remaining": len(remaining)}

    # ── Status (ContextEngine feed) ────────────────────────────────────────────

    def get_comms_status(self) -> dict:
        """Returns {urgent, unread, pending} — fed to ContextEngine world_state every tick."""
        return {
            "urgent": self._urgent_count,
            "unread": self._unread_count,
            "pending": len(self._pending),
        }

    def get_pending_count(self) -> int:
        return self._unread_count + len(self._pending)

    def get_message_history(self, limit: int = 100) -> list[dict]:
        return self._history[-limit:]

    def is_connected(self) -> bool:
        """Always true — no external process dependency."""
        return True

    # ── Receive (polling placeholder) ─────────────────────────────────────────

    async def receive_messages(self, limit: int = 10) -> list[dict]:
        """
        Return recent incoming messages from all platforms.
        Currently returns history buffer — real Telegram polling would go here.
        """
        msgs = self._history[-limit:]
        self._unread_count = len(msgs)
        self._urgent_count = sum(
            1 for m in msgs if self.PRIORITY_LEVELS.get(m.get("priority", "normal"), 1) >= 3
        )
        return msgs

    async def set_away_status(self, status: str, message: str = "") -> bool:
        logger.info(f"[VECTOR][comms] away status: {status} — {message}")
        return True

if __name__ == "__main__":
    import asyncio

    async def _smoke():
        hub = MessagingHub()

        # Status always works
        status = hub.get_comms_status()
        assert "urgent" in status and "unread" in status and "pending" in status

        # Notification to unconfigured platforms -> queued
        result = await hub.send_notification("test smoke", "normal")
        assert result.get("status") in ("sent", "queued")

        # Skill registry
        reg = hub.register_skill("test-skill", "skill content here")
        assert reg["status"] == "registered"
        assert "test-skill" in hub.list_skills()

        # Cron list
        jobs = hub.list_cron_jobs()
        assert isinstance(jobs, list)

        # sync pending
        sync = await hub.sync_pending_messages()
        assert "synced" in sync

        print(f"comms/messenger.py OK — status={status}, skills={hub.list_skills()}")

    asyncio.run(_smoke())

