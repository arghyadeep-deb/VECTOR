import sys
import os
import uuid
import asyncio
import datetime
import hashlib
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger


class ConsolidationBot(AgentBase):
    """
    Compresses old episodic memory into semantic summaries.
    Writes daily reflections to Obsidian. Runs once per day.
    """

    CONSOLIDATION_DAYS = 30
    REFLECTION_HOURS = 24
    # Forgetting horizon: raw episodes older than this are pruned AFTER they have
    # been summarized into semantic_memory + mem0. 3x the consolidation window so
    # nothing is forgotten before it has been consolidated.
    RETENTION_DAYS = 90
    # Minimum gap between event-triggered consolidations.  A research burst that
    # stores 20 episodes would otherwise fire 20 full consolidation passes (each
    # fetching up to 200 episodes, making an LLM call, writing a semantic_memory
    # row, and running the forgetting pass).  6 h keeps the first pass and
    # suppresses the rest; run_forever()'s 24 h cycle still runs weekly on top.
    CONSOLIDATION_COOLDOWN_HOURS = 6

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ConsolidationBot",
            district="memory_curator",
            generation=generation,
        )
        self.capabilities = ["consolidate", "entity_add", "knowledge_query", "memory", "memory_curator", "memory_stored", "recall", "relation_add", "remember", "save_note", "store_findings", "who"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        mem0_enabled = os.getenv("VECTOR_MEM0_ENABLE") == "1"
        # mem0 episodic layer — self-hosted OSS only (RULE 11, never MemoryClient)
        try:
            if not mem0_enabled:
                raise ImportError("mem0 disabled; set VECTOR_MEM0_ENABLE=1 to enable")
            from mem0 import Memory as _Mem0
            self._mem0 = _Mem0()
            logger.info("[VECTOR][consolidation_bot] mem0 episodic layer active")
        except ImportError:
            self._mem0 = None
            logger.info("[VECTOR][consolidation_bot] mem0 not installed — EpisodicMemory only")
        except Exception as _e:
            self._mem0 = None
            logger.warning(f"[VECTOR][consolidation_bot] mem0 init failed: {_e}")
        # Concurrency guard: 3 sources can trigger consolidation simultaneously
        # (handle_event on every memory_stored/research_complete, run_forever
        # weekly Monday loop, autonomous_loop 2AM Monday reflect). Without this
        # lock they all fetch the same episodes and write key
        # 'consolidation:{today}' — last writer wins via ON CONFLICT DO UPDATE,
        # silently discarding the others.
        self._consolidation_lock = asyncio.Lock()
        self._last_consolidation_date: datetime.date | None = None
        self._last_consolidation_time: datetime.datetime | None = None
        # Set when the last consolidation pass could not persist its summary
        # (remember() returned False) so run() can report it instead of "ok".
        self._consolidation_write_failed: bool = False
        logger.info(f"[VECTOR][consolidation_bot] ready gen={generation} hp={self.health_points}")
        # Phase 2B: subscribe to memory events
        self.subscribe_to("memory_stored")
        self.subscribe_to("research_complete")

    async def handle_event(self, event: dict) -> dict:
        """Phase 2B: Run consolidation when memory fills up.

        Rate-limited: skips if fewer than CONSOLIDATION_COOLDOWN_HOURS have
        elapsed since the last event-triggered consolidation.  Without this,
        a research burst that stores 20 episodes fires 20 full consolidation
        passes (each fetching 200 episodes, making an LLM call, and running
        the forgetting pass).  consolidate_old_episodes() has its own date +
        lock guard as defense-in-depth for scheduled/concurrent callers.
        """
        await super().handle_event(event)
        et = event.get("event_type", "")
        if et in ("memory_stored", "research_complete"):
            now = datetime.datetime.now(datetime.timezone.utc)
            if (
                self._last_consolidation_time is not None
                and (now - self._last_consolidation_time)
                < datetime.timedelta(hours=self.CONSOLIDATION_COOLDOWN_HOURS)
            ):
                logger.debug(
                    f"[VECTOR][consolidation_bot] consolidation cooldown active "
                    f"({self.CONSOLIDATION_COOLDOWN_HOURS}h), skipping: {et}"
                )
                return {"status": "skipped", "agent": self.name, "event": et, "reason": "cooldown"}
            try:
                logger.info(f"[VECTOR][consolidation_bot] event-triggered consolidation: {et}")
                await self.run({"type": "consolidate", "params": {"source": "event"}})
                self._last_consolidation_time = now
            except Exception as e:
                logger.warning("[VECTOR][consolidation_bot] handle_event failed: {}", e)
        return {"status": "handled", "agent": self.name, "event": et}

    # ── mem0 helper ───────────────────────────────────────────────────────────

    def _store_to_mem0(self, content: str, role: str = "assistant") -> None:
        """Store content to mem0 episodic layer alongside EpisodicMemory."""
        if not self._mem0:
            return
        try:
            self._mem0.add(
                [{"role": role, "content": content}],
                user_id="vector",
                metadata={"source": "consolidation_bot"},
            )
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] mem0 store failed: {e}")

    # ── Episode helpers ────────────────────────────────────────────────────────

    def _fetch_old_episodes(self, days_old: int) -> list[dict]:
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_old)
        ).isoformat()
        # KNOWN_ISSUES #21: a cached self._memory.conn never sees
        # get_db_connection()'s self-healing reopen-if-closed logic — see
        # pattern_finder.py's _fetch_window() for the full explanation.
        # get_temp_cursor() always resolves a live connection.
        from core.memory.episodic import get_temp_cursor
        with get_temp_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM episodic_memory WHERE timestamp < ? ORDER BY timestamp ASC LIMIT 200",
                (cutoff,),
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _fetch_recent_episodes(self, hours: int) -> list[dict]:
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        ).isoformat()
        # KNOWN_ISSUES #21 — see _fetch_old_episodes() above.
        from core.memory.episodic import get_temp_cursor
        with get_temp_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM episodic_memory WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 100",
                (cutoff,),
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    # ── Core tasks ─────────────────────────────────────────────────────────────

    async def consolidate_old_episodes(self) -> int:
        """Compress episodes older than CONSOLIDATION_DAYS into semantic_memory summaries."""
        # Non-blocking dedup: if another coroutine is already consolidating, or
        # we already consolidated today, skip silently rather than queuing.
        if self._last_consolidation_date == datetime.date.today():
            logger.debug("[VECTOR][consolidation_bot] consolidation already done today — skipping")
            return 0
        if self._consolidation_lock.locked():
            logger.debug("[VECTOR][consolidation_bot] consolidation already in progress — skipping")
            return 0
        async with self._consolidation_lock:
            # Double-check after acquiring lock (another coroutine may have
            # finished while we waited — though with locked() guard above we
            # shouldn't have waited at all).
            if self._last_consolidation_date == datetime.date.today():
                return 0
            return await self._consolidate_old_episodes_impl()

    async def _consolidate_old_episodes_impl(self) -> int:
        """Inner consolidation logic — called with _consolidation_lock held."""
        episodes = self._fetch_old_episodes(self.CONSOLIDATION_DAYS)
        if not episodes:
            logger.info("[VECTOR][consolidation_bot] no old episodes to consolidate")
            return 0

        batch_text = "\n".join(
            f"[{ep['timestamp'][:10]}] {ep['event_type']}: {ep['content'][:120]}"
            for ep in episodes[:50]
        )
        hydration = self._context.session_hydration_prompt()  # RULE 1

        try:
            if os.getenv("VECTOR_MEMORY_CURATOR_LLM") != "1":
                raise RuntimeError("memory curator LLM disabled; set VECTOR_MEMORY_CURATOR_LLM=1 to enable")
            from core.inference.vectorcode_llm import achat
            summary = await achat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": hydration},
                    {
                        "role": "user",
                        "content": (
                            "You are VECTOR's ConsolidationBot. Compress these episodic memories "
                            "into 3-5 key semantic facts. Return as bullet points.\n\n"
                            + batch_text
                        ),
                    },
                ],
                timeout=60.0,
            )
            if not summary:
                raise RuntimeError("empty model response")
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] LLM unavailable: {e}")
            first_ts = episodes[0]["timestamp"][:10]
            last_ts = episodes[-1]["timestamp"][:10]
            summary = f"Compressed {len(episodes)} episodes ({first_ts} to {last_ts})"

        # Placeholder detection: if the summary is the fallback placeholder (not
        # real LLM output), flag low confidence so downstream consumers know
        # this is metadata, not actual semantic content. Without this, the
        # placeholder gets stored at confidence=0.8 alongside real facts, and
        # after prune_old_episodes() deletes the raw episodes (RETENTION_DAYS=90),
        # only the placeholder survives as the permanent "summary" — irreversibly
        # losing the actual episodic content.
        _is_placeholder = summary.startswith("Compressed") and "episodes" in summary
        _confidence = 0.3 if _is_placeholder else 0.8
        if _is_placeholder:
            logger.warning(
                f"[VECTOR][consolidation_bot] storing placeholder summary "
                f"(confidence={_confidence}) — LLM inference failed, raw episodes "
                f"will be pruned in {self.RETENTION_DAYS}d without real consolidation"
            )

        key = f"consolidation:{datetime.date.today().isoformat()}"
        # remember() swallows write errors and returns False (it never raises).
        # If the summary was not persisted we must NOT go on to prune the raw
        # episodes it was meant to replace, nor report success.
        self._consolidation_write_failed = False
        if self._memory.remember(key, summary, category="consolidation", confidence=_confidence) is False:
            self._consolidation_write_failed = True
            logger.error(
                "[VECTOR][consolidation_bot] summary write failed for {} — "
                "raw episodes kept, no pruning, consolidation not recorded", key,
            )
            return 0
        self._store_to_mem0(f"Memory consolidation [{key}]: {summary[:400]}")
        self._memory.store_chain(
            situation="memory_consolidation",
            goal_ids=["maintain_memory"],
            steps=["fetch_old_episodes", "summarize_llm", "store_semantic"],
            action="consolidate",
            outcome=f"compressed {len(episodes)} episodes",
            reward=0.8,
        )
        self.award_points(30, f"consolidated {len(episodes)} old episodes")
        logger.info(f"[VECTOR][consolidation_bot] consolidated {len(episodes)} episodes → {key}")

        # Forgetting (roadmap #7): now that old episodes are summarized into
        # semantic_memory + mem0, prune the redundant raw rows past the retention
        # horizon so the episodic DB stays bounded in 24/7 operation.
        try:
            forgotten = self._memory.prune_old_episodes(self.RETENTION_DAYS)
            if forgotten:
                self.award_points(10, f"forgot {forgotten} stale raw episodes")
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] forgetting pass skipped: {e}")

        try:
            from core.engine.memory_tree.tree_builder import get_shared_tree
            tree_forgotten = get_shared_tree().prune_old_chunks(self.RETENTION_DAYS)
            if tree_forgotten:
                self.award_points(5, f"forgot {tree_forgotten} stale tree chunks")
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] memory_tree forgetting pass skipped: {e}")

        self._last_consolidation_date = datetime.date.today()
        self._last_consolidation_time = datetime.datetime.now(datetime.timezone.utc)
        return len(episodes)

    async def write_daily_reflection(self) -> bool:
        """Summarize last 24h of episodic memory → write to Obsidian Reflections/."""
        # Same concurrency guard as consolidate_old_episodes — the 2AM reflect
        # in autonomous_loop and run_forever's Monday loop can both call this
        # simultaneously. Uses the same lock so a concurrent consolidation
        # blocks reflection too (they write overlapping date-keyed state).
        if self._consolidation_lock.locked():
            logger.debug("[VECTOR][consolidation_bot] reflection skipped — consolidation in progress")
            return False
        async with self._consolidation_lock:
            return await self._write_daily_reflection_impl()

    async def _write_daily_reflection_impl(self) -> bool:
        """Inner reflection logic — called with _consolidation_lock held."""
        episodes = self._fetch_recent_episodes(hours=self.REFLECTION_HOURS)
        date_str = datetime.date.today().isoformat()
        title = f"Daily Reflection — {date_str}"

        if not episodes:
            logger.info("[VECTOR][consolidation_bot] no recent episodes — writing minimal reflection")
            reflection = "No significant events logged in the last 24 hours."
        else:
            episodes_text = "\n".join(
                f"- [{ep['event_type']}] {ep['content'][:100]}"
                for ep in episodes[:30]
            )
            hydration = self._context.session_hydration_prompt()  # RULE 1

            try:
                if os.getenv("VECTOR_MEMORY_CURATOR_LLM") != "1":
                    raise RuntimeError("memory curator LLM disabled; set VECTOR_MEMORY_CURATOR_LLM=1 to enable")
                from core.inference.vectorcode_llm import achat
                reflection = await achat(
                    model=CONFIG["models"]["reasoning"],
                    messages=[
                        {"role": "system", "content": hydration},
                        {
                            "role": "user",
                            "content": (
                                "Write a concise daily reflection for VECTOR based on these events. "
                                "2-3 paragraphs: what happened, what was learned, what to improve.\n\n"
                                + episodes_text
                            ),
                        },
                    ],
                    timeout=60.0,
                )
                if not reflection:
                    raise RuntimeError("empty model response")
            except Exception as e:
                logger.warning(f"[VECTOR][consolidation_bot] LLM unavailable: {e}")
                reflection = (
                    f"Daily summary: {len(episodes)} events logged.\n\n" + episodes_text[:800]
                )

        try:
            self._obsidian.write_note(
                title=title,
                content=reflection,
                folder="Reflections",
                tags=["reflection", "daily", "auto", "vector"],
            )
            self._store_to_mem0(f"Daily reflection [{date_str}]: {reflection[:600]}")
            self._memory.store_chain(
                situation="daily_reflection",
                goal_ids=["self_awareness"],
                steps=["fetch_recent_episodes", "generate_reflection", "write_vault"],
                action="write_daily_reflection",
                outcome=f"reflection written: {title}",
                reward=0.9,
            )
            self.award_points(50, "daily reflection written to vault")
            logger.info(f"[VECTOR][consolidation_bot] reflection written: {title}")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][consolidation_bot] write_note failed: {e}")
            self.deduct_points(20, "reflection write failed")
            return False

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        task = task or {}
        task_type = task.get("type", "")
        if task_type == "store_findings":
            return self._store_findings(task.get("params") or {})
        # classify_chat_intent()'s LLM classifier isn't limited to a fixed
        # vocabulary for non-RED-tier task types (governor.py: "Otherwise pick
        # a short snake_case task_type") — live traces show it invents
        # "create_note" as often as it uses the RED-tier "overwrite_note_
        # personal" string for the same kind of request. Match on substring
        # rather than an exact list so new LLM-invented synonyms (add_note,
        # note_this, etc.) still land here instead of back in the HP-lottery.
        if task_type in ("save_note", "overwrite_note_personal") or "note" in task_type:
            return self._save_note(task.get("params") or {})
        # KNOWN_ISSUES #21's residual/#6 in the 2026-07-30 cleanup pass:
        # entity_add/knowledge_add/relation_add/knowledge_relate are real
        # task_types DISTRICT_TASK_MAP routes to memory_curator (a genuine,
        # distinct capability from note-saving — the knowledge graph, not
        # episodic memory), but until now nothing here declared them, so
        # they fell to the same HP-lottery default as the original #21 bug.
        if task_type in ("entity_add", "knowledge_add", "relation_add", "knowledge_relate"):
            return self._kg_write(task.get("params") or {}, task_type)
        if task_type == "knowledge_query":
            return self._kg_query(task.get("params") or {})
        # 2026-07-30 audit fix (Phase 2 — memory subsystem): governor.py's
        # DISTRICT_TASK_MAP routes the literal task_types "remember",
        # "recall", and "memory" straight to district=memory_curator (see
        # core/city/governor.py DISTRICT_TASK_MAP), but until now none of
        # them were declared here either — same HP-lottery-fallback class of
        # bug as save_note/entity_add above (KNOWN_ISSUES #21/#6). A user
        # saying "remember that my flight is Friday" or "recall what I said
        # about the flight" silently ran a full consolidate_old_episodes()
        # pass instead — the fact was never actually stored (or looked up),
        # and the reply was a meaningless episode count.
        if task_type in ("remember", "memory_store"):
            return self._remember_fact(task.get("params") or {})
        if task_type in ("recall", "memory_query", "memory"):
            # "memory" alone is ambiguous (LLM classifier shorthand for
            # "this is memory-flavored", not necessarily read vs write) —
            # treat it as a read, since a misclassified read that runs a
            # lookup is harmless, while a misclassified write would silently
            # fabricate a stored "fact" from a question.
            return self._recall_query(task.get("params") or {})
        if task_type == "consolidate":
            count = await self.consolidate_old_episodes()
            if self._consolidation_write_failed:
                return {"status": "error", "consolidated": 0,
                        "error": "consolidation summary could not be written; raw episodes kept"}
            return {"status": "ok", "consolidated": count}
        # 2026-07-30 audit fix (Phase 2 — orphaned MemoryRouter): anything
        # else that reaches memory_curator — an LLM-invented task_type not
        # in the fixed vocabulary above (governor.py: classify_chat_intent()
        # is free to pick "a short snake_case task_type" for non-RED-tier
        # requests, so novel synonyms like "log_this"/"jot" are expected),
        # or an HP-lottery win with no matching capability at all — used to
        # fall straight through to consolidate_old_episodes() and return a
        # bare episode count as the "answer", regardless of what the person
        # actually said. core/memory/router.py's MemoryRouter was built
        # earlier this session (task #117) specifically to classify free
        # text and dispatch it to whichever real store it belongs in
        # (policy/counterfactual/entity/reasoning/semantic/episodic), but
        # was never wired to an actual call site — grep confirmed its only
        # callers were its own self-test and unit test. This closes that
        # gap: real free text with nowhere better to go gets properly
        # classified and stored/queried instead of silently consolidating.
        # consolidate_old_episodes() is still reachable — it just needs the
        # explicit task_type="consolidate" now (handle_event() above already
        # uses that), rather than being every unmatched task_type's default.
        params = task.get("params") or {}
        text = str(
            params.get("query") or params.get("content") or params.get("text") or ""
        ).strip()
        if not text:
            count = await self.consolidate_old_episodes()
            return {"status": "ok", "consolidated": count, "note": "no text given; ran default consolidation"}
        try:
            from core.memory.router import get_router
            router = get_router()
            if self._looks_like_question(text):
                result = router.route_read(text)
                if result.store_result:
                    return {"status": "ok", "response": str(result.store_result)[:1000],
                            "routed_to": result.category}
                return {"status": "ok", "response": f"Nothing found for \"{text}\".",
                        "routed_to": result.category}
            result = router.route_write(text, event_type=task_type or "note", source="chat")
            return {"status": "ok", "response": f"Noted ({result.category}): {text}",
                    "routed_to": result.category}
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] memory_router dispatch failed: {e}")
            count = await self.consolidate_old_episodes()
            return {"status": "ok", "consolidated": count, "note": f"router unavailable ({e}); ran default consolidation"}

    @staticmethod
    def _looks_like_question(text: str) -> bool:
        """Cheap read-vs-write heuristic for the MemoryRouter catch-all
        above: a trailing '?' or a leading question word means 'look this
        up', anything else means 'store this'."""
        t = text.strip().lower()
        if t.endswith("?"):
            return True
        first_word = t.split()[0] if t.split() else ""
        return first_word in (
            "who", "what", "when", "where", "why", "how", "do", "does",
            "did", "is", "are", "was", "were", "can", "could", "should",
            "would", "will",
        )

    def _remember_fact(self, params: dict) -> dict:
        """Handle the literal 'remember'/'memory_store' task_type — store a
        fact the owner explicitly asked VECTOR to remember. Distinct from
        _save_note() (personal_note category, "note this down" phrasing):
        this is the semantic-memory equivalent for "remember X" phrasing,
        but shares the exact same idempotent content-hash key strategy so
        repeating the same fact converges to one row instead of duplicating
        (same fix rationale as _save_note(), 2026-07-30 idempotency pass)."""
        content = str(
            params.get("content") or params.get("query") or params.get("text") or ""
        ).strip()
        if not content:
            return {"status": "error", "error": "nothing given to remember"}
        fact_id = str(params.get("note_id") or params.get("title") or params.get("key") or "").strip()
        if fact_id:
            key = f"fact:id:{fact_id.lower()}"
        else:
            content_hash = hashlib.sha256(content.strip().lower().encode("utf-8")).hexdigest()[:16]
            key = f"fact:content:{content_hash}"
        try:
            if self._memory.remember(key, content, category="semantic_fact", confidence=0.9) is False:
                return {"status": "error", "error": "memory write failed; fact was not stored"}
            self._memory.store(event_type="remember", content=content, tags=["remember"], source="chat")
            self.award_points(10, "fact_remembered")
            return {"status": "ok", "response": f"Got it — I'll remember: {content}"}
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] remember failed: {e}")
            return {"status": "error", "error": str(e)}

    def _recall_query(self, params: dict) -> dict:
        """Return verbatim durable facts, never inferred answers from audit logs."""
        query = str(
            params.get("query") or params.get("content") or params.get("text") or ""
        ).strip()
        if not query:
            return {"status": "error", "error": "no recall query provided"}
        try:
            hits = self._memory.search_facts(query, limit=5)
            if not hits:
                return {"status": "ok", "response": f"I don't have anything remembered about \"{query}\"."}
            lines = [f"- [{h['timestamp'][:10]}] {h['value']}" for h in hits]
            return {"status": "ok", "response": "Here's what I remember:\n" + "\n".join(lines)}
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] recall failed: {e}")
            return {"status": "error", "error": str(e)}

    def _kg_write(self, params: dict, task_type: str) -> dict:
        """Handle entity_add/knowledge_add/relation_add/knowledge_relate.

        Governor dispatch only ever hands this free chat text (params.query/
        content/text) or, for a structured caller, explicit fields — supports
        both rather than assuming one shape. For free text, reuses
        KnowledgeGraph.add_from_text()'s existing "X is/uses/has/builds/runs
        Y" heuristic extractor (already built for exactly this purpose) so a
        statement like "VECTOR runs on Ollama" becomes a real relation
        instead of silently falling through to consolidate_old_episodes().
        """
        from core.memory.knowledge_graph import get_knowledge_graph
        kg = get_knowledge_graph()
        try:
            # Structured entity add: {"name": ..., "entity_type": ..., "properties": {...}}
            if task_type in ("entity_add", "knowledge_add") and params.get("name"):
                entity = kg.add_entity(
                    str(params["name"]),
                    entity_type=str(params.get("entity_type", "concept")),
                    properties=params.get("properties") or {},
                )
                self.award_points(10, "entity_added")
                return {"status": "ok", "response": f"Added to knowledge graph: {entity.name} ({entity.entity_type})"}

            # Structured relation add: {"subject": ..., "predicate": ..., "object": ...}
            if task_type in ("relation_add", "knowledge_relate") and params.get("subject") and params.get("object"):
                relation = kg.add_relation(
                    str(params["subject"]),
                    str(params.get("predicate", "related_to")),
                    str(params["object"]),
                    confidence=float(params.get("confidence", 1.0)),
                    source=str(params.get("source", "chat")),
                )
                self.award_points(10, "relation_added")
                return {"status": "ok", "response": f"Noted: {relation.subject} {relation.predicate} {relation.obj}"}

            # Free-text fallback (the common real path — classify_chat_intent
            # hands over the raw user sentence, not structured fields).
            text = str(
                params.get("query") or params.get("content") or params.get("text") or ""
            ).strip()
            if not text:
                return {"status": "error", "error": f"no entity/relation content provided for {task_type}"}
            relations = kg.add_from_text(text, source="chat")
            if relations:
                self.award_points(10, "kg_extracted_from_text")
                summary = "; ".join(f"{r.subject} {r.predicate} {r.obj}" for r in relations)
                return {"status": "ok", "response": f"Noted for the knowledge graph: {summary}"}
            # No extractable subject-predicate-object triple (heuristic regex
            # needs capitalized proper-noun-shaped subject/object) — still
            # store the raw statement as a low-confidence generic entity
            # rather than silently dropping it or running an unrelated
            # consolidation pass.
            entity = kg.add_entity(text[:80], entity_type="note", properties={"raw": text})
            self.award_points(5, "kg_entity_fallback")
            return {"status": "ok", "response": f"Noted: {text}"}
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] {task_type} failed: {e}")
            return {"status": "error", "error": str(e)}

    def _kg_query(self, params: dict) -> dict:
        """Handle knowledge_query — read-only lookup against the knowledge graph."""
        from core.memory.knowledge_graph import get_knowledge_graph
        term = str(
            params.get("query") or params.get("term") or params.get("content") or params.get("text") or ""
        ).strip()
        if not term:
            return {"status": "error", "error": "no search term provided for knowledge_query"}
        try:
            result = get_knowledge_graph().query(term)
            if not result.entities and not result.relations:
                return {"status": "ok", "response": f"Nothing in the knowledge graph yet for \"{term}\"."}
            return {"status": "ok", "response": result.to_markdown()}
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] knowledge_query failed: {e}")
            return {"status": "error", "error": str(e)}

    def _save_note(self, params: dict) -> dict:
        """Save a "note this down" / personal-reminder-style request.

        KNOWN_ISSUES #21/#23: save_note and overwrite_note_personal are
        real task_types Governor.dispatch() routes to district="memory_curator"
        (classify_chat_intent() picks them with high confidence — e.g. 0.95
        live), but none of the 3 memory_curator agents ever declared either as
        a capability. That meant the request fell through to
        Governor.dispatch()'s HP-lottery fallback (governor.py's Task A.3
        note) and ran whatever agent won HP's UNRELATED default action
        instead — for this bot, that's consolidate_old_episodes(), which
        returns {"consolidated": <count>}. Confirmed live: a "note this down"
        request silently consolidated old episodes instead, and the bare
        episode count (e.g. 200) rendered as the entire response — nonsense
        to the person who asked to have something noted. This gives the task
        type an actual, correct handler instead of an accidental one.
        """
        content = str(
            params.get("content") or params.get("query") or params.get("text") or ""
        ).strip()
        if not content:
            return {"status": "error", "error": "no note content provided to save"}

        # 2026-07-30 audit fix (idempotency): the key used to be
        # f"note:{now.isoformat()}" — a fresh microsecond-precision
        # timestamp every call, so asking "note this down: X" twice (a
        # plausible real scenario: the owner repeats themselves, or a client
        # retry fires after a slow response) created two separate rows with
        # identical content, both retrievable forever, no way to tell
        # they're the same note. remember()'s underlying SQL is already a
        # real upsert (INSERT ... ON CONFLICT(key) DO UPDATE) — the bug was
        # purely in how the key was built, defeating that. Two cases now:
        #   - explicit note_id/title in params -> key by that (lets a
        #     caller that KNOWS which note it means genuinely overwrite it
        #     — this is what "overwrite_note_personal" needs to actually
        #     overwrite something instead of just adding another note).
        #   - no identifier given -> key by a hash of the normalized
        #     content, so repeating the exact same note converges to one
        #     row instead of duplicating, while a genuinely different note
        #     still gets its own key.
        note_id = str(params.get("note_id") or params.get("title") or "").strip()
        if note_id:
            key = f"note:id:{note_id.lower()}"
        else:
            content_hash = hashlib.sha256(content.strip().lower().encode("utf-8")).hexdigest()[:16]
            key = f"note:content:{content_hash}"
        try:
            if self._memory.remember(key, content, category="personal_note", confidence=1.0) is False:
                return {"status": "error", "error": "memory write failed; note was not saved"}
            self.award_points(10, "note_saved")
            return {"status": "ok", "response": f"Noted: {content}"}
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] save_note failed: {e}")
            return {"status": "error", "error": str(e)}

    def _store_findings(self, params: dict) -> dict:
        """Store a specific research finding into semantic memory.

        districts/research/research_hub.py's event-triggered research sends
        this — it expects a targeted write, not a full consolidation pass.
        Reuses the same EpisodicMemory.remember() write path
        consolidate_old_episodes() already uses for semantic-memory entries.
        """
        topic = str(params.get("topic", "")).strip()
        findings = str(params.get("findings", "")).strip()
        if not topic or not findings:
            return {"status": "error", "error": "store_findings needs both 'topic' and 'findings'"}
        key = f"finding:{topic}:{datetime.datetime.now().isoformat()}"
        try:
            if self._memory.remember(key, findings, category="research_finding", confidence=0.6) is False:
                return {"status": "error", "error": "memory write failed; findings were not stored"}
            self.award_points(15, "finding_stored")
            return {"status": "ok", "key": key}
        except Exception as e:
            logger.warning(f"[VECTOR][consolidation_bot] store_findings failed: {e}")
            return {"status": "error", "error": str(e)}

    async def run_forever(self) -> None:
        """Daily reflection + weekly consolidation. RULE 2 — never crashes."""
        logger.info("[VECTOR][consolidation_bot] run_forever started")
        while self.is_alive:
            try:
                await self.write_daily_reflection()
                if datetime.datetime.now().weekday() == 0:  # Monday = weekly consolidation
                    await self.consolidate_old_episodes()
            except Exception as e:
                logger.error(f"[VECTOR][consolidation_bot] tick error: {e}")
                self.deduct_points(10, "tick error")

            for _ in range(1440):  # 24h in 1-min chunks — responsive to is_alive
                if not self.is_alive:
                    break
                await asyncio.sleep(60)

        logger.warning("[VECTOR][consolidation_bot] died — HP=0")


if __name__ == "__main__":
    import tempfile, os
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        bot = ConsolidationBot(generation=1)
        assert bot.health_points == 500
        assert bot.name == "ConsolidationBot"
        assert bot.district == "memory_curator"

        # Seed an episode to reflect on
        bot._memory.store(
            event_type="task",
            content="ConsolidationBot smoke test event",
            tags=["smoke", "test"],
            source="smoke_test",
        )

        # write_daily_reflection — writes to real vault, graceful if Ollama absent
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Reflections").mkdir()
            bot._obsidian._vault = vault

            ok = await bot.write_daily_reflection()
            assert ok, "write_daily_reflection returned False"
            assert bot.health_points > 500, "HP should have increased after success"

            note_files = list((vault / "Reflections").glob("*.md"))
            assert note_files, "No reflection note written to vault"
            content = note_files[0].read_text(encoding="utf-8")
            assert "source: vector" in content

        print(f"✅ consolidation_bot.py OK  HP={bot.health_points}")

    asyncio.run(_smoke())
