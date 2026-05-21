"""
Autopilot — automatically chains district agents based on task output.

Ported from ruflo's ruflo-autopilot plugin concept.
Autopilot reads the output of one district agent, classifies what comes
next, and dispatches the follow-on task — enabling multi-step autonomous
pipelines without manual chaining.

Example chain:
  research → [autopilot] → coding → [autopilot] → qa → [autopilot] → done
"""
import sys
import asyncio
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory

# Chaining rules: task_result_keyword → next district + task_type
_CHAIN_RULES: list[tuple[list[str], str, str]] = [
    # If output mentions code/implementation → route to coding
    (["implement", "write code", "build", "create function", "python"], "coding", "code"),
    # If output mentions testing → route to qa
    (["test", "verify", "check", "validate", "qa"], "qa", "qa_check"),
    # If output mentions research → route to research
    (["research", "find papers", "search for", "look up"], "research", "research"),
    # If output mentions security → route to security
    (["security", "vulnerability", "threat", "risk"], "security", "threat"),
    # If output mentions deployment → route to ops
    (["deploy", "launch", "production", "server"], "ops", "deploy"),
    # If output mentions writing/docs → route to documentation
    (["document", "write docs", "readme", "api reference"], "documentation", "write_docs"),
    # If output mentions marketing → route to marketing
    (["publish", "post", "social media", "blog", "seo"], "marketing", "social_media"),
    # If output mentions finance → route to finance
    (["budget", "cost", "revenue", "expense"], "finance", "finance"),
]

_STOP_SIGNALS = [
    "done", "complete", "finished", "no further action",
    "task complete", "pipeline done", "stop"
]


class Autopilot(AgentBase):
    """
    Autonomous agent chainer. Reads task output, decides what district
    handles it next, and dispatches automatically. Implements the
    NEXUS Dev↔QA loop pattern and ruflo's autopilot plugin concept.

    Max chain depth enforced to prevent infinite loops.
    All chaining decisions logged to episodic memory.
    """

    MAX_CHAIN_DEPTH = 5  # NEXUS: max 3 retries; autopilot: max 5 hops

    def __init__(self):
        super().__init__(agent_id="autopilot_001", name="Autopilot", district="governance")
        self._memory: EpisodicMemory | None = None
        self._governor = None
        logger.info("[VECTOR][autopilot] initialized (max_depth={})", self.MAX_CHAIN_DEPTH)

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_governor(self):
        if self._governor is None:
            from core.city.governor import Governor
            self._governor = Governor()
        return self._governor

    def classify_next_step(self, task_output: str | dict) -> dict | None:
        """Analyse task output and decide what district/task comes next.

        Returns {district, task_type, reason} or None if pipeline should stop.
        """
        text = task_output if isinstance(task_output, str) else str(task_output)
        text_lower = text.lower()

        # Check stop signals first
        if any(s in text_lower for s in _STOP_SIGNALS):
            return None

        # Match chaining rules
        for keywords, district, task_type in _CHAIN_RULES:
            if any(kw in text_lower for kw in keywords):
                return {
                    "district": district,
                    "task_type": task_type,
                    "reason": f"output contains '{[k for k in keywords if k in text_lower][0]}'",
                }

        return None  # No matching rule → stop chain

    async def run_chain(self, initial_task: dict, chain_depth: int = 0) -> dict:
        """
        Execute a task and auto-chain to the next district if needed.
        Recursive up to MAX_CHAIN_DEPTH.
        """
        if chain_depth >= self.MAX_CHAIN_DEPTH:
            logger.warning("[VECTOR][autopilot] max chain depth {} reached — stopping", self.MAX_CHAIN_DEPTH)
            return {"status": "ok", "chain_stopped": "max_depth_reached", "depth": chain_depth}

        gov = self._get_governor()
        task_type = initial_task.get("type", "unknown")
        logger.info("[VECTOR][autopilot] chain depth={} dispatching {}", chain_depth, task_type)

        # Execute current task
        result = await gov.dispatch(initial_task)

        self._get_memory().store(
            event_type="autopilot_chain_step",
            content=f"depth={chain_depth} task={task_type} status={result.get('status')}",
            tags=["governance", "autopilot", f"depth_{chain_depth}"],
            source="autopilot",
        )

        if result.get("status") not in ("ok", "stub"):
            logger.warning("[VECTOR][autopilot] task failed at depth {} — stopping", chain_depth)
            return result

        # Classify what comes next
        next_step = self.classify_next_step(result)
        if next_step is None:
            logger.info("[VECTOR][autopilot] chain complete at depth {}", chain_depth)
            self.award_points(30 + chain_depth * 5, f"autopilot_chain_depth_{chain_depth}")
            return {**result, "chain_depth": chain_depth, "chain_complete": True}

        logger.info(
            "[VECTOR][autopilot] depth={} → chaining to {} ({}) — reason: {}",
            chain_depth, next_step["district"], next_step["task_type"], next_step["reason"]
        )

        # Build follow-on task
        follow_on = {
            "type": next_step["task_type"],
            "district": next_step["district"],
            "context": str(result)[:500],
            "autopilot_depth": chain_depth + 1,
        }
        return await self.run_chain(follow_on, chain_depth + 1)

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "chain")
        try:
            if task_type == "classify":
                output = task.get("output", "")
                next_step = self.classify_next_step(output)
                self.award_points(10, "next_step_classified")
                return {"status": "ok", "next_step": next_step}

            else:  # chain — run full autopilot chain
                result = await self.run_chain(task)
                return {"status": "ok", **result}

        except Exception as e:
            logger.error("[VECTOR][autopilot] {}", e)
            self.deduct_points(30, "autopilot_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = Autopilot()
        # Test classification
        cases = [
            "You should implement this in Python using FastAPI",
            "Run tests to verify the implementation works",
            "Research papers on transformer architecture",
            "Pipeline is done, no further action needed",
            "Deploy to production server",
        ]
        for case in cases:
            next_step = agent.classify_next_step(case)
            label = f"→ {next_step['district']}/{next_step['task_type']}" if next_step else "→ STOP"
            print(f"[OK] '{case[:45]}...' {label}")

        result = await agent.run({"type": "classify", "output": "implement this feature in Python"})
        print(f"[OK] run classify: next={result.get('next_step')}")
        print("autopilot.py OK")

    asyncio.run(_smoke())
