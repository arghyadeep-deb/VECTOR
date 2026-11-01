import sys
import subprocess
import uuid
import asyncio
import datetime
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger

_CHAIRMAN = CONFIG["models"]["chairman"]
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_DOCS_DIR = _BASE_DIR / "docs"


class DocGenerator(AgentBase):
    """
    Creates structured documents (weekly summaries, changelogs, district reports)
    from VECTOR's live data — episodic memory and git history.
    RULE 11: vector-reasoning (local), not Claude API.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="DocGenerator",
            district="documentation",
            generation=generation,
        )
        self.capabilities = ["changelog", "district_report", "docs", "documentation", "generate", "generate_docs", "weekly_summary"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        _DOCS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"[VECTOR][doc_generator] ready gen={generation}")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _llm(self, prompt: str) -> str:
        """Single LLM call — always hydrates context first (RULE 1)."""
        hydration = self._context.session_hydration_prompt()
        try:
            from core.inference.vectorcode_llm import chat
            text = chat(
                model=_CHAIRMAN,
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "user", "content": prompt},
                ],
                timeout=90.0,
            )
            if not text:
                raise ValueError("empty response")
            return text
        except Exception as e:
            logger.warning(f"[VECTOR][doc_generator] LLM unavailable: {e}")
            return ""

    def _fetch_recent_events(self, days: int = 7, limit: int = 200) -> list[dict]:
        """Pull episodic_memory events from the last N days."""
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        ).isoformat()
        try:
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cur:
                cur.execute(
                    """
                    SELECT event_type, content, tags, timestamp, source
                    FROM episodic_memory
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (cutoff, limit),
                )
                rows = cur.fetchall()
                return [
                    {"event_type": r[0], "content": r[1], "tags": r[2],
                     "timestamp": r[3], "source": r[4]}
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"[VECTOR][doc_generator] fetch events failed: {e}")
            return []

    def _fetch_agent_hp(self) -> dict[str, int]:
        """Read current HP for all known agents from agent_history (latest per name)."""
        try:
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cur:
                cur.execute(
                    """
                    SELECT agent_name, final_hp
                    FROM agent_history
                    ORDER BY died_at DESC
                    """,
                )
                rows = cur.fetchall()
                seen: dict[str, int] = {}
                for name, hp in rows:
                    if name not in seen:
                        seen[name] = hp
                return seen
        except Exception as e:
            logger.error(f"[VECTOR][doc_generator] fetch HP failed: {e}")
            return {}

    # ── Core generators ────────────────────────────────────────────────────────

    def generate_weekly_summary(self) -> str:
        """
        Fetch last 7 days from episodic_memory → LLM → structured weekly report.
        Covers: what VECTOR did, decisions made, HP changes, goals progressed.
        """
        events = self._fetch_recent_events(days=7)
        hp_map = self._fetch_agent_hp()
        date_str = datetime.date.today().isoformat()

        if not events:
            fallback = (
                f"# VECTOR Weekly Summary — {date_str}\n\n"
                "*No episodic events found for the past 7 days.*"
            )
            return fallback

        event_digest = "\n".join(
            f"- [{e['timestamp'][:10]}] {e['event_type']}: {e['content'][:120]}"
            for e in events[:80]
        )
        hp_digest = "\n".join(f"- {name}: {hp} HP" for name, hp in list(hp_map.items())[:20])

        prompt = (
            f"Generate a structured weekly report for VECTOR autonomous AI system.\n"
            f"Week ending: {date_str}\n\n"
            f"RECENT EVENTS (last 7 days):\n{event_digest}\n\n"
            f"AGENT HP STATUS:\n{hp_digest or '(none recorded)'}\n\n"
            "Format:\n"
            "# VECTOR Weekly Summary — {date}\n\n"
            "## What VECTOR Did\n(bullet list of key actions)\n\n"
            "## Decisions Made\n(key decisions + rationale)\n\n"
            "## Agent Health\n(HP changes, any deaths/births)\n\n"
            "## Goals Progressed\n(which goals advanced and how)\n\n"
            "## Next Week Priorities\n(top 3 focuses)"
        )
        text = self._llm(prompt)
        if not text:
            text = (
                f"# VECTOR Weekly Summary — {date_str}\n\n"
                f"## Events\n{event_digest}\n\n"
                f"## Agent HP\n{hp_digest or '(none)'}"
            )
        return text

    def generate_changelog(self) -> str:
        """
        Read last 20 git commits via subprocess → format as clean CHANGELOG.md.
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(_BASE_DIR), "log", "--oneline", "-20",
                 "--format=%h|%ai|%s|%an"],
                capture_output=True, text=True, timeout=15,
            )
            raw_log = result.stdout.strip()
        except Exception as e:
            logger.warning(f"[VECTOR][doc_generator] git log failed: {e}")
            raw_log = ""

        if not raw_log:
            return "# CHANGELOG\n\n*No git history available.*"

        entries: list[str] = []
        for line in raw_log.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                sha, date, subject, author = parts
                entries.append(f"- `{sha}` ({date[:10]}) {subject} — *{author}*")
            else:
                entries.append(f"- {line}")

        log_block = "\n".join(entries)
        prompt = (
            "Format this git log as a clean CHANGELOG.md with grouped sections "
            "(Features, Fixes, Refactors, Other). Use the commit messages as-is; "
            "just group and add headers.\n\n"
            f"GIT LOG:\n{log_block}"
        )
        text = self._llm(prompt)
        if not text:
            date_str = datetime.date.today().isoformat()
            text = f"# CHANGELOG\n\n*Updated: {date_str}*\n\n## Recent Commits\n{log_block}"
        return text

    def generate_district_report(self, district_name: str) -> str:
        """
        Aggregate that district's episodic events → performance report.
        """
        try:
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cur:
                cur.execute(
                    """
                    SELECT event_type, content, timestamp
                    FROM episodic_memory
                    WHERE source = ? OR tags LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT 100
                    """,
                    (district_name, f'%"{district_name}"%'),
                )
                rows = cur.fetchall()
                events = [
                    {"event_type": r[0], "content": r[1], "timestamp": r[2]}
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"[VECTOR][doc_generator] district query failed: {e}")
            events = []

        date_str = datetime.date.today().isoformat()
        if not events:
            return (
                f"# District Report — {district_name}\n\n"
                f"*Generated: {date_str}*\n\n"
                "*No events recorded for this district.*"
            )

        digest = "\n".join(
            f"- [{e['timestamp'][:10]}] {e['event_type']}: {e['content'][:120]}"
            for e in events[:60]
        )
        prompt = (
            f"Generate a performance report for the VECTOR '{district_name}' district.\n"
            f"Generated: {date_str}\n\n"
            f"EVENTS:\n{digest}\n\n"
            "Format:\n"
            "# District Report — {district}\n\n"
            "## Summary\n"
            "## Key Actions\n"
            "## Performance\n(success rate, errors, notable outcomes)\n"
            "## Recommendations\n"
        )
        text = self._llm(prompt)
        if not text:
            text = (
                f"# District Report — {district_name}\n\n"
                f"*Generated: {date_str}*\n\n"
                f"## Events\n{digest}"
            )
        return text

    # ── Write ──────────────────────────────────────────────────────────────────

    def write_document(self, content: str, doc_type: str) -> bool:
        """
        Save document to docs/ directory and Obsidian Reports/ folder.
        doc_type used as filename base and Obsidian tag.
        """
        date_str = datetime.date.today().isoformat()
        filename = f"{doc_type}_{date_str}.md"
        out_path = _DOCS_DIR / filename

        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            logger.info(f"[VECTOR][doc_generator] wrote {out_path}")
        except Exception as e:
            logger.error(f"[VECTOR][doc_generator] disk write failed: {e}")
            return False

        title = f"{doc_type.replace('_', ' ').title()} — {date_str}"
        try:
            self._obsidian.write_note(
                title=title,
                content=content,
                folder="Reports",
                tags=["report", doc_type, "auto-generated", "vector"],
            )
        except Exception as e:
            logger.warning(f"[VECTOR][doc_generator] obsidian write failed: {e}")

        return True

    # ── run ───────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """
        task["type"]:
          "weekly_summary"   → generate + write weekly report
          "changelog"        → generate + write CHANGELOG.md
          "district_report"  → params["district"] required
        """
        task_type = task.get("type", "")
        params = task.get("params", {})

        try:
            if task_type == "weekly_summary":
                content = self.generate_weekly_summary()
                ok = self.write_document(content, "weekly_summary")
                if ok:
                    self._memory.store(
                        event_type="doc_generated",
                        content="Weekly summary generated",
                        tags=["documentation", "weekly_summary"],
                        source="doc_generator",
                    )
                    self._memory.store_chain(
                        situation="weekly_summary",
                        goal_ids=["documentation"],
                        steps=["fetch_events", "fetch_hp", "llm_generate", "write_document"],
                        action="generate_weekly_summary",
                        outcome="weekly summary written",
                        reward=0.85,
                    )
                    self.award_points(50, "weekly summary generated")
                    return {"status": "ok", "doc_type": "weekly_summary"}
                else:
                    self.deduct_points(30, "weekly summary write failed")
                    return {"status": "error", "reason": "write failed"}

            elif task_type in ("changelog", "generate_changelog"):
                # 2026-07-29 KNOWN_ISSUES: the real production
                # /documentation/changelog route (core/api/routers/
                # documentation.py) and DISTRICT_TASK_MAP (core/city/
                # governor.py) both dispatch task_type="generate_changelog",
                # which never matched this handler's original bare
                # "changelog" check — every changelog request, routed
                # correctly or not, fell to the `else` branch's "unknown
                # task type" error. Accept both spellings rather than
                # picking one canonical name and risking missing another
                # caller elsewhere that already relies on the other.
                content = self.generate_changelog()
                ok = self.write_document(content, "changelog")
                if ok:
                    self._memory.store(
                        event_type="doc_generated",
                        content="CHANGELOG generated from git log",
                        tags=["documentation", "changelog"],
                        source="doc_generator",
                    )
                    self.award_points(50, "changelog generated")
                    return {"status": "ok", "doc_type": "changelog"}
                else:
                    self.deduct_points(30, "changelog write failed")
                    return {"status": "error", "reason": "write failed"}

            elif task_type == "district_report":
                district = params.get("district", "")
                if not district:
                    return {"status": "error", "reason": "district required"}
                content = self.generate_district_report(district)
                ok = self.write_document(content, f"district_report_{district}")
                if ok:
                    self._memory.store(
                        event_type="doc_generated",
                        content=f"District report generated for {district}",
                        tags=["documentation", "district_report", district],
                        source="doc_generator",
                    )
                    self.award_points(50, f"district report: {district}")
                    return {"status": "ok", "doc_type": f"district_report_{district}"}
                else:
                    self.deduct_points(30, f"district report write failed: {district}")
                    return {"status": "error", "reason": "write failed"}

            else:
                return {"status": "error", "reason": f"unknown task type: {task_type}"}

        except Exception as e:
            logger.error(f"[VECTOR][doc_generator] run error: {e}")
            self.deduct_points(30, f"run exception: {e}")
            return {"status": "error", "reason": str(e)}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][doc_generator] run_forever — event-driven")
        while self.is_alive:
            try:
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"[VECTOR][doc_generator] tick: {e}")
        logger.warning("[VECTOR][doc_generator] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile

    agent = DocGenerator()
    assert agent.health_points == 500, f"expected 500 HP, got {agent.health_points}"

    # Smoke test: changelog (always works — falls back to plain text if no git)
    changelog = agent.generate_changelog()
    assert isinstance(changelog, str) and len(changelog) > 0, "changelog empty"
    assert "CHANGELOG" in changelog.upper(), "missing CHANGELOG header"

    # Smoke test: district_report with no data (graceful fallback)
    report = agent.generate_district_report("nonexistent_district")
    assert isinstance(report, str) and "District Report" in report

    print(f"✅ doc_generator.py OK HP={agent.health_points}")
