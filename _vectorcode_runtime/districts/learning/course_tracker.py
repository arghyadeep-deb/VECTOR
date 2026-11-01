"""
Module: agents/learning/course_tracker.py
District: learning | Focus: Track online courses, lessons, and learning progress
"""

from core.memory.db_utils import apply_pragmas
import sys
from pathlib import Path
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime, sqlite3, threading
from typing import Optional


class CourseTracker(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="CourseTracker",
            district="learning",
            generation=1
        )
        self.capabilities = ["add_course", "course", "generate_report", "get_progress", "learn", "learning", "log_lesson", "progress"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self._lock = threading.RLock()
        from core.runtime_paths import data_path

        self.db_path = data_path("learning_courses.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info("[VECTOR][learning] CourseTracker ready")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        apply_pragmas(conn)
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""CREATE TABLE IF NOT EXISTS courses (
                    name TEXT PRIMARY KEY,
                    platform TEXT,
                    url TEXT,
                    added_at TEXT,
                    total_lessons INTEGER DEFAULT 0,
                    completed_lessons INTEGER DEFAULT 0
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_name TEXT,
                    lesson_name TEXT,
                    completed_at TEXT,
                    notes TEXT,
                    UNIQUE(course_name, lesson_name)
                )""")
                conn.commit()
            finally:
                conn.close()

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def add_course(self, name: str, platform: str, url: str) -> dict:
        logger.info(f"[VECTOR][learning] Adding course: {name} from {platform}")
        self.add_lesson({"action": "add_course", "course": name, "platform": platform})

        if not (name or "").strip():
            return {"error": "Course name is required"}

        added_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            conn = self._get_conn()
            try:
                # Upsert: INSERT OR REPLACE would reset total/completed counters
                # of an already-tracked course while its lesson rows remain.
                conn.execute(
                    "INSERT INTO courses (name, platform, url, added_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET platform = excluded.platform, url = excluded.url",
                    (name, platform, url, added_at)
                )
                conn.commit()
            finally:
                conn.close()

        result = {"course_name": name, "platform": platform, "url": url, "added_at": added_at}
        self.memory.store(
            event_type="course_added",
            content=f"Added course: {name} on {platform}",
            tags=["course", platform, name],
            context=result,
            source="CourseTracker"
        )

        logger.info(f"[VECTOR][learning] Course '{name}' added from {platform}")
        return result

    def get_progress(self, course_name: str) -> dict:
        logger.info(f"[VECTOR][learning] Getting progress for: {course_name}")
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "SELECT platform, url, added_at, total_lessons, completed_lessons FROM courses WHERE name = ?",
                    (course_name,)
                )
                row = cursor.fetchone()
                if not row:
                    return {"error": f"Course '{course_name}' not found"}
                platform, url, added_at, total, completed = row
                cursor2 = conn.execute(
                    "SELECT lesson_name, completed_at FROM lessons WHERE course_name = ? ORDER BY completed_at DESC",
                    (course_name,)
                )
                lessons = [{"lesson": r[0], "completed_at": r[1]} for r in cursor2.fetchall()]
            finally:
                conn.close()

        progress_pct = round((completed / total) * 100, 2) if total > 0 else 0.0
        return {
            "course_name": course_name,
            "platform": platform,
            "url": url,
            "total_lessons": total,
            "completed_lessons": completed,
            "progress_percent": progress_pct,
            "added_at": added_at,
            "recent_lessons": lessons[:10],  # ordered newest-first
        }

    def log_lesson(self, course_name: str, lesson_name: str, notes: Optional[str] = None) -> dict:
        logger.info(f"[VECTOR][learning] Logging lesson: {course_name} - {lesson_name}")
        self.add_lesson({"action": "log_lesson", "course": course_name, "lesson": lesson_name})

        if not (course_name or "").strip() or not (lesson_name or "").strip():
            return {"error": "course_name and lesson_name are required"}

        completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            conn = self._get_conn()
            try:
                if not conn.execute("SELECT 1 FROM courses WHERE name = ?", (course_name,)).fetchone():
                    logger.warning("[VECTOR][learning] log_lesson: unknown course '{}'", course_name)
                    return {"error": f"Course '{course_name}' not found"}
                conn.execute(
                    "INSERT OR IGNORE INTO lessons (course_name, lesson_name, completed_at, notes) VALUES (?, ?, ?, ?)",
                    (course_name, lesson_name, completed_at, notes or "")
                )
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM lessons WHERE course_name = ?", (course_name,)
                )
                completed = cursor.fetchone()[0]
                conn.execute(
                    "UPDATE courses SET completed_lessons = ? WHERE name = ?",
                    (completed, course_name)
                )
                conn.commit()
            finally:
                conn.close()

        result = {"course_name": course_name, "lesson_name": lesson_name, "completed_at": completed_at, "notes": notes}
        self.memory.store(
            event_type="lesson_logged",
            content=f"Completed lesson '{lesson_name}' in course '{course_name}'",
            tags=["learning", "lesson", course_name],
            context=result,
            source="CourseTracker"
        )

        return result

    def generate_report(self) -> dict:
        logger.info("[VECTOR][learning] Generating learning progress report")
        self.add_lesson({"action": "generate_report"})

        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute("SELECT name, platform, total_lessons, completed_lessons, added_at FROM courses")
                courses = []
                for row in cursor.fetchall():
                    total = row[2]
                    completed = row[3]
                    pct = round((completed / total) * 100, 2) if total > 0 else 0.0
                    courses.append({"name": row[0], "platform": row[1], "total": total, "completed": completed, "percent": pct, "added_at": row[4]})
                cursor2 = conn.execute("SELECT COUNT(*) FROM lessons")
                total_lessons = cursor2.fetchone()[0]
            finally:
                conn.close()

        overall_pct = 0.0
        if courses:
            overall_pct = round(sum(c["percent"] for c in courses) / len(courses), 2)

        prompt = f"Summarize this learning progress: {json.dumps(courses, indent=2)}. Total lessons completed: {total_lessons}, Overall progress: {overall_pct}%. Give actionable insights and recommendations."
        insights = self._call_ollama(prompt)

        report = {
            "total_courses": len(courses),
            "total_lessons_completed": total_lessons,
            "overall_progress_percent": overall_pct,
            "courses": courses,
            "insights": insights,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="learning_report_generated",
            content=f"Learning report: {len(courses)} courses, {total_lessons} lessons",
            tags=["learning", "report", "progress"],
            context=report,
            source="CourseTracker"
        )

        return report


    async def run(self, task: dict) -> dict:
        # 2026-07-29 (found while investigating the languages TIER6 eval
        # finding): this completely ignored task_type and every param —
        # ANY dispatch, including a real chat question about something
        # unrelated to course progress, always returned the exact same
        # generate_report() dump. Worst-case instance of the #1/#14/#15/
        # #21/#33/#36 bug class: not even reading the task at all. Add real
        # branches for this agent's actual capabilities, and a grounded
        # free-text fallback for anything else with a real question;
        # generate_report() stays the default only when there's truly no
        # query to answer (matches this agent's original always-safe,
        # non-destructive behavior for structurally empty dispatches).
        p = task.get("params", {}) or {}
        task_type = task.get("type", "")

        def _wrap(res: dict) -> dict:
            return {"status": "error" if res.get("error") else "ok", **res}

        if task_type == "add_course":
            return _wrap(self.add_course(
                p.get("name", ""), p.get("platform", ""), p.get("url", ""),
            ))
        if task_type == "get_progress":
            return _wrap(self.get_progress(p.get("course_name", "")))
        if task_type == "log_lesson":
            return _wrap(self.log_lesson(
                p.get("course_name", ""), p.get("lesson_name", ""), p.get("notes"),
            ))
        if task_type in ("generate_report", "report", "progress_report"):
            result = self.generate_report()
            return {"status": "ok", **result}

        # NOTE: an empty/missing task_type is exactly the shape a real
        # free-text query arrives in (governor dispatch always sets a real
        # type, but direct/manual calls and some callers don't) — check for
        # a real query BEFORE falling to the report default, or a genuine
        # question with no explicit type would get silently swallowed by
        # the report dump again, the same bug this fix exists to close.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            try:
                answer = self._call_ollama(
                    "You are VECTOR's CourseTracker, a learning-district agent that "
                    "tracks the owner's online course enrollments and lesson progress "
                    "(add_course, get_progress, log_lesson, generate_report). Answer "
                    f"the owner's question directly:\n\n{query}"
                )
                return {"status": "ok", "response": answer or ""}
            except Exception as e:
                logger.warning("[VECTOR][learning] course_tracker free-text fallback failed: {}", e)

        result = self.generate_report()
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = CourseTracker()
    assert agent.district == "learning"

    agent.add_course("Deep Learning Specialization", "Coursera", "https://coursera.org/deep-learning")
    agent.add_course("FastAPI Masterclass", "Udemy", "https://udemy.com/fastapi")

    agent.log_lesson("Deep Learning Specialization", "Neural Networks Basics", "Completed forward propagation")
    agent.log_lesson("Deep Learning Specialization", "Deep Neural Networks", "Learned backprop")
    agent.log_lesson("FastAPI Masterclass", "Introduction to FastAPI", "Set up environment")

    progress = agent.get_progress("Deep Learning Specialization")
    assert progress["completed_lessons"] == 2

    report = agent.generate_report()
    assert "total_courses" in report
    assert report["total_courses"] >= 2
    assert "insights" in report

    print("✅ course_tracker.py OK")
