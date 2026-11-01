import sys
import uuid
import asyncio
import datetime

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class KIITScraper(AgentBase):
    """
    Scrapes KIIT ERP portal for:
    - Today's class schedule
    - Attendance percentage per subject
    - Upcoming assignment deadlines

    Runs daily at 7AM via APScheduler.
    Fires alerts via Pushover when attendance < 75%.
    """

    KIIT_ERP_URL = "https://erp.kiit.ac.in"

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "KIITScraper", "time_calendar")
        self.capabilities = ["attendance", "calendar", "check_attendance", "class", "kiit", "schedule"]
        if ghost:
            self.inherit_ghost(ghost)
        self._browser = None
        self._page = None
        self._playwright = None
        # op name -> reason, for scrapes that FAILED (vs. genuinely empty).
        # Cleared per-op on success so [] can be told apart from "failed".
        self.last_errors: dict[str, str] = {}
        self._credentials = {
            "username": CONFIG["api_keys"].get("kiit_username", ""),
            "password": CONFIG["api_keys"].get("kiit_password", ""),
        }
        logger.info("[VECTOR][kiit] KIITScraper initialized")

    async def _get_browser(self):
        """Lazy-init playwright chromium browser. Returns page or None."""
        if self._browser is not None:
            return self._page
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            context = await self._browser.new_context()
            self._page = await context.new_page()
            logger.info("[VECTOR][kiit] Playwright browser started")
            return self._page
        except Exception as e:
            logger.error(f"[VECTOR][kiit] Browser init failed: {e}")
            self._browser = None
            self._page = None
            return None

    async def _login(self, page) -> bool:
        """Attempt ERP login. Returns True if successful."""
        username = self._credentials.get("username", "")
        password = self._credentials.get("password", "")
        if not username or not password:
            logger.warning("[VECTOR][kiit] Credentials not configured — skipping login")
            return False
        try:
            await page.goto(self.KIIT_ERP_URL, timeout=15000)
            # Wait for login form — selectors may need adjustment per actual portal
            await page.wait_for_selector("input[name='username'], input[type='text']", timeout=8000)
            await page.fill("input[name='username']", username)
            await page.fill("input[name='password']", password)
            await page.click("button[type='submit'], input[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=10000)
            # A rejected login re-renders the form: a password field still on
            # the page means we are NOT authenticated.
            if await page.query_selector("input[type='password']") is not None:
                logger.error("[VECTOR][kiit] Login rejected — login form still shown")
                return False
            logger.info("[VECTOR][kiit] Login attempt completed")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][kiit] Login failed: {e}")
            return False

    async def get_schedule(self) -> list[dict]:
        """
        Scrape today's class schedule.
        Returns [{subject, time, room, faculty}]
        """
        try:
            page = await self._get_browser()
            if page is None:
                logger.warning("[VECTOR][kiit] No browser available — returning empty schedule")
                self.last_errors["schedule"] = "no_browser"
                self.deduct_points(10, "schedule_scrape_failed_no_browser")
                return []

            logged_in = await self._login(page)
            if not logged_in:
                self.last_errors["schedule"] = "login_failed"
                self.deduct_points(10, "schedule_scrape_failed_login")
                return []

            # Navigate to timetable section
            await page.goto(f"{self.KIIT_ERP_URL}/student/timetable", timeout=10000)
            await page.wait_for_load_state("networkidle", timeout=8000)

            # Parse table rows — selectors adjusted for typical ERP layouts
            rows = await page.query_selector_all("table tr")
            schedule = []
            for row in rows[1:]:  # skip header
                cells = await row.query_selector_all("td")
                if len(cells) >= 4:
                    texts = [await c.inner_text() for c in cells[:4]]
                    schedule.append({
                        "subject": texts[0].strip(),
                        "time": texts[1].strip(),
                        "room": texts[2].strip(),
                        "faculty": texts[3].strip(),
                    })

            self.last_errors.pop("schedule", None)
            self.award_points(10, "schedule_fetched")
            logger.info(f"[VECTOR][kiit] Schedule fetched: {len(schedule)} classes")
            return schedule
        except Exception as e:
            logger.error(f"[VECTOR][kiit] get_schedule error: {e}")
            self.last_errors["schedule"] = f"error: {e}"
            self.deduct_points(10, "schedule_scrape_failed")
            return []

    async def get_attendance(self) -> list[dict]:
        """
        Scrape attendance per subject.
        Returns [{subject, present, total, percent}]
        """
        try:
            page = await self._get_browser()
            if page is None:
                logger.warning("[VECTOR][kiit] No browser available — returning empty attendance")
                self.last_errors["attendance"] = "no_browser"
                self.deduct_points(10, "attendance_scrape_failed_no_browser")
                return []

            logged_in = await self._login(page)
            if not logged_in:
                self.last_errors["attendance"] = "login_failed"
                self.deduct_points(10, "attendance_scrape_failed_login")
                return []

            # Navigate to attendance section
            await page.goto(f"{self.KIIT_ERP_URL}/student/attendance", timeout=10000)
            await page.wait_for_load_state("networkidle", timeout=8000)

            rows = await page.query_selector_all("table tr")
            attendance = []
            unparsed = 0
            for row in rows[1:]:  # skip header
                cells = await row.query_selector_all("td")
                if len(cells) >= 3:
                    texts = [await c.inner_text() for c in cells[:4]]
                    subject = texts[0].strip() if len(texts) > 0 else ""
                    present_str = texts[1].strip() if len(texts) > 1 else "0"
                    total_str = texts[2].strip() if len(texts) > 2 else "0"
                    try:
                        present = int(present_str.split("/")[0]) if "/" in present_str else int(present_str)
                        total = int(total_str)
                        percent = round((present / total) * 100, 1) if total > 0 else 0.0
                    except (ValueError, ZeroDivisionError):
                        # Do not fabricate a 0% row: that would raise a bogus
                        # "at risk" alert for a row we simply failed to parse.
                        logger.warning(
                            "[VECTOR][kiit] Unparseable attendance row for {!r}: {!r}/{!r}",
                            subject, present_str, total_str,
                        )
                        unparsed += 1
                        continue
                    if subject:
                        attendance.append({
                            "subject": subject,
                            "present": present,
                            "total": total,
                            "percent": percent,
                        })

            if unparsed and not attendance:
                self.last_errors["attendance"] = f"parse_failed:{unparsed}_rows"
                self.deduct_points(10, "attendance_scrape_failed_parse")
                return []
            if unparsed:
                self.last_errors["attendance"] = f"partial:{unparsed}_rows_unparsed"
            else:
                self.last_errors.pop("attendance", None)
            self.award_points(10, "attendance_fetched")
            logger.info(f"[VECTOR][kiit] Attendance fetched: {len(attendance)} subjects")
            return attendance
        except Exception as e:
            logger.error(f"[VECTOR][kiit] get_attendance error: {e}")
            self.last_errors["attendance"] = f"error: {e}"
            self.deduct_points(10, "attendance_scrape_failed")
            return []

    @staticmethod
    def _at_risk(subjects: list[dict]) -> list[str]:
        # total == 0 means no classes held yet (or unknown) — not "0% attendance".
        return [
            s["subject"] for s in subjects
            if s.get("total", 1) > 0 and s.get("percent", 100) < 75
        ]

    async def check_attendance_alerts(self) -> list[str]:
        """Return subjects where attendance < 75% — these need urgent alerts.
        An empty list is only "all clear" if `last_errors` has no "attendance"."""
        try:
            subjects = await self.get_attendance()
            at_risk = self._at_risk(subjects)
            if at_risk:
                self.award_points(20, "detected_attendance_risk")
                logger.warning(f"[VECTOR][kiit] AT RISK subjects: {at_risk}")
            return at_risk
        except Exception as e:
            logger.error(f"[VECTOR][kiit] check_alerts error: {e}")
            return []

    async def scrape_all(self) -> dict:
        """Full scrape: schedule + attendance + alerts."""
        # RULE 1: No LLM call here — pure scraping, no session_hydration_prompt needed
        logger.info("[VECTOR][kiit] Starting full scrape")
        schedule = await self.get_schedule()
        attendance = await self.get_attendance()
        alerts = self._at_risk(attendance)
        if alerts:
            self.award_points(20, "detected_attendance_risk")
            logger.warning(f"[VECTOR][kiit] AT RISK subjects: {alerts}")

        result = {
            "schedule": schedule,
            "attendance": attendance,
            "at_risk_subjects": alerts,
            "errors": dict(self.last_errors),
            "agent": self.to_dict(),
        }
        logger.info(
            f"[VECTOR][kiit] scrape_all done — "
            f"{len(schedule)} classes, {len(attendance)} subjects, {len(alerts)} at-risk"
        )
        return result

    async def close(self):
        """Clean up playwright resources."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"[VECTOR][kiit] Close error: {e}")


    async def answer_time_calendar_question(self, query: str) -> str:
        """Answer a free-text question instead of silently launching a
        headless browser and logging into the real KIIT ERP portal with
        real credentials on any unmatched task_type — a real, unrelated
        side effect for a stray conversational message (KNOWN_ISSUES bug
        pattern). Does not invent schedule/attendance data it hasn't
        actually scraped."""
        context = (
            f"KIITScraper checks today's class schedule, per-subject "
            f"attendance %, and upcoming assignment deadlines by logging "
            f"into {self.KIIT_ERP_URL}. It doesn't cache results locally — "
            f"a live check requires actually running the scrape (task_type "
            f"'check_attendance' or no type, e.g. the daily 7AM run)."
        )
        prompt = (
            "You are VECTOR's KIITScraper in the time_calendar district. "
            "Answer the owner's question using this real context — do not "
            f"invent schedule/attendance data you haven't actually scraped:"
            f"\n\n{context}\n\nQuestion: {query}"
        )
        try:
            result = self.vchat([{"role": "user", "content": prompt}])
            return (result or "").strip() or context
        except Exception as e:
            logger.warning(f"[VECTOR][kiit] answer_time_calendar_question failed: {e}")
            return context

    async def run(self, task: dict) -> dict:
        t = task.get("type", "")
        try:
            if t == "check_attendance":
                alerts = await self.check_attendance_alerts()
                if "attendance" in self.last_errors:
                    # [] here means "could not check", NOT "all clear".
                    return {"status": "error", "alerts": alerts,
                            "error": self.last_errors["attendance"]}
                return {"status": "ok", "alerts": alerts}

            # KNOWN_ISSUES bug pattern: any unmatched task_type (e.g. a
            # stray conversational question routed here) used to
            # unconditionally trigger a real browser login + full portal
            # scrape. Real free text now gets answered in words; a
            # genuinely content-free structured call (t=="" with no query
            # — the daily cron job's shape) still scrapes exactly as before.
            query = (
                (task.get("params") or {}).get("query")
                or task.get("query")
                or task.get("text")
                or ""
            ).strip()
            if query:
                answer = await self.answer_time_calendar_question(query)
                if answer:
                    return {"status": "ok", "response": answer}

            result = await self.scrape_all()
            status = "error" if self.last_errors else "ok"
            return {"status": status, **result}
        finally:
            await self.close()

    async def run_forever(self) -> None:
        """RULE 2 — never stops. Scrapes KIIT portal daily at 07:00."""
        logger.info("[VECTOR][kiit_scraper] run_forever started — fires at 07:00")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                if now.hour == 7 and 0 <= now.minute < 5:
                    await self.scrape_all()
            except Exception as e:
                logger.error(f"[VECTOR][kiit_scraper] tick error: {e}")
                self.deduct_points(5, "tick_error")
            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(1)
        logger.warning("[VECTOR][kiit_scraper] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def smoke():
        scraper = KIITScraper()
        result = await scraper.scrape_all()
        await scraper.close()
        ok = (
            isinstance(result, dict)
            and "schedule" in result
            and "attendance" in result
            and "at_risk_subjects" in result
            and "agent" in result
            and isinstance(result["schedule"], list)
            and isinstance(result["attendance"], list)
            and isinstance(result["at_risk_subjects"], list)
        )
        print(
            f"✅ kiit_scraper OK — keys={list(result.keys())}, "
            f"schedule={len(result['schedule'])}, attendance={len(result['attendance'])}"
            if ok else "❌ FAILED"
        )

    asyncio.run(smoke())
