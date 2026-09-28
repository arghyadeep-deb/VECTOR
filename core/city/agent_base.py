
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()
from core.config import CONFIG
from loguru import logger
import asyncio, datetime, uuid
from collections import deque

# Default global voice personality — used when an agent has no override
# Always respond in English regardless of the language the user writes/speaks
# in (VECTOR must still UNDERSTAND any language on input) — 2026-07-28 owner
# decision. See core/prompt_library.py's get()/get_for_agent() for the
# equivalent global suffix applied to the ~100 district-agent prompts.
_VECTOR_PERSONALITY = (
    "You are VECTOR, a precise and professional AI assistant. "
    "Speak clearly and concisely. "
    "Always respond in English, no matter what language the user writes or "
    "speaks in — understand any language, but reply only in English."
)

# Pre-set voice styles for key agents (district → style string)
_DISTRICT_VOICE_STYLES: dict[str, str] = {
    "governance": "Formal, deliberate, and authoritative. Suitable for high-stakes council decisions.",
    "coding":     "Terse and technical. No filler words. Output facts and code references only.",
    "research":   "Curious and precise. Cite sources. Ask clarifying questions when context is unclear.",
}

# Per-agent-name overrides (name.lower() → style string)
_AGENT_NAME_VOICE_STYLES: dict[str, str] = {
    "councilchairman": "Formal, deliberate, and authoritative. Suitable for high-stakes council decisions.",
    "gitbot":          "Terse and technical. No filler words. Output facts and code references only.",
}


def _model_rank() -> dict:
    m = CONFIG['models']
    return {m['ambient']: 1, m['reasoning']: 2, m['focus']: 3, m['cloud_orchestrator']: 4, m['cloud_coder']: 5}


class AgentBase:
    def __init__(self, agent_id, name, district, generation=1):
        self._ensure_legacy_event_loop()
        self.id = agent_id
        self.name = name
        self.district = district
        self.generation = generation
        self.health_points = 500
        self.model = self._calculate_model()
        self.ghost_memory = {}
        self.lessons = []
        self.best_decisions = []
        self.personality_traits = {}
        self.created_at = datetime.datetime.utcnow().isoformat()
        self.last_active = self.created_at
        self.subscribed_events: set[str] = set()
        self._inbox = deque(maxlen=500)
        self._facts: dict[str, object] = {}
        self._district_llm = None
        # Populated from config/agent_manifest.yaml by ManifestLoader — lets
        # governor.dispatch() pick the agent whose declared capability
        # matches the task type when a district has more than one agent,
        # instead of always picking whichever has the highest HP.
        self.capabilities: list[str] = []
        # Per-agent voice style — empty string means "use global personality"
        self.voice_style: str = (
            _AGENT_NAME_VOICE_STYLES.get(name.lower(), "")
            or _DISTRICT_VOICE_STYLES.get(district, "")
        )
        # HP reward-curve shaping state (2026-08-05 fix) — see award_points().
        # Counts how many times THIS agent has been awarded points for each
        # exact `reason` string, so a routine task that repeats unchanged
        # every tick (health_check_done, seo_report_generated, ...) can be
        # told apart from genuinely novel/varied accomplishments. Lives only
        # as long as this instance — a fresh generation (spawned on death)
        # starts with a clean slate, same as self.lessons/self._facts.
        self._reason_award_counts: dict[str, int] = {}
        logger.info(f'[VECTOR][city] Agent {name} gen {generation} born at 500 HP using {self.model}')

    @staticmethod
    def _ensure_legacy_event_loop() -> None:
        """Keep sync orchestration using get_event_loop() compatible with Python 3.13."""
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def _calculate_model(self) -> str:
        model = self._hp_model()
        try:
            from core.city import experience
            if experience.hp_fair_enabled() and model is not None:
                # Standing follows LEVEL, not the day's HP: experience can only raise the tier, never lower it. (HP still
                # decides at the bottom: at 0 there is no model at all.) Level 0 -> no change from the HP tier.
                lvl = experience.lineage_stats(self)["level"]
                floor = self._level_model(lvl)
                if floor is not None and _model_rank().get(floor, 0) > _model_rank().get(model, 0):
                    return floor
        except Exception:
            pass
        return model


    def _level_model(self, level: int):
        """The model tier a level guarantees: L2 reasoning, L4 focus, L6 orchestrator, L8 coder (0-1: no floor)."""
        if level >= 8:
            return CONFIG['models']['cloud_coder']
        if level >= 6:
            return CONFIG['models']['cloud_orchestrator']
        if level >= 4:
            return CONFIG['models']['focus']
        if level >= 2:
            return CONFIG['models']['reasoning']
        return None

    def _hp_model(self) -> str:
        if self.health_points >= 800:
            return CONFIG['models']['cloud_coder']
        elif 600 <= self.health_points < 800:
            return CONFIG['models']['cloud_orchestrator']
        elif 400 <= self.health_points < 600:
            return CONFIG['models']['focus']
        elif 200 <= self.health_points < 400:
            return CONFIG['models']['reasoning']
        elif 1 <= self.health_points < 200:
            return CONFIG['models']['ambient']
        else:
            return None

    def get_voice_style(self) -> str:
        """Return this agent's voice/personality style string for TTS context.

        Returns self.voice_style if set; falls back to the global VECTOR personality.
        """
        return self.voice_style if self.voice_style else _VECTOR_PERSONALITY

    def _validate_hp_delta(self, delta: float, reason: str) -> float:
        """Validate an HP delta through the hardening layer, falling back safely."""
        try:
            from core.security.hp_validator import get_hp_validator

            result = get_hp_validator().validate(
                float(delta),
                self.id,
                self.district,
                {"agent": self.name, "reason": reason},
            )
            if result.issues:
                logger.warning(
                    "[VECTOR][city] HP validation issues for {}: {}",
                    self.name,
                    "; ".join(result.issues),
                )
            return float(result.validated_delta)
        except Exception as e:
            logger.warning("[VECTOR][city] HP validation fallback for {}: {}", self.name, e)
            return float(delta)

    def award_points(self, points, reason) -> dict:
        """Award HP for a task outcome, shaped so routine repetition can't
        pin an agent at the 1000 ceiling (2026-08-05 fix).

        Production measurement (4d17h run): 1,098 award events vs 4 deducts,
        0 deaths, "virtually every line reads +30.0HP | 1000->1000" — agents
        doing merely-frequent routine work (health_check_done,
        seo_report_generated, fired on every tick) saturated the cap within
        minutes because every award was full-value and the only ceiling was
        a flat `min(1000, hp+delta)`. That makes HP measure how often an
        agent runs, not the quality of what it did — the opposite of
        Critical Rule #4 ("fake HP = fake evolution"), and it is what makes
        Governor.dispatch()'s `max(agents, key=lambda a: a.health_points)`
        fallback an effectively arbitrary tiebreak once every agent in a
        district is tied at the ceiling.

        Two independent, multiplicative dampeners fix this without touching
        any of the ~160 call sites or changing the documented point
        constants (+100 owner approved, +50 task done well, +30 output
        used, +40 council vote, ...):

          1. Repeat-reason habituation — the Nth time THIS agent earns
             points for the exact same `reason` string, the raw award is
             divided by (1 + N). A reason that repeats unchanged forever
             (a templated health check, a routine report) decays toward
             zero marginal value within a few dozen repeats — precisely the
             pattern in the production log. A reason that never repeats
             (novel work, a one-off critical fix, an owner approval) always
             earns full credit the first time it happens.
          2. Headroom (ceiling-approach) scaling — every award is also
             scaled by how much room is left below the cap,
             (1000 - hp) / 1000. This is what stops saturation for agents
             whose reason strings differ on every call (e.g. per-query
             research awards) — mechanism 1 alone can't catch that, since
             each string only ever appears "for the first time". Approaching
             1000 now costs exponentially more real accomplishments the
             closer an agent gets, so agents with genuinely different
             performance profiles settle at genuinely different steady-state
             HP instead of all racing to the same wall.

        The hard `min(1000, ...)` / `max(0, ...)` clamps stay in place as a
        safety net regardless of shaping (see hp_validator's own outlier
        clamp), so HP can never leave [0, 1000] no matter how large a raw
        award is.

        deduct_points() is deliberately NOT shaped — the Darwinian death
        mechanic must stay at full strength; only the runaway positive side
        was broken.
        """
        old_hp = self.health_points
        repeat_count = self._reason_award_counts.get(reason, 0)
        self._reason_award_counts[reason] = repeat_count + 1
        repeat_multiplier = 1.0 / (1.0 + repeat_count)
        headroom_multiplier = max(0.0, (1000.0 - self.health_points) / 1000.0)
        shaped_points = points * repeat_multiplier * headroom_multiplier
        validated_points = max(0.0, self._validate_hp_delta(shaped_points, reason))
        self.health_points = min(1000, self.health_points + validated_points)
        # Fair-HP probation is a recovery window, not a permanent strike counter. Once an agent has genuinely recovered above the
        # documented 50 HP threshold, a later collapse starts a fresh probation instead of consuming stale chances forever.
        if self.health_points > 50 and getattr(self, "_probation_used", False):
            self._probation_used = False
            self._probation_left = 0
            logger.info(f'[VECTOR][city] {self.name} recovered above 50HP; probation reset')
        old_model = self.model
        self.model = self._calculate_model()
        model_changed = self.model != old_model
        logger.info(
            f'[VECTOR][city] {self.name} +{validated_points:.2f}HP ({reason}) | '
            f'{old_hp}->{self.health_points} '
            f'[repeat#{repeat_count} x{repeat_multiplier:.3f}, headroom x{headroom_multiplier:.3f}]'
        )
        if model_changed:
            logger.info(f'[VECTOR][city] {self.name} model upgraded: {old_model} -> {self.model}')
        return {
            "old_hp": old_hp,
            "new_hp": self.health_points,
            "model_changed": model_changed,
            "new_model": self.model,
            "reason": reason,
            "requested_delta": points,
            "validated_delta": validated_points,
            "repeat_count": repeat_count,
            "repeat_multiplier": repeat_multiplier,
            "headroom_multiplier": headroom_multiplier,
        }

    def deduct_points(self, points, reason) -> dict:
        old_hp = self.health_points
        validated_points = abs(self._validate_hp_delta(-abs(points), reason))
        self.health_points = max(0, self.health_points - validated_points)
        old_model = self.model
        self.model = self._calculate_model()
        model_changed = self.model != old_model
        logger.warning(f'[VECTOR][city] {self.name} -{validated_points}HP ({reason}) | {old_hp}->{self.health_points}')
        # Remember WHY HP was lost, so a death leaves a ghost that says what went wrong
        # (2026-09-25: real deaths had empty lessons because nothing recorded failures).
        # A reason already remembered is not added again, so repeats can't flood the 20 slots.
        lesson = f"lost {validated_points:g}HP: {reason}"
        if validated_points and not any(reason in str(x) for x in self.lessons):
            self.add_lesson(lesson)
        if self.health_points == 0:
            if self._grant_probation(reason):
                return {
                    "old_hp": old_hp, "new_hp": self.health_points, "model_changed": True, "new_model": self.model, "reason": reason,
                    "requested_delta": -abs(points), "validated_delta": -validated_points, "died": False, "probation": True,
                    "probation_left": self._probation_left,
                }
            ghost = self.die()
            return {
                "old_hp": old_hp,
                "new_hp": self.health_points,
                "model_changed": model_changed,
                "new_model": self.model,
                "reason": reason,
                "requested_delta": -abs(points),
                "validated_delta": -validated_points,
                "died": True,
                "ghost": ghost,
            }
        return {
            "old_hp": old_hp,
            "new_hp": self.health_points,
            "model_changed": model_changed,
            "new_model": self.model,
            "reason": reason,
            "requested_delta": -abs(points),
            "validated_delta": -validated_points,
            "died": False,
        }

    PROBATION_CHANCES = 3

    def _grant_probation(self, reason) -> bool:
        """Reaching 0 HP is not yet death (VECTOR_HP_FAIR): the first collapse of a generation puts the agent on probation at 1 HP
        with PROBATION_CHANCES more chances, and each further collapse spends one. Death comes when they are spent. A success that
        lifts HP back above 50 ends probation. Off by default: without the flag, 0 HP is death exactly as before."""
        try:
            from core.city import experience
            if not experience.hp_fair_enabled():
                return False
        except Exception:
            return False
        if not getattr(self, "_probation_used", False):
            self._probation_used = True
            self._probation_left = self.PROBATION_CHANCES
            note = f"collapsed to 0HP on '{reason}'; on probation for {self.PROBATION_CHANCES} more chances"
        elif getattr(self, "_probation_left", 0) > 0:
            self._probation_left -= 1
            note = f"collapsed again on '{reason}'; {self._probation_left} chances left"
        else:
            return False
        self.health_points = 1
        self.model = self._calculate_model()
        if not any(note[:40] in str(x) for x in self.lessons):
            self.add_lesson(note)
        logger.warning("[VECTOR][city] {} at 0HP -> probation ({} chances left)", self.name, getattr(self, "_probation_left", 0))
        return True

    def die(self) -> dict:
        try:
            from core.city import experience
            experience.record_death(self, cause="; ".join(str(x) for x in self.lessons[-3:]))
        except Exception:
            pass
        ghost = {
            'name': self.name, 'district': self.district,
            'generation': self.generation, 'final_hp': 0,
            'lessons_learned': self.lessons[-20:],
            'best_decisions': self.best_decisions[-10:],
            'personality_traits': self.personality_traits,
            'died_at': datetime.datetime.utcnow().isoformat()
        }
        self.ghost_memory = ghost
        logger.warning(f'[VECTOR][city] Agent {self.name} gen {self.generation} DIED. Ghost preserved with {len(self.lessons)} lessons.')
        # RULE 9 — actually remove from the city registry and spawn a successor.
        # Without this, deregister()'s full ghost->successor pipeline (already
        # built in agent_registry.py) was never triggered by anything.
        try:
            from core.city.agent_registry import get_registry
            get_registry().deregister(self.id)
        except Exception as e:
            logger.error(f'[VECTOR][city] {self.name} deregister/successor-spawn failed: {e}')
        return ghost

    def inherit_ghost(self, ghost):
        if not ghost:
            return
        self.lessons = ghost.get('lessons_learned', [])
        self.best_decisions = ghost.get('best_decisions', [])
        self.personality_traits = ghost.get('personality_traits', {})
        logger.info(f'[VECTOR][city] {self.name} inherited {len(self.lessons)} lessons from generation {ghost.get("generation")}')

    def add_lesson(self, lesson):
        self.lessons.append(lesson)
        self.lessons = self.lessons[-20:]

    def record_decision(self, decision, reward):
        if reward > 0.6:
            self.best_decisions.append({**decision, 'reward': reward})
            self.best_decisions = self.best_decisions[-10:]

    def can_vote_in_council(self) -> bool:
        try:
            from core.city import experience
            if experience.level_council_enabled():
                # experienced (level 5+) and not on the ropes; a strong day's HP alone no longer buys a vote
                return experience.lineage_stats(self)["level"] >= 5 and self.health_points >= 300
        except Exception:
            pass
        return self.health_points >= 700

    @property
    def level(self) -> int:
        try:
            from core.city import experience
            return experience.lineage_stats(self)["level"]
        except Exception:
            return 0

    def subscribe_to(self, event_type: str) -> None:
        """Register interest in an event type for local event-bus dispatch."""
        if event_type:
            self.subscribed_events.add(event_type)

    async def handle_event(self, event: dict) -> dict:
        """Queue an event for later agent processing."""
        self._inbox.append(event)
        self.last_active = datetime.datetime.utcnow().isoformat()
        return {"status": "queued", "agent": self.name, "event_type": event.get("event_type")}

    async def run(self, task: dict) -> dict:
        """Base task runner used by tests and simple district fallbacks.

        `"stub": True` marks this as the unoverridden base implementation —
        it did no real work, so Governor.dispatch()'s RULE 9 HP award must
        not treat this "ok" the same as a real district agent's demonstrated
        outcome (see governor.py's HP-award check). Additive only: status
        stays "ok" so existing callers that assert on it are unaffected.
        """
        self.last_active = datetime.datetime.utcnow().isoformat()
        return {"status": "ok", "agent": self.name, "task": task, "stub": True}

    def get_system_prompt(self) -> str:
        """Return a compact system prompt for generic agent interactions.

        Includes inherited lessons and best decisions from ghost memory so
        successors actually benefit from predecessor experience (RULE 9 —
        Darwinian evolution). Without this, gen-N agents behave identically
        to gen-1 regardless of how many lessons they inherited.
        """
        parts = [
            f"You are {self.name}, a VECTOR agent in the {self.district} district.",
            f"Generation {self.generation}, HP {self.health_points}.",
            self.get_voice_style(),
        ]

        # Inherited wisdom — lessons from deceased predecessors
        if self.lessons:
            lessons_text = "; ".join(str(l) for l in self.lessons[-10:])
            parts.append(f"You inherit these lessons from your predecessors: {lessons_text}.")

        # Proven decisions — high-reward choices to replicate
        if self.best_decisions:
            best = self.best_decisions[-5:]
            decisions_text = "; ".join(
                f"{d.get('decision', d)} (reward={d.get('reward', 0):.1f})"
                for d in best
            )
            parts.append(f"Your predecessors' best decisions: {decisions_text}.")

        book = self._playbook_text()
        if book:
            parts.append(book)

        return " ".join(parts)

    def _playbook_text(self, task_type: str | None = None) -> str:
        """DO / DON'T lines from this lineage's experience ledger (VECTOR_PLAYBOOK); empty when off or nothing is recorded."""
        try:
            from core.city import experience
            if not experience.playbook_enabled():
                return ""
            lines = experience.playbook(self, task_type=task_type, k=6)
            return ("What your lineage has learned: " + " ".join(lines)) if lines else ""
        except Exception:
            return ""

    def vchat(self, messages: list[dict] | str) -> str:
        """Small LLM helper with an Ollama-safe fallback path.

        RULE 1: session_hydration_prompt() before EVERY LLM call, no
        exceptions. This was previously missing here — every agent's own
        vchat() calls (the base helper ~25 district agents build on) went
        to the LLM with zero world-state/person-model/goal context, unlike
        every other real LLM call site in the codebase (governor.py,
        commands.py, ambient_listener.py, ...). Fixed 2026-09-23.
        """
        msg_list = [{"role": "user", "content": messages}] if isinstance(messages, str) else list(messages)
        try:
            from core.loop.context_engine import ContextEngine
            hydration = ContextEngine().session_hydration_prompt()
        except Exception as _hydr_err:
            logger.debug("[VECTOR][city] vchat hydration failed for {}: {}", self.name, _hydr_err)
            hydration = ""
        book = self._playbook_text()
        if book:
            hydration = (hydration + "\n\n" + book).strip() if hydration else book
        if hydration:
            if msg_list and msg_list[0].get("role") == "system":
                msg_list = [
                    {"role": "system", "content": (hydration + "\n\n" + msg_list[0].get("content", "")).strip()},
                    *msg_list[1:],
                ]
            else:
                msg_list = [{"role": "system", "content": hydration}, *msg_list]

        # 2026-09-23 fix (independent review of the RULE 1 hydration fix
        # above caught this): both real chat() signatures --
        # core/inference/district_llm.py's DistrictLLM.chat() and
        # core/inference/ollama_safe.py's chat() -- require `model` as a
        # REQUIRED first positional argument, `messages` second. The
        # previous calls here (both before and after the hydration fix)
        # passed only `msg_list`, landing in the `model` slot with no
        # `messages` argument at all -- a guaranteed TypeError on every
        # real call, silently swallowed by the except below, so vchat() has
        # never actually reached an LLM in production. self.model (HP-tier
        # resolved by _calculate_model()) is a real Ollama tag; fall back to
        # the ambient tag on the HP<1 edge case where it's None.
        _model = self.model or CONFIG["models"]["ambient"]
        if self._district_llm is not None:
            try:
                if hasattr(self._district_llm, "chat"):
                    return self._district_llm.chat(_model, msg_list)
                if callable(self._district_llm):
                    return self._district_llm(msg_list)
            except Exception as e:
                logger.debug("[VECTOR][city] district_llm fallback for {}: {}", self.name, e)
        try:
            from core.inference.ollama_safe import chat
            return chat(_model, msg_list, caller_id=f"agent_{self.name}"[:64])
        except Exception as e:
            logger.debug("[VECTOR][city] vchat fallback for {}: {}", self.name, e)
            if isinstance(messages, str):
                return messages
            return ""

    def know(self, key: str, value) -> None:
        """Store a lightweight fact locally; tries SharedFacts if available."""
        self._facts[key] = value
        try:
            from core.memory.shared_facts import SharedFacts
            # SharedFacts.set()'s real kwarg is source_agent=, not source= —
            # the old source= silently raised TypeError on every call (swallowed
            # below), so cross-agent fact sharing never actually persisted.
            SharedFacts().set(key, value, source_agent=self.name)
        except Exception as e:
            # Must not raise (agents can't crash because the fact store is
            # down) but must not lie about success either — log the real
            # error so this class of failure is visible going forward.
            logger.warning("[VECTOR][city] SharedFacts.set({!r}) failed for {}: {}", key, self.name, e)

    def recall_fact(self, key: str, default=None):
        """Recall a local/shared fact, returning default when unavailable."""
        if key in self._facts:
            return self._facts[key]
        try:
            from core.memory.shared_facts import SharedFacts
            value = SharedFacts().get(key)
            return default if value is None else value
        except Exception as e:
            logger.warning("[VECTOR][city] SharedFacts.get({!r}) failed for {}: {}", key, self.name, e)
            return default

    # ── Agent-to-agent (A2A) ───────────────────────────────────────────────────────────────────────────────────────────
    # Every agent in every district inherits these. They go through the governed bus (core/city/a2a_bus.py): Governor.dispatch()
    # for delivery (tier gate, unknown-type gate, timeout, HP accounting), depth/cycle/rate/budget limits, an audit trail, and no
    # inherited authority. Phase 1 carries information/analysis requests; YELLOW/RED task types need the PermissionGateway.

    async def a2a_ask(self, task_type: str, params: dict | None = None, *, to=None, capability: str | None = None,
                      timeout: float | None = None, escalate: bool = False, verify=None):
        """Ask a peer (by name/id, "district:<name>", or by declared capability) and wait. Returns an A2AReply; never raises.
        Pass `verify=lambda result: bool` to check the answer yourself: only a verified answer earns the helper collaboration XP."""
        from core.city.a2a_bus import get_bus
        return await get_bus().ask(self, task_type, params, to=to, capability=capability, timeout=timeout, escalate=escalate,
                                   verify=verify)

    async def a2a_delegate(self, task_type: str, params: dict | None = None, *, to=None, capability: str | None = None,
                           timeout: float | None = None):
        """Hand a piece of work to a peer and wait for the result (recorded as a delegation)."""
        from core.city.a2a_bus import get_bus
        return await get_bus().delegate(self, task_type, params, to=to, capability=capability, timeout=timeout)

    def a2a_tell(self, task_type: str, params: dict | None = None, *, to=None, capability: str | None = None) -> str:
        """Fire and forget. Returns a marker; the reply arrives in a2a_inbox()."""
        from core.city.a2a_bus import get_bus
        return get_bus().tell(self, task_type, params, to=to, capability=capability)

    def a2a_inbox(self, limit: int = 20) -> list[dict]:
        from core.city.a2a_bus import get_bus
        return get_bus().inbox(self.id, limit)

    def a2a_describe(self) -> dict:
        from core.city.a2a_bus import describe_agent
        return describe_agent(self)

    async def request_agent_help(self, target_agent: str, task: dict) -> dict:
        """Request help from another live agent, by name or district.

        2026-09-26: this used to look the target up and call `target.run(task)` directly -- around the Governor and the
        PermissionGateway, so a YELLOW/RED task type could run with no approval and the target's HP accounting was skipped.
        It now goes through the A2A bus. The return shape is unchanged: {"status": "requested"|"unavailable", "target_agent",
        "result"|"error"}, plus an "a2a" entry with the bus's own verdict.
        """
        try:
            from core.city.a2a_bus import get_bus
            bus = get_bus()
            task_type = str((task or {}).get("type") or (task or {}).get("action") or "")
            params = (task or {}).get("params") if isinstance((task or {}).get("params"), dict) else {}
            to = target_agent if bus.resolve(target_agent) is not None else f"district:{target_agent}"
            reply = await bus.ask(self, task_type, params, to=to)
            if reply.delivered:
                return {"status": "requested", "target_agent": target_agent, "result": reply.result, "a2a": reply.to_dict()}
            return {"status": "unavailable", "target_agent": target_agent,
                    "error": reply.refused or reply.error or reply.status, "a2a": reply.to_dict()}
        except Exception as e:
            logger.debug("[VECTOR][city] request_agent_help fallback: {}", e)
            return {"status": "unavailable", "target_agent": target_agent, "error": str(e)}

    def get_status(self) -> str:
        if self.health_points >= 800:
            return 'elite'
        elif self.health_points >= 600:
            return 'strong'
        elif self.health_points >= 400:
            return 'healthy'
        elif self.health_points >= 200:
            return 'weakened'
        elif self.health_points >= 1:
            return 'critical'
        else:
            return 'dead'

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'district': self.district,
            'generation': self.generation,
            'health_points': self.health_points,
            'model': self.model,
            'ghost_memory': self.ghost_memory,
            'lessons': self.lessons,
            'best_decisions': self.best_decisions,
            'personality_traits': self.personality_traits,
            'created_at': self.created_at,
            'last_active': self.last_active,
        }

    @property
    def is_alive(self):
        return self.health_points > 0

    @property
    def is_elite(self):
        return self.health_points >= 800

    @property
    def can_access_cloud(self):
        return self.health_points >= 600

if __name__ == '__main__':
    a = AgentBase(str(uuid.uuid4()), 'TestAgent', 'coding')
    assert a.health_points == 500
    assert a.model == CONFIG['models']['focus']

    # requested_delta always reports the raw ask; validated_delta reflects
    # repeat + headroom shaping (2026-08-05 fix), so it is no longer a
    # simple clamp-to-200 of the raw request.
    result = a.award_points(350, 'test award')
    assert result['requested_delta'] == 350
    assert result['repeat_count'] == 0
    assert 0 < result['validated_delta'] < 350
    assert a.health_points > 500
    assert a.is_elite is False

    # THE regression check for the saturation bug: hammering the exact same
    # reason over and over (the "health_check_done" production pattern)
    # must NOT ride min(1000, ...) up to the ceiling — each repeat is worth
    # strictly less than the last.
    spammer = AgentBase(str(uuid.uuid4()), 'SpammerAgent', 'ops')
    prior_delta = None
    for _ in range(50):
        r = spammer.award_points(30, 'health_check_done')
        if prior_delta is not None:
            assert r['validated_delta'] <= prior_delta, (
                'repeated identical reason must not gain value over time'
            )
        prior_delta = r['validated_delta']
    assert spammer.health_points < 700, (
        f'spammer pinned near the ceiling by routine repeats: {spammer.health_points}'
    )

    # A deliberately oversized single award still cannot push HP past 1000 —
    # hp_validator's own outlier clamp plus the final min(1000, ...) hold.
    a.health_points = 950
    a.award_points(1_000_000, 'huge one-off bonus')
    assert a.health_points == 1000
    assert a.is_elite is True

    # EMA smoothing damps opposite-sign deltas, so death takes several
    # max-size deductions rather than one oversized one. deduct_points is
    # intentionally NOT shaped — the death mechanic stays at full strength.
    for _ in range(50):
        if not a.is_alive:
            break
        a.deduct_points(200, 'test death')
    assert a.health_points == 0
    assert 'died_at' in a.ghost_memory
    print('OK agent_base.py')
