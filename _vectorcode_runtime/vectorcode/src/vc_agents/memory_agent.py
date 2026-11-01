"""
MemoryAgent — wraps vectorcode's memory_manager/memory_provider for session memory.

Manages short-term session context within vectorcode's execution environment.
Bridges vectorcode's memory stack (memory_manager.py + memory_provider.py) with
VECTOR's episodic memory (core/memory/episodic.py) for long-term persistence.
"""
from __future__ import annotations

import datetime


from loguru import logger


class MemoryAgent:
    """
    Session memory manager for vectorcode's agent runtime.

    Short-term: vectorcode's MemoryManager (in-process, per-session)
    Long-term:  VECTOR's EpisodicMemory (SQLite, persists across sessions)

    Use add() for adding facts, search() for retrieval, flush() to persist
    session memory to VECTOR's long-term store.
    """

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self._vc_manager = None
        self._episodic = None
        self._session_facts: list[dict] = []
        logger.info("[VECTOR][vc_memory] initialized session={}", session_id)

    def _get_vc_manager(self):
        if self._vc_manager is None:
            try:
                from vectorcode.src.agent.memory_manager import MemoryManager
                self._vc_manager = MemoryManager()
            except Exception as e:
                logger.debug("[VECTOR][vc_memory] vc MemoryManager unavailable: {}", e)
        return self._vc_manager

    def _get_episodic(self):
        if self._episodic is None:
            from core.memory.episodic import EpisodicMemory
            self._episodic = EpisodicMemory()
        return self._episodic

    def add(self, content: str, tags: list[str] = None, source: str = "vectorcode") -> None:
        """Add a fact to session memory."""
        fact = {
            "content": content,
            "tags": tags or [],
            "source": source,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._session_facts.append(fact)
        # Also push to vectorcode's MemoryManager if available
        mgr = self._get_vc_manager()
        if mgr:
            try:
                mgr.add(content, metadata={"session_id": self.session_id, "source": source})
            except Exception:
                logger.opt(exception=True).debug("[VECTOR] suppressed exception")

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Search session + long-term memory for relevant facts."""
        results = []

        # Search vectorcode's MemoryManager first (most recent session context)
        mgr = self._get_vc_manager()
        if mgr:
            try:
                vc_results = mgr.search(query, limit=limit)
                results.extend(vc_results or [])
            except Exception:
                logger.opt(exception=True).debug("[VECTOR] suppressed exception")

        # Supplement with VECTOR's episodic memory
        try:
            episodic_results = self._get_episodic().recall(query, limit=limit)
            for r in episodic_results:
                if not any(r.get("content") == x.get("content") for x in results):
                    results.append(r)
        except Exception as e:
            logger.debug("[VECTOR][vc_memory] episodic recall failed: {}", e)

        # Fall back to session facts if no results
        if not results:
            query_lower = query.lower()
            for fact in reversed(self._session_facts):
                if query_lower in fact.get("content", "").lower():
                    results.append(fact)
                if len(results) >= limit:
                    break

        return results[:limit]

    def flush(self, event_type: str = "vectorcode_session") -> int:
        """Persist all session facts to VECTOR's long-term episodic memory."""
        flushed = 0
        episodic = self._get_episodic()
        for fact in self._session_facts:
            try:
                episodic.store(
                    event_type=event_type,
                    content=fact["content"],
                    tags=fact.get("tags", []) + ["vectorcode", self.session_id],
                    source=fact.get("source", "vectorcode"),
                )
                flushed += 1
            except Exception as e:
                logger.debug("[VECTOR][vc_memory] flush failed: {}", e)
        self._session_facts.clear()
        logger.info("[VECTOR][vc_memory] flushed {} facts to episodic memory", flushed)
        return flushed

    def get_session_context(self, max_chars: int = 2000) -> str:
        """Return recent session facts as a context string for LLM injection."""
        lines = []
        total = 0
        for fact in reversed(self._session_facts[-20:]):
            line = f"- [{fact['source']}] {fact['content']}"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)
        return "\n".join(reversed(lines)) if lines else ""


if __name__ == "__main__":
    agent = MemoryAgent("test_session")
    agent.add("VECTOR has 37 districts", tags=["architecture"])
    agent.add("Arghyadeep is KIIT CSE 2023-27", tags=["user"])
    agent.add("RTX 5070 Ti 12GB VRAM", tags=["hardware"])
    results = agent.search("districts", limit=3)
    print(f"[OK] search: {len(results)} results")
    ctx = agent.get_session_context()
    print(f"[OK] context: {len(ctx)} chars")
    flushed = agent.flush()
    print(f"[OK] flush: {flushed} facts persisted")
    print("memory_agent.py OK")
