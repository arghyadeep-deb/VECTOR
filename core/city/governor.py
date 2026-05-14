import sys
import asyncio
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


# RED-tier task types that require LLM Council review before execution.
# Mirrors the RED permission tier in critical_rules.md.
_COUNCIL_TASK_TYPES: frozenset[str] = frozenset({
    "push_github",
    "deploy_production",
    "delete_files",
    "financial_transaction",
    "send_email",
    "execute_code",
    "overwrite_note_personal",
    "create_pr",
})

DISTRICT_TASK_MAP: dict[str, str] = {
    "code": "coding",
    "git": "coding",
    "git_status": "coding",
    "review": "coding",
    "bug": "coding",
    "refactor": "coding",
    "architect": "coding",
    "calendar": "time_calendar",
    "schedule": "time_calendar",
    "deadline": "time_calendar",
    "kiit": "time_calendar",
    "attendance": "time_calendar",
    "check_attendance": "time_calendar",
    "class": "time_calendar",
    "message": "communications",
    "email": "communications",
    "notify": "communications",
    "whatsapp": "communications",
    "vectorcode_comms": "communications",
    "vectorcode": "communications",
    "search": "research",
    "research": "research",
    "paper": "research",
    "search_arxiv": "research",
    "search_web": "research",
    "daily_digest": "research",
    "news": "research",
    "find": "research",
    "threat": "security",
    "malware": "security",
    "security": "security",
    "scan": "security",
    "memory": "memory_curator",
    "remember": "memory_curator",
    "recall": "memory_curator",
    "consolidate": "memory_curator",
    "vote": "governance",
    "council": "governance",
    "decision": "governance",
    "health": "health",
    "sleep": "health",
    "fatigue": "health",
    "check_fatigue": "health",
    "finance": "finance",
    "budget": "finance",
    "money": "finance",
    "monthly_report": "finance",
    "learn": "learning",
    "video": "learning",
    "course": "learning",
    "daily_review": "reflection",
    "reflect": "reflection",
    "journal": "reflection",
    "project": "projects",
    "deadline_check": "projects",
    "progress": "projects",
    "image": "content",
    "generate_image": "content",
    "comfyui": "content",
    "script": "content",
}


class Governor:
    """
    VECTOR's task orchestrator. Routes tasks to the right district agent.
    RULE 9 — HP wired to actual outcomes: success → +50 HP, failure → -30 HP.
    Never crashes — every exception caught internally.
    """

    def __init__(self):
        self._registry = None
        self._memory = None
        self._active_tasks: dict[str, dict] = {}
        logger.info("[VECTOR][governor] initialized")

    def _get_registry(self):
        if self._registry is None:
            from core.city.agent_registry import get_registry
            self._registry = get_registry()
        return self._registry

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    def route_task(self, task_type: str) -> str:
        """Determine which district should handle this task type.
        First tries keyword matching (fast, free). Falls back to LLM classification."""
        task_lower = task_type.lower()
        for keyword, district in DISTRICT_TASK_MAP.items():
            if keyword in task_lower:
                return district
        # LLM fallback for natural language task types
        return self._llm_classify(task_type)

    def _llm_classify(self, task_type: str) -> str:
        """Use vector-ambient (fast, local) to classify task into a district."""
        try:
            from core.inference.ollama_safe import chat
            from core.config import CONFIG
            districts = list(set(DISTRICT_TASK_MAP.values()))
            prompt = (
                f"Classify this task into exactly one district name from this list: {districts}\n"
                f"Task: {task_type}\n"
                "Reply with only the district name, nothing else."
            )
            result = chat(
                model=CONFIG["models"]["ambient"],
                messages=[{"role": "user", "content": prompt}],
                timeout=5.0,
            ).strip().lower()
            # Validate the response is a known district
            if result in districts:
                logger.info(f"[VECTOR][governor] LLM classified '{task_type}' → {result}")
                return result
        except Exception as e:
            logger.warning(f"[VECTOR][governor] LLM classify failed: {e}")
        logger.warning(f"[VECTOR][governor] unknown task '{task_type}' → defaulting to research")
        return "research"

    async def dispatch(self, task: dict) -> dict:
        """
        Dispatch task to appropriate district agent.
        RULE 9 — HP wired to actual outcome after every dispatch.
        """
        task_id = f"task_{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"
        task_type = task.get("type", "unknown")
        district = task.get("district") or self.route_task(task_type)

        logger.info(f"[VECTOR][governor] dispatch {task_id} → {district} ({task_type})")
        self._active_tasks[task_id] = {
            "task": task,
            "district": district,
            "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        result: dict = {}
        agent = None

        try:
            agents = self._get_registry().get_by_district(district)

            if not agents:
                logger.warning(f"[VECTOR][governor] no agents in {district}")
                result = {"status": "no_agents", "district": district}
            else:
                agent = max(agents, key=lambda a: a.health_points)

                if hasattr(agent, "run"):
                    result = await agent.run(task)
                else:
                    result = {"status": "stub", "agent": agent.name}

            # RULE 9 — HP wired to actual task outcomes
            if agent is not None:
                if result.get("status") == "ok":
                    agent.award_points(50, "task_completed_by_governor")
                elif result.get("status") in ("error", "failed"):
                    agent.deduct_points(30, "task_failed_by_governor")

            self._get_memory().store(
                event_type="governor_dispatch",
                content=f"type={task_type} district={district} status={result.get('status')}",
                tags=["governor", district, task_type],
                source="governor",
            )

        except Exception as e:
            logger.error(f"[VECTOR][governor] dispatch error {task_id}: {e}")
            if agent is not None:
                agent.deduct_points(30, "exception_during_task")
            result = {"status": "error", "error": str(e)}
        finally:
            self._active_tasks.pop(task_id, None)

        return {**result, "task_id": task_id, "district": district}

    def get_active_tasks(self) -> list[dict]:
        return list(self._active_tasks.values())

    def get_district_summary(self) -> dict:
        """Agent count and avg HP per district."""
        reg = self._get_registry()
        summary = {}
        for district, count in reg.count_by_district().items():
            agents = reg.get_by_district(district)
            if agents:
                avg_hp = sum(a.health_points for a in agents) / len(agents)
                summary[district] = {"agents": count, "avg_hp": round(avg_hp)}
        return summary


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from core.city.agent_base import AgentBase
    from core.city.agent_registry import get_registry

    reg = get_registry()
    a = AgentBase("gov_test_001", "CodeBot", "coding")
    reg.register(a)

    gov = Governor()
    route = gov.route_task("review my git code")
    result = asyncio.run(gov.dispatch({"type": "code_review", "file": "core/main.py"}))
    summary = gov.get_district_summary()

    ok = route == "coding" and "task_id" in result and "coding" in summary
    print(
        f"✅ governor OK — route={route}, "
        f"dispatch status={result.get('status')}, districts={len(summary)}"
        if ok else "❌ FAILED"
    )
