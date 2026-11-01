"""Unified memory facade — ONE entry point to VECTOR's 5 core memory stores.

Why this exists
---------------
Agents previously had to know the exact module path for each store
(`from core.memory.episodic import EpisodicMemory`, `...policy import
PolicyMemory`, etc.), which is the "which memory do I call?" fragmentation the
audit flagged. This facade gives a single, discoverable entry:

    from core.memory.unified import get_memory
    mem = get_memory()
    mem.episodic.store(...)
    mem.policy.get_score(...)
    mem.reasoning.store_chain(...)
    mem.counterfactual.should_avoid(...)
    mem.semantic.remember(...)

Safety / scope
--------------
- Purely ADDITIVE. The existing per-class imports (EpisodicMemory is used in
  ~176 files) keep working unchanged — nothing is rewritten.
- The 5 sacred tables (episodic_memory, semantic_memory, policy_memory,
  reasoning_chains, agent_history) are NOT touched; this only routes to the
  existing store classes.
- Each store is lazy-loaded on first access, so importing the facade is cheap
  and a store that fails to construct never breaks the others.
- Optional pluggable backends under `vectorcode/src/plugins/memory/*` and
  district-specific stores are intentionally NOT collapsed in here — they are a
  separate plugin layer, not the core.
"""

from loguru import logger

__all__ = ["UnifiedMemory", "get_memory"]


class UnifiedMemory:
    """Lazy facade over the 5 core memory stores. Access via :func:`get_memory`."""

    def __init__(self) -> None:
        self._episodic = None
        self._semantic = None
        self._policy = None
        self._reasoning = None
        self._counterfactual = None

    @property
    def episodic(self):
        if self._episodic is None:
            from core.memory.episodic import EpisodicMemory
            self._episodic = EpisodicMemory()
        return self._episodic

    @property
    def semantic(self):
        if self._semantic is None:
            from core.memory.semantic import SemanticMemory
            self._semantic = SemanticMemory()
        return self._semantic

    @property
    def policy(self):
        if self._policy is None:
            from core.memory.policy import PolicyMemory
            self._policy = PolicyMemory()
        return self._policy

    @property
    def reasoning(self):
        if self._reasoning is None:
            from core.memory.reasoning_memory import ReasoningMemory
            self._reasoning = ReasoningMemory()
        return self._reasoning

    @property
    def counterfactual(self):
        if self._counterfactual is None:
            from core.memory.counterfactual import CounterfactualMemory
            self._counterfactual = CounterfactualMemory()
        return self._counterfactual


_INSTANCE: UnifiedMemory | None = None


def get_memory() -> UnifiedMemory:
    """Return the process-wide UnifiedMemory facade (singleton)."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = UnifiedMemory()
        logger.debug("[VECTOR][memory] unified facade initialised")
    return _INSTANCE


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    m = get_memory()
    # Touch each store — confirms the facade wires to real, constructable classes.
    assert m.episodic is not None
    assert m.semantic is not None
    assert m.policy is not None
    assert m.reasoning is not None
    assert m.counterfactual is not None
    assert get_memory() is m  # singleton
    print("✅ unified.py OK — 5 core stores reachable via one facade")
