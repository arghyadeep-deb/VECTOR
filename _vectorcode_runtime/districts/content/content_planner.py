"""Daily content planner (sub-project D).

`build_wedge_content_plan()` (script -> schedule_post) had no production caller, so the real
post queue never received a real job. This plans ONE such plan per day; the autonomous loop
executes it (both steps already permission-classified) and the existing 09:00
`job_content_scheduler` publishes it only after the owner approves (RED `content_publish`).
Nothing here publishes or touches the gateway.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger

GOAL_ID = "g_first_revenue"  # Blueprint: content ops is the Wave-1 revenue path
_WORK_TOPIC = "what VECTOR did today"
# Truthful, VECTOR-about-VECTOR topics (growth engine rule: truthful claims only).
_SHOWCASE_TOPICS = (
    "How VECTOR's Permission Gateway keeps an autonomous AI agent safe",
    "VECTOR's agent city: agents earn HP, die, and pass lessons to their successors",
    "Running a personal AI assistant fully on one laptop with local models",
    "Why VECTOR asks the owner before anything leaves the machine",
    "How VECTOR learns from its own decisions with a policy memory",
    "Inside VECTOR's LLM council: three perspectives, one verdict",
    "How VECTOR routes a chat message to the right district agent",
)


def pick_topic(now: datetime, has_real_work: bool) -> str:
    """Real work today wins; otherwise a capability showcase rotating by day of year."""
    if has_real_work:
        return _WORK_TOPIC
    return _SHOWCASE_TOPICS[now.timetuple().tm_yday % len(_SHOWCASE_TOPICS)]


def _configured_platforms(publisher: Any) -> list[str]:
    out = []
    if getattr(publisher, "_devto_key", ""):
        out.append("devto")
    if getattr(publisher, "_hashnode_token", "") and getattr(publisher, "_hashnode_pub_id", ""):
        out.append("hashnode")
    if getattr(publisher, "_medium_token", ""):
        out.append("medium")
    return out


def _has_real_work() -> bool:
    try:
        from core.memory.episodic import EpisodicMemory

        return bool(EpisodicMemory().recall("task completed", limit=3))
    except Exception:
        return False


def _has_active_content_plan(store: Any) -> bool:
    return any(str(getattr(p, "objective", "")).startswith("Wedge content pipeline")
               for p in store.active_plans())


async def plan_daily_content(store: Any = None, publisher: Any = None, now: datetime | None = None) -> dict:
    """Create at most one active content plan. Never raises (the loop must not die)."""
    try:
        from core.runtime.plans import build_wedge_content_plan, get_plan_store

        store = store or get_plan_store()
        if _has_active_content_plan(store):
            return {"status": "skipped", "reason": "an active content plan already exists"}
        if publisher is None:
            from districts.content.blog_publisher import BlogPublisher

            publisher = BlogPublisher()
        platforms = _configured_platforms(publisher)
        if not platforms:
            return {"status": "skipped", "reason": "no publishing platform configured"}
        topic = pick_topic(now or datetime.now(tz=timezone.utc), _has_real_work())
        plan = build_wedge_content_plan(GOAL_ID, topic, platforms=platforms)
        store.add(plan)
        logger.info("[VECTOR][content-plan] planned '{}' -> {} ({})", topic, platforms, plan.id)
        return {"status": "planned", "plan_id": plan.id, "topic": topic, "platforms": platforms}
    except Exception as exc:
        logger.warning("[VECTOR][content-plan] failed: {}", exc)
        return {"status": "error", "error": str(exc)}


if __name__ == "__main__":
    import asyncio

    print(asyncio.run(plan_daily_content()))
