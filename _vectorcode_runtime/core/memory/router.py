"""MemoryRouter — classify-then-dispatch orchestration in front of
UnifiedMemory (core.memory.unified).

Why this exists
----------------
UnifiedMemory (core.memory.unified) gives one discoverable entry point to
VECTOR's stores (`mem.episodic`, `mem.semantic`, `mem.policy`,
`mem.reasoning`, `mem.counterfactual`) — but it's a passive facade. Every
call site still has to know, on its own, which store a given write or read
actually belongs in. That's the "which memory do I call?" fragmentation
unified.py's own docstring already names as the underlying problem it was
only a partial fix for.

MemoryRouter closes that gap: callers hand it a write (free text + optional
structural metadata) or a read (a query + optional task hint) and it decides
where that belongs, then dispatches through UnifiedMemory. Nothing in
unified.py or the underlying store classes is touched — this sits strictly
in front of them.

Classification strategy: deterministic first, LLM fallback only for
genuinely ambiguous free text
----------------------------------------------------------------------------
Most memory events are NOT ambiguous — they're structurally unambiguous by
construction. An action that just executed with a reward attached is
obviously a policy-memory write; a plan the user just rejected is obviously
counterfactual; a person/entity being described is obviously entity memory.
For all of these a keyword/shape rule is correct with certainty — asking an
LLM to guess at something already known from context can only add noise,
not accuracy. This mirrors the existing pattern in
core/api/routers/commands.py: a deterministic keyword fast-path first,
falling through to an LLM router (classify_chat_intent()) only when the
fast-path genuinely can't decide.

An LLM call (local Ollama, qwen3:14b, allow_cloud=False — zero cost, matches
this project's ₹0-forever ethos) is used ONLY when no deterministic rule
fires: genuinely ambiguous free text with no structural hint at all. On any
LLM failure or unparseable output, the safe default is EPISODIC — VECTOR's
"foundational, catch-everything" store — so a write is never silently
dropped.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

_CLASSIFIER_MODEL = "qwen3:14b"
_CLASSIFIER_TIMEOUT_S = 15.0

# ── Write categories ─────────────────────────────────────────────────────
CAT_POLICY = "policy"
CAT_COUNTERFACTUAL = "counterfactual"
CAT_ENTITY = "entity"
CAT_REASONING = "reasoning"
CAT_SEMANTIC = "semantic"
CAT_EPISODIC = "episodic"

_ALL_WRITE_CATEGORIES = frozenset({
    CAT_POLICY, CAT_COUNTERFACTUAL, CAT_ENTITY, CAT_REASONING, CAT_SEMANTIC, CAT_EPISODIC,
})

_REJECTION_PATTERNS = re.compile(
    r"\b(decided not to|rejected the (plan|idea|proposal)|instead of .+ (we|i) could have|"
    r"what if (i|we) had|chose not to|ruled out|abandoned the (plan|approach|idea))\b",
    re.IGNORECASE,
)

_ENTITY_PATTERNS = re.compile(
    r"^\s*([A-Z][\w'.-]+(?:\s[A-Z][\w'.-]+){0,2})\s+(is|works at|is a|is my|is the)\b",
)

_FACT_STATEMENT_PATTERNS = re.compile(
    r"\b(remember that|note that|for the record|my \w+ is|please remember)\b",
    re.IGNORECASE,
)

# semantic.search() / reasoning_memory.search_chains() / knowledge_graph.query()
# all do a plain `column LIKE '%term%'` — none tokenize or rank. Handing them a
# whole natural-language question ("who is Arghyadeep") never substring-matches
# a short stored value ("Arghyadeep"), so route_read() strips the leading
# question phrasing first and searches on what's left. (episodic.recall() is
# the one exception — it's real FTS5 and doesn't need this.)
_SEARCH_TERM_STRIP = re.compile(
    r"\b(who (?:is|was)|what do (?:i|you) know about|"
    r"have i (?:done|tried) this before|what worked last time(?: with| for| on)?|"
    r"past (?:attempt|reasoning)(?:s)?(?: at| for| with)?|what'?s my|my \w+ is|"
    r"do you remember|how (?:good|well) (?:is|did|does)|should i)\b[:\s]*",
    re.IGNORECASE,
)


@dataclass
class RouteResult:
    category: str
    method: str  # "deterministic" | "llm" | "fallback"
    detail: str = ""
    store_result: Any = None
    extra: dict = field(default_factory=dict)


class MemoryRouter:
    """Classify-then-dispatch front end for UnifiedMemory."""

    def __init__(self) -> None:
        from core.memory.unified import get_memory
        self._mem = get_memory()

    # ── WRITE ────────────────────────────────────────────────────────────

    def route_write(
        self,
        content: str,
        *,
        event_type: str = "note",
        metadata: "dict | None" = None,
        source: str = "router",
    ) -> RouteResult:
        """Classify an incoming piece of information and write it to the
        store it actually belongs in.

        `metadata` carries structural hints from a caller that already knows
        more than the raw text does (e.g. a district agent that just ran an
        action and has a real reward score) — these are checked FIRST and
        are authoritative when present, since they're ground truth, not a
        guess. Only when nothing in metadata or the text itself gives an
        unambiguous signal does this fall through to the LLM classifier.
        """
        meta = metadata or {}
        content = (content or "").strip()
        if not content:
            return RouteResult(CAT_EPISODIC, "fallback", "empty content, nothing to route")

        # 1. Explicit action+reward -> policy (RL-style action/situation score).
        if meta.get("action_type") and meta.get("reward") is not None:
            return self._write_policy(content, meta)

        # 2. Explicit or textual rejection/counterfactual signal.
        if meta.get("rejected") or meta.get("counterfactual") or _REJECTION_PATTERNS.search(content):
            return self._write_counterfactual(content, meta)

        # 3. Explicit reasoning chain shape (steps + action + outcome).
        if meta.get("chain") or (meta.get("steps") and meta.get("action") and meta.get("outcome")):
            return self._write_reasoning(content, meta)

        # 4. Explicit entity hint, or "Name is/works at/..." shape in the text.
        if meta.get("entity") or _ENTITY_PATTERNS.match(content):
            return self._write_entity(content, meta)

        # 5. Explicit goal-shaped or fact-shaped statement -> semantic.
        if meta.get("goal_update") or meta.get("fact") or meta.get("key") or _FACT_STATEMENT_PATTERNS.search(content):
            return self._write_semantic(content, meta)

        # 6. Nothing structural fired — genuinely ambiguous free text.
        #    Ask the local judge to pick a category; any failure -> episodic.
        category = self._llm_classify_write(content)
        if category == CAT_POLICY:
            return self._write_policy(content, meta, method="llm")
        if category == CAT_COUNTERFACTUAL:
            return self._write_counterfactual(content, meta, method="llm")
        if category == CAT_ENTITY:
            return self._write_entity(content, meta, method="llm")
        if category == CAT_REASONING:
            return self._write_reasoning(content, meta, method="llm")
        if category == CAT_SEMANTIC:
            return self._write_semantic(content, meta, method="llm")
        return self._write_episodic(content, event_type, meta, source, method="llm" if category else "fallback")

    # ── per-category write dispatchers ──────────────────────────────────
    # `method` records WHY this category was chosen ("deterministic" when a
    # rule in route_write() fired directly, "llm" when the local classifier
    # picked it after nothing structural matched) — it must be threaded
    # through, not hardcoded, or RouteResult.method lies about llm-routed
    # writes.

    def _write_policy(self, content: str, meta: dict, method: str = "deterministic") -> RouteResult:
        try:
            situation_hash = meta.get("situation_hash") or self._mem.policy.make_situation_hash(
                meta.get("situation", content)
            )
            result = self._mem.policy.update_from_outcome(
                meta["action_type"], situation_hash, float(meta["reward"])
            )
            return RouteResult(CAT_POLICY, method, "action+reward -> policy", result)
        except Exception as e:
            logger.warning(f"[VECTOR][memory_router] policy write failed, falling back to episodic: {e}")
            return self._write_episodic(content, "policy_write_failed", meta, "router")

    def _write_counterfactual(self, content: str, meta: dict, method: str = "deterministic") -> RouteResult:
        try:
            decision_id = meta.get("decision_id") or str(uuid.uuid4())
            result = self._mem.counterfactual.record_rejection(
                decision_id=decision_id,
                proposal=meta.get("rejected_action") or content,
                reason=meta.get("reason", "") or content,
                context=meta.get("context"),
            )
            return RouteResult(CAT_COUNTERFACTUAL, method, "rejection language -> counterfactual", result)
        except Exception as e:
            logger.warning(f"[VECTOR][memory_router] counterfactual write failed, falling back to episodic: {e}")
            return self._write_episodic(content, "rejected_decision", meta, "router")

    def _write_reasoning(self, content: str, meta: dict, method: str = "deterministic") -> RouteResult:
        try:
            chain_id = self._mem.reasoning.store_chain(
                situation=meta.get("situation", content),
                goal_ids=meta.get("goal_ids", []),
                steps=meta.get("steps", []),
                action=meta.get("action", ""),
                outcome=meta.get("outcome", ""),
                reward=float(meta.get("reward", 0.5)),
            )
            return RouteResult(CAT_REASONING, method, "thought-action-outcome shape -> reasoning", chain_id)
        except Exception as e:
            logger.warning(f"[VECTOR][memory_router] reasoning write failed, falling back to episodic: {e}")
            return self._write_episodic(content, "reasoning_write_failed", meta, "router")

    def _write_entity(self, content: str, meta: dict, method: str = "deterministic") -> RouteResult:
        try:
            from core.memory.knowledge_graph import get_knowledge_graph
            kg = get_knowledge_graph()
            name = meta.get("entity") or (_ENTITY_PATTERNS.match(content) or [None, content.split()[0]])[1]
            kg.add_entity(name, meta.get("entity_type", "unspecified"), {"source_text": content[:300]})
            return RouteResult(CAT_ENTITY, method, "entity-shaped statement -> knowledge graph", name)
        except Exception as e:
            logger.warning(f"[VECTOR][memory_router] entity write failed, falling back to episodic: {e}")
            return self._write_episodic(content, "entity_write_failed", meta, "router")

    def _write_semantic(self, content: str, meta: dict, method: str = "deterministic") -> RouteResult:
        try:
            key = meta.get("key") or self._derive_semantic_key(content)
            # SemanticMemory.store() returns None (upsert, not a success flag) —
            # the key itself is the useful "what did we write" result for callers.
            self._mem.semantic.store(
                key, meta.get("value", content), meta.get("category", "general"),
                float(meta.get("confidence", 0.6)),
            )
            return RouteResult(CAT_SEMANTIC, method, "fact/goal-shaped statement -> semantic", key)
        except Exception as e:
            logger.warning(f"[VECTOR][memory_router] semantic write failed, falling back to episodic: {e}")
            return self._write_episodic(content, "semantic_write_failed", meta, "router")

    def _write_episodic(self, content: str, event_type: str, meta: dict, source: str, method: str = "fallback") -> RouteResult:
        try:
            event_id = self._mem.episodic.store(
                event_type=event_type, content=content,
                tags=meta.get("tags"), context=meta.get("context"), source=source,
            )
            return RouteResult(CAT_EPISODIC, method, "no structural or LLM signal -> episodic (safe default)", event_id)
        except Exception as e:
            logger.error(f"[VECTOR][memory_router] episodic write failed (last-resort store): {e}")
            return RouteResult(CAT_EPISODIC, method, f"write failed entirely: {e}", None)

    @staticmethod
    def _derive_semantic_key(content: str) -> str:
        import hashlib
        return "fact_" + hashlib.sha256(content.encode()).hexdigest()[:12]

    # ── READ ─────────────────────────────────────────────────────────────

    def route_read(self, query: str, *, task_hint: "str | None" = None, limit: int = 5) -> RouteResult:
        """Classify an incoming query and read from the store(s) it actually
        belongs in. Falls back to episodic full-text recall whenever the
        chosen store returns nothing, since episodic is the broadest net."""
        query = (query or "").strip()
        if not query:
            return RouteResult(CAT_EPISODIC, "fallback", "empty query", [])

        hint = (task_hint or "").lower()
        category = None
        method = "deterministic"

        if hint in _ALL_WRITE_CATEGORIES:
            category = hint
        elif re.search(r"\bwho (is|was)\b|\bwhat do (i|you) know about\b", query, re.IGNORECASE):
            category = CAT_ENTITY
        elif re.search(r"\bhave i (done|tried) this before\b|\bwhat worked last time\b|\bpast (attempt|reasoning)\b", query, re.IGNORECASE):
            category = CAT_REASONING
        elif re.search(r"\bwhat'?s my\b|\bmy \w+ is\b|\bdo you remember\b", query, re.IGNORECASE):
            category = CAT_SEMANTIC
        elif re.search(r"\bhow (good|well) (is|did|does)\b|\bshould i\b.+\bagain\b", query, re.IGNORECASE):
            category = CAT_POLICY
        else:
            category = self._llm_classify_read(query)
            method = "llm" if category else "fallback"

        result = self._dispatch_read(category, query, limit)
        if not result and category != CAT_EPISODIC:
            # Broadest net as a fallback — a wrong category guess shouldn't
            # mean "found nothing" when episodic might still have it.
            fallback = self._mem.episodic.recall(query, limit=limit)
            if fallback:
                return RouteResult(CAT_EPISODIC, "fallback", f"{category} returned nothing; episodic fallback hit", fallback)
        return RouteResult(category or CAT_EPISODIC, method, f"routed to {category}", result)

    def _dispatch_read(self, category: "str | None", query: str, limit: int) -> Any:
        try:
            term = self._extract_search_term(query)
            if category == CAT_ENTITY:
                from core.memory.knowledge_graph import get_knowledge_graph
                result = get_knowledge_graph().query(term, max_results=max(limit, 20))
                # GraphQueryResult has no __bool__/__len__, so an empty hit would
                # otherwise look "truthy" to route_read()'s episodic-fallback check.
                return result if result.total > 0 else None
            if category == CAT_REASONING:
                return self._mem.reasoning.search_chains(term, limit=limit)
            if category == CAT_SEMANTIC:
                exact = self._mem.semantic.get(self._derive_semantic_key(query))
                if exact:
                    return exact
                return self._mem.semantic.search(term, limit=limit)
            if category == CAT_POLICY:
                action_type = self._extract_action_type(query)
                situation_hash = self._mem.policy.make_situation_hash(query)
                return self._mem.policy.get_score(action_type, situation_hash)
        except Exception as e:
            logger.debug(f"[VECTOR][memory_router] {category} read failed, will fall through to episodic: {e}")
            return None
        return self._mem.episodic.recall(query, limit=limit)

    @staticmethod
    def _extract_search_term(query: str) -> str:
        cleaned = _SEARCH_TERM_STRIP.sub("", query).strip(" ?.!:")
        return cleaned or query

    @staticmethod
    def _extract_action_type(query: str) -> str:
        """Best-effort action_type extraction for a policy-category read.

        VECTOR's real action_type strings are consistently snake_case (e.g.
        'check_weather', 'set_reminder' — see commands.py's intent actions),
        so pull the first snake_case token out of the natural-language
        question instead of scoring against the raw sentence, which would
        never match anything written by _write_policy(). Falls back to the
        lowercased query if no such token is present."""
        m = re.search(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", query.lower())
        return m.group(0) if m else query.strip().lower()

    # ── LLM fallback (only reached when no deterministic rule fired) ───────

    def _llm_classify_write(self, content: str) -> "str | None":
        return self._llm_classify(
            content,
            "Classify what KIND of memory this text is, for a personal AI "
            "assistant's memory system. Reply with EXACTLY ONE WORD, no "
            "punctuation, no explanation: "
            "'policy' (an action's outcome/success worth scoring), "
            "'counterfactual' (a rejected plan or 'what if' scenario), "
            "'reasoning' (a multi-step thought process worth reusing later), "
            "'entity' (a fact about a specific named person/place/thing), "
            "'semantic' (a general fact, preference, or goal), or "
            "'episodic' (a plain event/experience log, use this if unsure).",
        )

    def _llm_classify_read(self, query: str) -> "str | None":
        return self._llm_classify(
            query,
            "Classify what KIND of memory would answer this question, for a "
            "personal AI assistant's memory system. Reply with EXACTLY ONE "
            "WORD, no punctuation, no explanation: "
            "'entity' (asking about a specific named person/place/thing), "
            "'reasoning' (asking about a past decision/approach), "
            "'semantic' (asking about a stored fact/preference/goal), "
            "'policy' (asking how well an action tends to work), or "
            "'episodic' (a general question about a past event, use this if unsure).",
        )

    def _llm_classify(self, text: str, instruction: str) -> "str | None":
        try:
            from core.inference.vectorcode_llm import chat
            reply = chat(
                model=_CLASSIFIER_MODEL,
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": text[:500]},
                ],
                timeout=_CLASSIFIER_TIMEOUT_S,
                provider="ollama",
                allow_cloud=False,
                temperature=0.0,
                domain="memory_routing",
            )
            if not reply:
                return None
            word = re.sub(r"[^a-z]", "", reply.strip().lower().split()[0]) if reply.strip() else ""
            return word if word in _ALL_WRITE_CATEGORIES else None
        except Exception as e:
            logger.debug(f"[VECTOR][memory_router] LLM classification unavailable, defaulting to episodic: {e}")
            return None


_INSTANCE: "MemoryRouter | None" = None


def get_router() -> MemoryRouter:
    """Process-wide MemoryRouter singleton."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MemoryRouter()
        logger.debug("[VECTOR][memory_router] initialised")
    return _INSTANCE


if __name__ == "__main__":
    # real test, no mocks — deterministic-path smoke test (no LLM/network needed)
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    r = get_router()

    w1 = r.route_write("Executed check_weather with reward", event_type="action",
                        metadata={"action_type": "check_weather", "reward": 0.9})
    assert w1.category == CAT_POLICY, w1

    w2 = r.route_write("Decided not to push the untested branch to prod")
    assert w2.category == CAT_COUNTERFACTUAL, w2

    w3 = r.route_write("Arghyadeep is the owner of VECTOR")
    assert w3.category == CAT_ENTITY, w3

    w4 = r.route_write("Remember that I prefer dark mode in all apps")
    assert w4.category == CAT_SEMANTIC, w4

    w5 = r.route_write("VECTOR API restarted cleanly at 3am", event_type="ops")
    assert w5.category in _ALL_WRITE_CATEGORIES, w5  # ambiguous -> LLM or episodic fallback, either is fine here

    print(f"✅ router.py OK — deterministic write classification verified "
          f"(policy={w1.category}, counterfactual={w2.category}, entity={w3.category}, semantic={w4.category})")
