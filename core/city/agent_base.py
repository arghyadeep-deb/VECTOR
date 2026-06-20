
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()
from core.config import CONFIG
from loguru import logger
import asyncio, datetime, uuid
from collections import deque

# Default global voice personality — used when an agent has no override
_VECTOR_PERSONALITY = (
    "You are VECTOR, a precise and professional AI assistant. "
    "Speak clearly and concisely."
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
        # Per-agent voice style — empty string means "use global personality"
        self.voice_style: str = (
            _AGENT_NAME_VOICE_STYLES.get(name.lower(), "")
            or _DISTRICT_VOICE_STYLES.get(district, "")
        )
        logger.info(f'[VECTOR][city] Agent {name} gen {generation} born at 500 HP using {self.model}')

    @staticmethod
    def _ensure_legacy_event_loop() -> None:
        """Keep sync orchestration using get_event_loop() compatible with Python 3.13."""
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def _calculate_model(self) -> str:
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
        old_hp = self.health_points
        validated_points = max(0.0, self._validate_hp_delta(points, reason))
        self.health_points = min(1000, self.health_points + validated_points)
        old_model = self.model
        self.model = self._calculate_model()
        model_changed = self.model != old_model
        logger.info(f'[VECTOR][city] {self.name} +{validated_points}HP ({reason}) | {old_hp}->{self.health_points}')
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
        }

    def deduct_points(self, points, reason) -> dict:
        old_hp = self.health_points
        validated_points = abs(self._validate_hp_delta(-abs(points), reason))
        self.health_points = max(0, self.health_points - validated_points)
        old_model = self.model
        self.model = self._calculate_model()
        model_changed = self.model != old_model
        logger.warning(f'[VECTOR][city] {self.name} -{validated_points}HP ({reason}) | {old_hp}->{self.health_points}')
        if self.health_points == 0:
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

    def die(self) -> dict:
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
        return self.health_points >= 700

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
        """Base task runner used by tests and simple district fallbacks."""
        self.last_active = datetime.datetime.utcnow().isoformat()
        return {"status": "ok", "agent": self.name, "task": task}

    def get_system_prompt(self) -> str:
        """Return a compact system prompt for generic agent interactions."""
        return (
            f"You are {self.name}, a VECTOR agent in the {self.district} district. "
            f"Generation {self.generation}, HP {self.health_points}. "
            f"{self.get_voice_style()}"
        )

    def vchat(self, messages: list[dict] | str) -> str:
        """Small LLM helper with an Ollama-safe fallback path."""
        if self._district_llm is not None:
            try:
                if hasattr(self._district_llm, "chat"):
                    return self._district_llm.chat(messages)
                if callable(self._district_llm):
                    return self._district_llm(messages)
            except Exception as e:
                logger.debug("[VECTOR][city] district_llm fallback for {}: {}", self.name, e)
        try:
            from core.inference.ollama_safe import chat
            return chat(messages)
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
            SharedFacts().set(key, value, source=self.name)
        except Exception:
            logger.warning("[VECTOR] silent swallow")
            pass

    def recall_fact(self, key: str, default=None):
        """Recall a local/shared fact, returning default when unavailable."""
        if key in self._facts:
            return self._facts[key]
        try:
            from core.memory.shared_facts import SharedFacts
            value = SharedFacts().get(key)
            return default if value is None else value
        except Exception:
            return default

    async def request_agent_help(self, target_agent: str, task: dict) -> dict:
        """Request help through the workflow runner when available."""
        try:
            from core.loop.workflow_runner import WorkflowRunner
            workflow_id = await WorkflowRunner().trigger_workflow(
                "agent_help",
                {"from": self.name, "to": target_agent, "task": task},
            )
            return {"status": "requested", "target_agent": target_agent, "workflow_id": workflow_id}
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
    # hp_validator clamps any single delta to ±MAX_DELTA (200), so a
    # 350-point award lands as +200.
    result = a.award_points(350, 'test award')
    assert result['requested_delta'] == 350
    assert result['validated_delta'] <= 200
    assert a.health_points == 700
    assert a.is_elite is False
    a.award_points(200, 'test award 2')
    assert a.health_points == 900
    assert a.is_elite is True
    # EMA smoothing damps opposite-sign deltas, so death takes several
    # max-size deductions rather than one oversized one.
    for _ in range(50):
        if not a.is_alive:
            break
        a.deduct_points(200, 'test death')
    assert a.health_points == 0
    assert 'died_at' in a.ghost_memory
    print('OK agent_base.py')