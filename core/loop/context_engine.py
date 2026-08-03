import sys
import datetime
import os
import threading
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG

_SENSE_CACHE: dict = {
    "screen_summary": "",
    "presence": "unknown",
}
_SENSE_CACHE_LOCK = threading.RLock()


def get_sense_cache_snapshot() -> dict:
    """Return a stable copy of the shared sensing context."""
    with _SENSE_CACHE_LOCK:
        return dict(_SENSE_CACHE)


def update_sense_cache(screen_summary="", presence="unknown", **extra) -> None:
    """Update shared sensing context for all ContextEngine instances."""
    if isinstance(screen_summary, dict):
        data = dict(screen_summary)
    else:
        data = {"screen_summary": screen_summary, "presence": presence}
    data.update(extra)
    if "screen_summary" in data:
        data["screen_summary"] = str(data.get("screen_summary") or "")[:300]
    if not data.get("presence"):
        data["presence"] = "unknown"
    with _SENSE_CACHE_LOCK:
        _SENSE_CACHE.update(data)


class ContextEngine:
    """
    Builds VECTOR's world state. session_hydration_prompt() MUST be called before every LLM call.
    RULE 1 — Skip this = VECTOR has amnesia every session. Never skip.
    """

    def __init__(self):
        self._memory = None
        self._goals = None
        # Sense cache: populated by autonomous_loop._sense_tick() or update_sense_cache().
        # Keys written by FaceDetector: face.detected, face.identity, face.fatigue
        # Keys written by ScreenObserver: screen_summary
        self._sense_cache = _SENSE_CACHE
        logger.info("[VECTOR][context_engine] initialized")

    def update_sense_cache(self, data: dict) -> None:
        """Update the sense cache with latest sensing results.

        Called by autonomous_loop._sense_tick() after every FaceDetector /
        ScreenObserver pass. May also be called directly in tests.
        Expected keys (all optional):
          face.detected (bool), face.identity (str), face.fatigue (float)
          screen_summary (str)
        """
        update_sense_cache(data)

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    def _get_goals(self):
        if self._goals is None:
            from core.brain.goal_system import GoalSystem
            self._goals = GoalSystem()
        return self._goals

    def get_world_state(self, query: str | None = None) -> dict:
        """Gather current world state across 9 domains."""
        now = datetime.datetime.now()
        mem = self._get_memory()

        recent_episodes = []
        try:
            if query:
                recent_episodes = mem.search_semantic(query, top_k=5)
            else:
                recent_episodes = mem.recall("", limit=5)
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] episode recall failed: {e}")

        goal_summary = ""
        try:
            goal_summary = self._get_goals().get_goal_summary()
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] goal summary failed: {e}")

        mem_stats = {}
        try:
            mem_stats = mem.get_stats()
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] mem stats failed: {e}")

        # --- Presence / face detection from sense cache ---
        sense_cache = get_sense_cache_snapshot()
        face_data: dict = sense_cache.get("face", {})
        if face_data.get("detected"):
            presence = "present"
        elif "detected" in face_data:
            # detected key exists but is False — camera ran, no face found
            presence = "absent"
        else:
            presence = sense_cache.get("presence", "unknown")

        owner_identity: str = face_data.get("identity", "")
        fatigue_score: float = float(face_data.get("fatigue", 0.0))

        # Task B.2 — ADB-phone observe source (written by _sense_tick when
        # sensing.phone_enabled is on; gracefully {} when off/no device).
        phone_data: dict = sense_cache.get("phone", {})

        return {
            "timestamp": now.isoformat(),
            "time_of_day": self._time_of_day(now),
            "day_of_week": now.strftime("%A"),
            "owner": CONFIG["owner_name"],
            "env": CONFIG["env"],
            "version": CONFIG["version"],
            "active_model": CONFIG["models"].get(
                CONFIG["model_router"]["conversation"], "vector-focus"
            ),
            "recent_episodes": [ep.get("content", "")[:80] for ep in recent_episodes[:3]],
            "goal_summary": goal_summary,
            "memory_stats": mem_stats,
            "loop_status": "running",
            # Presence fields — sourced from FaceDetector via _sense_cache
            "presence": presence,
            "owner_identity": owner_identity,
            "fatigue_score": fatigue_score,
            "screen_summary": sense_cache.get("screen_summary", ""),
            "phone_connected": bool(phone_data.get("connected", False)),
            "phone_notification_count": int(phone_data.get("notification_count", 0)),
        }

    def _person_context_line(self, person_id: str, topic: str = "current task") -> str:
        try:
            from core.brain.person_model import PersonModel
            pm = PersonModel()
            try:
                model = pm.get_model(person_id)
                if not model:
                    return ""
                style = pm.infer_communication_style(person_id)
                stance = pm.predict_response(person_id, topic)
                recent = model.get("recent_interactions", [])[:3]
                recent_topics = [
                    str(item.get("summary", "")).replace("\n", " ")[:60]
                    for item in recent
                    if item.get("summary")
                ]
                style_str = " ".join(f"{k}={v}" for k, v in style.items())
                trust = float(model.get("trust_score", pm.get_trust(person_id)))
                return (
                    f"About {model.get('name', 'person')}: "
                    f"trust={trust:.2f} "
                    f"{style_str} "
                    f"expected_stance={stance} "
                    f"recent_topics={recent_topics}"
                )
            finally:
                close = getattr(pm, "close", None)
                if callable(close):
                    close()
        except Exception as e:
            logger.debug("[VECTOR][context_engine] person context unavailable: {}", e)
            return ""

    def session_hydration_prompt(self, extra_context: dict | None = None) -> str:
        """
        RULE 1 — Call this before EVERY LLM call.
        Returns a context block to prepend to the LLM message.
        """
        try:
            query = (extra_context or {}).get("query")
            state = self.get_world_state(query=query)
        except Exception as e:
            logger.error(f"[VECTOR][context_engine] world state failed: {e}")
            state = {
                "timestamp": datetime.datetime.now().isoformat(),
                "owner": CONFIG["owner_name"],
                "env": CONFIG["env"],
                "version": CONFIG["version"],
                "time_of_day": "unknown",
                "day_of_week": "unknown",
                "goal_summary": "",
                "recent_episodes": [],
            }

        lines = [
            f"[SESSION CONTEXT — {state['timestamp']}]",
            f"Owner: {state['owner']} | Env: {state['env']} | VECTOR v{state['version']}",
            f"Time: {state['time_of_day']} ({state['day_of_week']})",
        ]

        if state.get("presence") and state["presence"] not in ("unknown", ""):
            identity = state.get("owner_identity", "")
            fatigue = state.get("fatigue_score", 0.0)
            presence_line = f"Presence: {state['presence']}"
            if identity:
                presence_line += f" ({identity})"
            if fatigue > 0.0:
                presence_line += f" fatigue={fatigue:.2f}"
            lines.append(presence_line)

        if state.get("screen_summary"):
            lines.append(f"Screen: {state['screen_summary'][:120]}")

        if state.get("goal_summary"):
            lines.append(f"Active goals: {state['goal_summary']}")

        # Owner doctrine (brain vault Blueprint/(C) Doctrine.md) — rides every LLM call
        try:
            from core.brain.blueprint_doctrine import get_doctrine_line
            doctrine = get_doctrine_line()
            if doctrine:
                lines.append(doctrine)
        except Exception:
            logger.warning("[VECTOR][context_engine] doctrine unavailable, continuing")

        if state.get("recent_episodes"):
            episodes_str = " | ".join(
                e for e in state["recent_episodes"] if e
            )[:200]
            if episodes_str:
                lines.append(f"Recent context: {episodes_str}")

        # 2026-07-30 audit fix (Phase 2 — memory subsystem): the knowledge
        # graph (core/memory/knowledge_graph.py — entities/relations built up
        # via entity_add/knowledge_add/relation_add, see
        # districts/memory_curator/consolidation_bot.py::_kg_write()) was
        # only ever readable through the explicit "knowledge_query" task_type
        # — a normal conversational turn ("what do I use for X", "tell me
        # about my car") never surfaced anything VECTOR had actually learned
        # into the graph, even though session_hydration_prompt() is called
        # before every single LLM call (RULE 1) and is exactly where that
        # context belongs. Fixed by doing a cheap, best-effort KG lookup
        # keyed off proper-noun-shaped words in the query — same LIKE-based
        # substring match kg.query() already does for the explicit
        # knowledge_query path, just triggered automatically here too.
        # Never raises; empty/no-match is silently skipped like every other
        # optional line above.
        if query:
            kg_line = self._knowledge_graph_line(str(query))
            if kg_line:
                lines.append(kg_line)

        person_id = (extra_context or {}).get("person_id")
        if person_id:
            about = self._person_context_line(
                str(person_id),
                str((extra_context or {}).get("task", "current task")),
            )
            if about:
                lines.append(about)

        if extra_context:
            for k, v in extra_context.items():
                if k == "person_id":
                    continue
                lines.append(f"{k}: {v}")

        # Available commands (from brain vault)
        try:
            from vectorcode.src.command_registry import get_command_registry
            reg = get_command_registry()
            cmd_names = list(reg.load().keys())[:15]
            if cmd_names:
                lines.append(f"Brain commands: {', '.join('/' + c for c in cmd_names)}")
        except Exception:
            logger.warning("[VECTOR] silent swallow")
            pass

        lines.append("[END SESSION CONTEXT]")
        return "\n".join(lines)

    def _knowledge_graph_line(self, query: str) -> str:
        """Best-effort, read-only knowledge-graph lookup for session
        hydration (see session_hydration_prompt() call site above).
        Extracts proper-noun-shaped candidate terms from the free-text
        query and checks the graph for anything matching — same
        substring-LIKE match KnowledgeGraph.query() already does for the
        explicit knowledge_query task_type. Returns "" on no match or any
        failure (never raises, never blocks an LLM call on this)."""
        try:
            import re as _re
            candidates = _re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", query)
            # Dedup while preserving order; cap how many lookups we do —
            # this must stay cheap since it runs before every LLM call.
            seen: list[str] = []
            for c in candidates:
                if c not in seen:
                    seen.append(c)
            if not seen:
                return ""
            from core.memory.knowledge_graph import get_knowledge_graph
            kg = get_knowledge_graph()
            facts: list[str] = []
            for term in seen[:3]:
                result = kg.query(term, max_results=3)
                for e in result.entities[:2]:
                    fact = f"{e.name} ({e.entity_type})"
                    if fact not in facts:
                        facts.append(fact)
                for r in result.relations[:2]:
                    fact = f"{r.subject} {r.predicate} {r.obj}"
                    if fact not in facts:
                        facts.append(fact)
                if len(facts) >= 4:
                    break
            if not facts:
                return ""
            return "Known facts: " + "; ".join(facts[:4])[:250]
        except Exception as e:
            logger.debug("[VECTOR][context_engine] knowledge graph lookup skipped: {}", e)
            return ""

    async def get_vault_context(self, query: str = "") -> str:
        """Query LightRAG graph for vault context to feed session hydration."""
        if os.environ.get("VECTOR_OBSIDIAN_RAG_QUERY") != "1":
            return ""
        try:
            from core.memory.obsidian_sync import ObsidianSync
            sync = ObsidianSync()
            if hasattr(sync, "query"):
                return await sync.query(query) or ""
            return ""
        except Exception as e:
            logger.warning("[VECTOR][context] get_vault_context failed: {}", e)
            return ""

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate: 1 token ≈ 4 chars for English text."""
        return max(1, len(text) // 4)

    def get_context_token_count(self) -> int:
        """Estimate current session context size in tokens."""
        try:
            prompt = self.session_hydration_prompt()
            return self.estimate_tokens(prompt)
        except Exception:
            return 0

    def is_context_near_limit(self, limit: int = 32000) -> bool:
        """Return True if context is within 80% of the token limit."""
        return self.get_context_token_count() >= int(limit * 0.8)

    def _time_of_day(self, now: datetime.datetime) -> str:
        h = now.hour
        if 5 <= h < 9:
            return "early morning"
        elif 9 <= h < 12:
            return "morning"
        elif 12 <= h < 14:
            return "midday"
        elif 14 <= h < 18:
            return "afternoon"
        elif 18 <= h < 22:
            return "evening"
        elif 22 <= h or h < 1:
            return "night"
        else:
            return "late night"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    engine = ContextEngine()
    state = engine.get_world_state()
    prompt = engine.session_hydration_prompt({"task": "smoke test"})
    ok = (
        "SESSION CONTEXT" in prompt
        and "Arghyadeep" in prompt
        and "[END SESSION CONTEXT]" in prompt
        and len(state) >= 8
    )
    print(
        f"✅ context_engine OK — {len(state)} domains, prompt={len(prompt)} chars"
        if ok else "❌ FAILED"
    )
