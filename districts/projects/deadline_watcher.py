import sys
import uuid
import asyncio
import datetime

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from loguru import logger


class DeadlineWatcher(AgentBase):
    """
    Monitors project and KIIT deadlines. Fires reminders at T-7d, T-1d, T-0.
    Reads deadlines from semantic_memory (written by ProjectPlanner + DeadlineManager).
    """

    ALERT_DAYS = [7, 3, 1, 0]

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="DeadlineWatcher",
            district="projects",
            generation=generation,
        )
        self.capabilities = ["deadline", "deadline_check", "project"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._alerted_today: set[str] = set()
        logger.info(f"[VECTOR][deadline_watcher] ready gen={generation}")

    def add_deadline(self, name: str, deadline_date: str, project_id: str = "", urgency: str = "medium") -> None:
        """Register a deadline for tracking. Raises ValueError on an empty
        name or a non-ISO date (such a deadline would never alert)."""
        name = (name or "").strip()
        if not name:
            raise ValueError("deadline name is required")
        try:
            datetime.date.fromisoformat(deadline_date)
        except (TypeError, ValueError):
            raise ValueError(f"deadline date must be YYYY-MM-DD, got {deadline_date!r}") from None
        self._memory.remember(
            key=f"deadline:{deadline_date}:{name.replace(' ', '_')}",
            value=f"{name}|{project_id}|{urgency}",
            category="project_deadline",
            confidence=0.95,
        )
        logger.info(f"[VECTOR][deadline_watcher] registered: {name} due {deadline_date}")

    def _fetch_upcoming_deadlines(self, within_days: int = 30) -> list[dict]:
        today = datetime.date.today()
        cutoff_start = today.isoformat()
        cutoff_end = (today + datetime.timedelta(days=within_days)).isoformat()
        # Raises on DB failure: an unreadable store must not look like "no deadlines".
        self._memory = EpisodicMemory()
        cur = self._memory.conn.cursor()
        cur.execute(
            "SELECT key, value FROM semantic_memory "
            "WHERE category = 'project_deadline' "
            "ORDER BY key ASC"
        )
        rows = cur.fetchall()

        deadlines = []
        for key, value in rows:
            # key format: deadline:YYYY-MM-DD:name
            parts = key.split(":", 2)
            if len(parts) < 3:
                continue
            date_str = parts[1]
            if not (cutoff_start <= date_str <= cutoff_end):
                continue
            val_parts = value.split("|")
            try:
                deadline_date = datetime.date.fromisoformat(date_str)
                days_away = (deadline_date - today).days
                deadlines.append({
                    "name": val_parts[0] if val_parts else parts[2],
                    "date": date_str,
                    "days_away": days_away,
                    "project_id": val_parts[1] if len(val_parts) > 1 else "",
                    "urgency": val_parts[2] if len(val_parts) > 2 else "medium",
                })
            except ValueError:
                logger.warning("[VECTOR][deadline_watcher] unparseable deadline skipped: {}", key)
                continue

        return sorted(deadlines, key=lambda x: x["days_away"])

    def _alert_key(self, name: str, days_away: int) -> str:
        return f"{datetime.date.today().isoformat()}:{name}:{days_away}"

    async def check(self) -> list[dict]:
        deadlines = self._fetch_upcoming_deadlines(within_days=30)
        fired = []

        for d in deadlines:
            for threshold in self.ALERT_DAYS:
                if d["days_away"] == threshold:
                    key = self._alert_key(d["name"], threshold)
                    if key in self._alerted_today:
                        continue
                    self._alerted_today.add(key)

                    label = "TODAY" if threshold == 0 else f"in {threshold} day{'s' if threshold > 1 else ''}"
                    self._memory.store(
                        event_type="deadline_alert",
                        content=f"DEADLINE {label}: {d['name']} ({d['date']}) [{d['urgency']}]",
                        tags=["projects", "deadline", d["urgency"]],
                        source="deadline_watcher",
                    )
                    logger.warning(f"[VECTOR][deadline_watcher] ALERT: {d['name']} due {label}")
                    fired.append(d)

        return fired

    async def run(self, task: dict) -> dict:
        p = task.get("params") or {}
        if task.get("type") == "add_deadline":
            try:
                self.add_deadline(p.get("name", ""), p.get("date", ""), p.get("project_id", ""), p.get("urgency", "medium"))
            except ValueError as e:
                return {"status": "error", "error": str(e)}
            return {"status": "ok"}
        try:
            alerts = await self.check()
        except Exception as e:
            logger.error("[VECTOR][deadline_watcher] deadline check failed: {}", e)
            self.deduct_points(5, "deadline check failed")
            return {"status": "error", "error": f"deadline store unreadable: {e}", "alerts": [], "count": 0}
        return {"status": "ok", "alerts": alerts, "count": len(alerts)}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][deadline_watcher] run_forever — checking every hour")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                # Reset daily alert cache at midnight
                if now.hour == 0 and now.minute < 5:
                    self._alerted_today.clear()
                # Check deadlines at 09:00 and 18:00
                if now.minute < 5 and now.hour in (9, 18):
                    await self.check()
            except Exception as e:
                logger.error(f"[VECTOR][deadline_watcher] tick: {e}")
                self.deduct_points(5, "tick error")
            for _ in range(60):
                if not self.is_alive:
                    break
                await asyncio.sleep(60)
        logger.warning("[VECTOR][deadline_watcher] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import asyncio

    async def _smoke():
        bot = DeadlineWatcher()
        assert bot.health_points == 500
        # Add a deadline 3 days from now
        future = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
        bot.add_deadline("Test Project Submit", future, urgency="high")
        fired = await bot.check()
        # Should fire 3-day alert
        assert any(d["name"] == "Test Project Submit" for d in fired)
        print(f"OK deadline_watcher.py HP={bot.health_points} fired={len(fired)}")

    asyncio.run(_smoke())
