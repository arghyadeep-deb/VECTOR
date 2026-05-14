import sys
import json
import uuid
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


PRESEEDED_GOALS = [
    {
        "id": "g_kiit_attendance",
        "title": "Maintain KIIT attendance above 75%",
        "horizon": "LONG",
        "priority": 10,
        "status": "active",
        "progress": 0.0,
        "tags": ["kiit", "academic"],
    },
    {
        "id": "g_karpathy_30",
        "title": "Complete Karpathy playlist — 30 min/day",
        "horizon": "MID",
        "priority": 9,
        "status": "active",
        "progress": 0.0,
        "tags": ["learning", "ml", "karpathy"],
    },
    {
        "id": "g_vector_phase1",
        "title": "Complete VECTOR Phase 1 — 8 core districts",
        "horizon": "MID",
        "priority": 10,
        "status": "active",
        "progress": 0.25,
        "tags": ["vector", "coding", "build"],
    },
    {
        "id": "g_placement_prep",
        "title": "KIIT placement preparation — DSA + System Design",
        "horizon": "LONG",
        "priority": 8,
        "status": "active",
        "progress": 0.0,
        "tags": ["placement", "dsa", "interview"],
    },
    {
        "id": "g_daily_commit",
        "title": "Commit code every single day — no exceptions",
        "horizon": "SHORT",
        "priority": 7,
        "status": "active",
        "progress": 0.0,
        "tags": ["git", "habit", "coding"],
    },
]


class GoalSystem:
    """
    3-horizon goal management: LONG (months), MID (weeks), SHORT (days).
    RULE 6 — planner.py reads generate_immediate_actions(). Not world state. Goals.
    Pre-seeded with Arghyadeep's real goals on first run.
    """

    def __init__(self):
        self._goals: list[dict] = []
        self._memory = None
        self._load_or_seed()
        logger.info(f"[VECTOR][goal_system] initialized — {len(self._goals)} goals")

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    def _load_or_seed(self):
        """Load goals from semantic memory. Seed with pre-seeded goals if empty."""
        try:
            mem = self._get_memory()
            stored = mem.recall_fact("goals_v1")
            if stored and stored.get("value"):
                self._goals = json.loads(stored["value"])
                logger.info(f"[VECTOR][goal_system] loaded {len(self._goals)} goals from memory")
                return
        except Exception as e:
            logger.warning(f"[VECTOR][goal_system] load failed, using seeds: {e}")

        self._goals = [g.copy() for g in PRESEEDED_GOALS]
        self._persist()
        logger.info(f"[VECTOR][goal_system] seeded {len(self._goals)} goals")

    def _persist(self):
        try:
            mem = self._get_memory()
            mem.remember("goals_v1", json.dumps(self._goals), "goals", 1.0)
        except Exception as e:
            logger.error(f"[VECTOR][goal_system] persist failed: {e}")

    def get_active_goals(self, horizon: str | None = None) -> list[dict]:
        """Return active goals sorted by priority. Filter by horizon if provided."""
        goals = [g for g in self._goals if g.get("status") == "active"]
        if horizon:
            goals = [g for g in goals if g.get("horizon") == horizon.upper()]
        return sorted(goals, key=lambda g: g.get("priority", 0), reverse=True)

    def generate_immediate_actions(self, limit: int = 5) -> list[dict]:
        """
        RULE 6 — Planner reads this. Not world state. Not user commands. Goals.
        Returns SHORT-horizon actions and kickstarters for stalled LONG/MID goals.
        """
        actions = []

        for goal in self.get_active_goals("SHORT"):
            actions.append({
                "goal_id": goal["id"],
                "title": goal["title"],
                "action": "progress_goal",
                "urgency": "high",
                "source": "SHORT_goal",
                "tags": goal.get("tags", []),
            })

        for goal in self.get_active_goals():
            if goal.get("progress", 0) < 1.0 and goal["horizon"] in ("LONG", "MID"):
                actions.append({
                    "goal_id": goal["id"],
                    "title": f"Start: {goal['title']}",
                    "action": "kickstart_goal",
                    "urgency": "medium",
                    "source": f"{goal['horizon']}_unstarter",
                    "tags": goal.get("tags", []),
                })

        return actions[:limit]

    def update_goal_progress(self, goal_id: str, progress: float, note: str = "") -> bool:
        """Update progress (0.0-1.0). Auto-completes at 1.0."""
        for goal in self._goals:
            if goal["id"] == goal_id:
                goal["progress"] = max(0.0, min(1.0, progress))
                if progress >= 1.0:
                    goal["status"] = "completed"
                    logger.info(f"[VECTOR][goal_system] GOAL COMPLETED: {goal['title']}")
                goal["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                if note:
                    goal["last_note"] = note
                self._persist()
                return True
        logger.warning(f"[VECTOR][goal_system] goal not found: {goal_id}")
        return False

    def add_goal(
        self,
        title: str,
        horizon: str,
        priority: int = 5,
        tags: list[str] | None = None,
    ) -> str:
        """Add a new goal. Returns goal_id."""
        goal_id = f"g_{uuid.uuid4().hex[:8]}"
        self._goals.append({
            "id": goal_id,
            "title": title,
            "horizon": horizon.upper(),
            "priority": priority,
            "status": "active",
            "progress": 0.0,
            "tags": tags or [],
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        self._persist()
        logger.info(f"[VECTOR][goal_system] new goal: {goal_id} — {title}")
        return goal_id

    def complete_goal(self, goal_id: str) -> bool:
        return self.update_goal_progress(goal_id, 1.0)

    def get_goal_summary(self) -> str:
        """Formatted goal summary for session hydration context."""
        lines = []
        for h in ("SHORT", "MID", "LONG"):
            goals = self.get_active_goals(h)
            if goals:
                titles = ", ".join(g["title"][:40] for g in goals[:2])
                lines.append(f"{h}: {titles}")
        return " | ".join(lines) if lines else "No active goals"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    gs = GoalSystem()
    active = gs.get_active_goals()
    actions = gs.generate_immediate_actions()
    gs.update_goal_progress("g_daily_commit", 0.5, "committed today")
    summary = gs.get_goal_summary()
    new_id = gs.add_goal("Learn Bengali by August", "MID", priority=6, tags=["language"])
    ok = (
        len(active) >= 5
        and len(actions) >= 1
        and "VECTOR" in summary
        and new_id.startswith("g_")
    )
    print(
        f"✅ goal_system OK — {len(active)} goals, {len(actions)} actions"
        if ok else "❌ FAILED"
    )
