
import sys
import uuid
import asyncio
import datetime
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

# Naive timestamps from the calendar are interpreted in the zone events are
# created in (create_event uses Asia/Kolkata). Fixed offset: no tzdata needed.
_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _parse_event_dt(value: str) -> datetime.datetime:
    """Parse a Google Calendar dateTime into an AWARE datetime.
    Raises ValueError on garbage. 'Z' and '+05:30' offsets are honoured
    (the old code stripped 'Z' and then compared naive vs aware -> TypeError)."""
    dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_IST)
    return dt


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

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "DeadlineManager", "time_calendar")
        self.capabilities = ["calendar", "deadline", "deadline_check", "off", "peak", "schedule"]
        if ghost:
            self.inherit_ghost(ghost)
        self._service = None
        # None = no fetch yet; "" = last fetch OK; else the failure reason.
        # Lets callers tell "empty calendar" from "could not read calendar".
        self.last_fetch_error: str | None = None
        logger.info("[VECTOR][deadline] DeadlineManager initialized")

    def _get_service(self):
        """Lazy-load Google Calendar service. Tries service account file, then OAuth token from collections DB."""
        if self._service is not None:
            return self._service
        try:
            from googleapiclient.discovery import build

            SCOPES = ["https://www.googleapis.com/auth/calendar"]

            # Strategy 1: service account JSON file
            creds_path = CONFIG["api_keys"].get("google_credentials_path", "")
            if creds_path and Path(creds_path).exists():
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_file(
                    creds_path, scopes=SCOPES
                )
                self._service = build("calendar", "v3", credentials=credentials)
                logger.info("[VECTOR][deadline] Google Calendar: service account")
                return self._service

            # Strategy 2: FL-033's shared Google OAuth token
            # (~/.vector/connectors/google.json) -- the owner already
            # completed this consent on 2026-10-13 for the vectorcode
            # connectors system (Gmail/Calendar/Drive/Tasks/Contacts, one
            # consent for all of them); reuse it here instead of a second,
            # redundant OAuth setup (2026-10-25 correction — this used to
            # read a separate, never-actually-populated collections-DB
            # token store from a parallel OAuth app that was never used).
            try:
                from vectorcode.src.connectors.oauth import get_valid_google_token
                tokens = get_valid_google_token()
                if tokens:
                    import google.oauth2.credentials as _gcreds
                    credentials = _gcreds.Credentials(
                        token=tokens.get("access_token"),
                        refresh_token=tokens.get("refresh_token"),
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=tokens.get("client_id", ""),
                        client_secret=tokens.get("client_secret", ""),
                        scopes=SCOPES,
                    )
                    self._service = build("calendar", "v3", credentials=credentials)
                    logger.info("[VECTOR][deadline] Google Calendar: FL-033 shared Google token")
                    return self._service
            except Exception as _oauth_err:
                logger.warning("[VECTOR][deadline] OAuth token fallback failed: {}", _oauth_err)

            logger.warning("[VECTOR][deadline] Google Calendar not configured — no credentials found")
            return None
        except ImportError:
            logger.warning("[VECTOR][deadline] google-api-python-client not installed — run: pip install google-api-python-client")
            return None
        except Exception as e:
            logger.warning(f"[VECTOR][deadline] Google Calendar init failed: {e}")
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
            self.last_fetch_error = "calendar_not_configured"
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
            self.last_fetch_error = ""
            self.award_points(5, "calendar_fetched")
            logger.info(f"[VECTOR][deadline] Fetched {len(events)} events")
            return events
        except Exception as e:
            logger.error(f"[VECTOR][deadline] get_upcoming_events failed: {e}")
            self.last_fetch_error = f"fetch_failed: {e}"
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
            now = datetime.datetime.now(datetime.timezone.utc)
            threshold = now + datetime.timedelta(minutes=minutes_ahead)
            for event in events:
                title_lower = event.get("title", "").lower()
                is_class = any(kw in title_lower for kw in ["class", "lecture", "lab", "tutorial", "workshop"])
                start_str = event.get("start", "")
                if is_class and start_str:
                    try:
                        start_dt = _parse_event_dt(start_str)
                        if now <= start_dt <= threshold:
                            logger.info(f"[VECTOR][deadline] Class soon: {event['title']} at {start_str}")
                            return True
                    except ValueError:
                        logger.warning("[VECTOR][deadline] Unparseable event start {!r} — skipped", start_str)
            return False
        except Exception as e:
            logger.error(f"[VECTOR][deadline] is_class_soon error: {e}")
            return False

    def create_event(self, title: str, start_iso: str, end_iso: str, description: str = "") -> dict:
        """Create a Google Calendar event. Returns {id, link} or {error}."""
        service = self._get_service()
        if service is None:
            return {"error": "Google Calendar not configured"}
        try:
            event_body = {
                "summary": title,
                "description": description,
                "start": {"dateTime": start_iso, "timeZone": "Asia/Kolkata"},
                "end": {"dateTime": end_iso, "timeZone": "Asia/Kolkata"},
            }
            created = service.events().insert(calendarId="primary", body=event_body).execute()
            logger.info(f"[VECTOR][deadline] Created event: {title}")
            return {"id": created.get("id", ""), "link": created.get("htmlLink", "")}
        except Exception as e:
            logger.error(f"[VECTOR][deadline] create_event failed: {e}")
            return {"error": str(e)}

    def _get_free_blocks_today(self) -> list[str]:
        """Compute free time blocks for the rest of today (rough heuristic)."""
        try:
            events = self.get_upcoming_events(hours=12)
            if self.last_fetch_error:
                # Calendar unreadable: do NOT report every hour as free.
                logger.warning("[VECTOR][deadline] free blocks unknown — calendar unavailable: {}", self.last_fetch_error)
                return []
            local_tz = datetime.datetime.now().astimezone().tzinfo
            today = datetime.datetime.now(local_tz).date()
            busy_hours = set()
            for event in events:
                start_str = event.get("start", "")
                end_str = event.get("end", "")
                # Date-only (all-day) events don't block hourly slots.
                if start_str and end_str and "T" in start_str and "T" in end_str:
                    try:
                        start_dt = _parse_event_dt(start_str).astimezone(local_tz)
                        end_dt = _parse_event_dt(end_str).astimezone(local_tz)
                    except ValueError:
                        logger.warning("[VECTOR][deadline] Unparseable event times {!r}/{!r} — skipped", start_str, end_str)
                        continue
                    # Any overlap with an hour slot makes it busy (sub-hour and
                    # past-midnight events included).
                    for h in range(24):
                        slot_start = datetime.datetime.combine(today, datetime.time(h), tzinfo=local_tz)
                        slot_end = slot_start + datetime.timedelta(hours=1)
                        if start_dt < slot_end and end_dt > slot_start:
                            busy_hours.add(h)
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
            # False => events/free blocks are EMPTY BECAUSE the calendar could
            # not be read, not because the owner is free.
            "calendar_available": not self.last_fetch_error,
        }
        if self.last_fetch_error:
            result["calendar_error"] = self.last_fetch_error
        logger.info(f"[VECTOR][deadline] Schedule context built — window={energy_window}")
        return result

    async def run(self, task: dict) -> dict:
        p = task.get("params") if isinstance(task.get("params"), dict) else {}
        raw_hours = p.get("hours", task.get("hours", 24))
        try:
            hours = max(1, min(int(raw_hours), 24 * 31))
        except (TypeError, ValueError):
            hours = 24
        events = self.get_upcoming_events(hours)
        error = self.last_fetch_error
        ctx = self.get_schedule_context()
        if error:
            return {"status": "error", "error": error, "events": [], "context": ctx}
        return {"status": "ok", "events": events, "context": ctx}

    async def run_forever(self) -> None:
        """RULE 2 — never stops. Checks deadlines every 30 minutes."""
        logger.info("[VECTOR][deadline_manager] run_forever started — 30min check interval")
        while self.is_alive:
            try:
                context = self.get_schedule_context()
                if context.get("attendance_risk"):
                    logger.warning(f"[VECTOR][deadline_manager] attendance risk: {context['attendance_risk']}")
            except Exception as e:
                logger.error(f"[VECTOR][deadline_manager] tick error: {e}")
                self.deduct_points(5, "tick_error")
            for _ in range(1800):
                if not self.is_alive:
                    break
                await asyncio.sleep(1)
        logger.warning("[VECTOR][deadline_manager] died — HP=0")

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
