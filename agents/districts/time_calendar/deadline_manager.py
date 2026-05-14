import sys
import uuid
import asyncio
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class DeadlineManager(AgentBase):
    """
    Manages deadlines via Google Calendar API.
    Energy window routing:
      10AM-1PM  → peak: schedule hardest tasks
      2PM-4PM   → low: light tasks only
      7PM-10PM  → moderate: review + planning
      10PM+     → only critical tasks
      0AM-10AM  → off
    """

    ENERGY_WINDOWS = [
        (10, 13, "peak"),
        (14, 16, "low"),
        (19, 22, "moderate"),
        (22, 24, "critical_only"),
        (0, 10, "off"),
    ]

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "DeadlineManager", "time_calendar")
        if ghost:
            self.inherit_ghost(ghost)
        self._service = None
        logger.info("[VECTOR][deadline] DeadlineManager initialized")

    def _get_service(self):
        """Lazy-load Google Calendar service. Returns None if not configured."""
        if self._service is not None:
            return self._service
        try:
            creds_path = CONFIG["api_keys"].get("google_credentials_path", "")
            if not creds_path or not Path(creds_path).exists():
                logger.warning("[VECTOR][deadline] Google Calendar not configured — no credentials path")
                return None

            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
            credentials = service_account.Credentials.from_service_account_file(
                creds_path, scopes=SCOPES
            )
            self._service = build("calendar", "v3", credentials=credentials)
            logger.info("[VECTOR][deadline] Google Calendar service initialized")
            return self._service
        except ImportError:
            logger.warning("[VECTOR][deadline] google-api-python-client not installed")
            return None
        except Exception as e:
            logger.warning(f"[VECTOR][deadline] Google Calendar not configured: {e}")
            return None

    def get_current_energy_window(self) -> str:
        """Map current hour to an energy window label."""
        hour = datetime.datetime.now().hour
        for start, end, label in self.ENERGY_WINDOWS:
            if start <= hour < end:
                return label
        return "off"

    def get_upcoming_events(self, hours: int = 24) -> list[dict]:
        """
        Fetch upcoming events within the next N hours.
        Returns [{title, start, end, description}]
        """
        service = self._get_service()
        if service is None:
            logger.info("[VECTOR][deadline] No calendar service — returning empty events")
            return []
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            time_min = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            time_max = (now + datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            items = events_result.get("items", [])
            events = []
            for item in items:
                start = item.get("start", {}).get("dateTime", item.get("start", {}).get("date", ""))
                end = item.get("end", {}).get("dateTime", item.get("end", {}).get("date", ""))
                events.append({
                    "title": item.get("summary", "Untitled"),
                    "start": start,
                    "end": end,
                    "description": item.get("description", ""),
                })
            self.award_points(5, "calendar_fetched")
            logger.info(f"[VECTOR][deadline] Fetched {len(events)} events")
            return events
        except Exception as e:
            logger.error(f"[VECTOR][deadline] get_upcoming_events failed: {e}")
            self.deduct_points(5, "calendar_fetch_failed")
            return []

    def get_next_event(self) -> dict | None:
        """Return the first upcoming event within the next 2 hours, or None."""
        events = self.get_upcoming_events(hours=2)
        return events[0] if events else None

    def is_class_soon(self, minutes_ahead: int = 20) -> bool:
        """Check if a class/lecture is starting within the next N minutes."""
        try:
            events = self.get_upcoming_events(hours=1)
            now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            threshold = now + datetime.timedelta(minutes=minutes_ahead)
            for event in events:
                title_lower = event.get("title", "").lower()
                is_class = any(kw in title_lower for kw in ["class", "lecture", "lab", "tutorial", "workshop"])
                start_str = event.get("start", "")
                if is_class and start_str:
                    try:
                        # Parse ISO format, strip timezone suffix
                        start_dt = datetime.datetime.fromisoformat(start_str.replace("Z", ""))
                        if now <= start_dt <= threshold:
                            logger.info(f"[VECTOR][deadline] Class soon: {event['title']} at {start_str}")
                            return True
                    except ValueError:
                        pass
            return False
        except Exception as e:
            logger.error(f"[VECTOR][deadline] is_class_soon error: {e}")
            return False

    def _get_free_blocks_today(self) -> list[str]:
        """Compute free time blocks for the rest of today (rough heuristic)."""
        try:
            events = self.get_upcoming_events(hours=12)
            busy_hours = set()
            for event in events:
                start_str = event.get("start", "")
                end_str = event.get("end", "")
                if start_str and end_str:
                    try:
                        start_dt = datetime.datetime.fromisoformat(start_str.replace("Z", ""))
                        end_dt = datetime.datetime.fromisoformat(end_str.replace("Z", ""))
                        hour = start_dt.hour
                        while hour < end_dt.hour:
                            busy_hours.add(hour)
                            hour += 1
                    except ValueError:
                        pass
            now_hour = datetime.datetime.now().hour
            free = []
            for h in range(now_hour, 24):
                if h not in busy_hours:
                    window = self._hour_to_window(h)
                    if window not in ("off",):
                        free.append(f"{h:02d}:00 ({window})")
            return free[:5]  # top 5 free slots
        except Exception as e:
            logger.error(f"[VECTOR][deadline] free blocks error: {e}")
            return []

    def _hour_to_window(self, hour: int) -> str:
        for start, end, label in self.ENERGY_WINDOWS:
            if start <= hour < end:
                return label
        return "off"

    def get_schedule_context(self) -> dict:
        """
        Returns rich schedule context for session hydration.
        Used by context_engine before LLM calls.
        """
        energy_window = self.get_current_energy_window()
        next_event = self.get_next_event()
        upcoming = self.get_upcoming_events(hours=24)
        free_blocks = self._get_free_blocks_today()

        # Separate deadlines (events with "deadline" / "due" in title)
        deadlines = [
            e for e in upcoming
            if any(kw in e.get("title", "").lower() for kw in ["deadline", "due", "submit", "exam", "test"])
        ]

        result = {
            "energy_window": energy_window,
            "next_event": next_event,
            "free_blocks_today": free_blocks,
            "upcoming_deadlines": deadlines,
            "total_events_today": len(upcoming),
        }
        logger.info(f"[VECTOR][deadline] Schedule context built — window={energy_window}")
        return result


    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        events = self.get_upcoming_events(p.get("hours", 24))
        ctx = self.get_schedule_context()
        return {"status": "ok", "events": events, "context": ctx}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    manager = DeadlineManager()
    window = manager.get_current_energy_window()
    events = manager.get_upcoming_events()
    context = manager.get_schedule_context()

    ok = (
        isinstance(window, str)
        and window in ("peak", "low", "moderate", "critical_only", "off")
        and isinstance(events, list)
        and isinstance(context, dict)
        and "energy_window" in context
        and "next_event" in context
        and "free_blocks_today" in context
        and "upcoming_deadlines" in context
    )
    print(
        f"✅ deadline_manager OK — window={window}, events={len(events)}, "
        f"context_keys={list(context.keys())}"
        if ok else "❌ FAILED"
    )
