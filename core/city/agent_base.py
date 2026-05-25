
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG
from loguru import logger
import datetime, uuid

class AgentBase:
    def __init__(self, agent_id, name, district, generation=1):
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
        self.created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.last_active = self.created_at
        self.subscribed_events: set[str] = set()
        self._inbox: list[dict] = []
        # â”€â”€ Role system â€” load specialist role by name/district â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self.role = self._load_role(name, district)
        if self.role:
            logger.debug(
                "[VECTOR][city] {} loaded role={} tier={}",
                name, self.role.name, self.role.tier,
            )
        # â”€â”€ Vectorcode-backed LLM caller (auto-loads .md system prompt) â”€â”€â”€â”€â”€â”€
        self._district_llm = self._make_district_llm()
        logger.info(f'[VECTOR][city] Agent {name} gen {generation} born at 500 HP using {self.model}')

    def _load_role(self, name: str, district: str):
        """Load specialist role from roles registry by agent name or district."""
        try:
            from core.engine.agents.roles import get_agent_prompt, ROLES_BY_NAME
            # Try exact name match first (e.g. "researcher" â†’ RESEARCHER role)
            key = name.lower().replace("agent", "").replace("bot", "").strip("_- ")
            role = ROLES_BY_NAME.get(key)
            if role:
                return role
            # Fall back to district-level mapping
            _DISTRICT_ROLES = {
                "research": "researcher",
                "coding":   "code_executor",
                "governance": "orchestrator",
                "memory_curator": "archivist",
                "reflection": "archivist",
                "intelligence": "researcher",
            }
            district_role_key = _DISTRICT_ROLES.get(district)
            if district_role_key:
                return ROLES_BY_NAME.get(district_role_key)
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return None

    def get_system_prompt(self) -> str:
        """Return this agent's system prompt enriched with personality context."""
        parts = []
        if self.role and self.role.system_prompt:
            parts.append(self.role.system_prompt)
        personality_ctx = self._get_personality_context()
        if personality_ctx:
            parts.append(personality_ctx)
        return "\n\n".join(parts) if parts else ""

    def _get_personality_context(self) -> str:
        """Return personality trait summary if personality engine is enabled."""
        if not CONFIG.get("personality", {}).get("enabled", True):
            return ""
        try:
            from core.personality import PersonalityEngine
            pe = PersonalityEngine()
            self.personality_traits = dict(pe.card.traits)
            return (
                f"[PERSONALITY â€” {pe.card.name}]\n"
                f"Traits: {pe.card.get_traits_summary()}\n"
                f"Speech: address as '{pe.card.speech_patterns.address_owner}', "
                f"contractions={pe.card.speech_patterns.contractions}, "
                f"emoji={pe.card.speech_patterns.emoji}"
            )
        except Exception as e:
            logger.debug(f"[VECTOR][city] personality context unavailable: {e}")
            return ""

    def _make_district_llm(self):
        """Lazy-init DistrictLLM â€” routes calls through vectorcode_llm + .md prompt."""
        try:
            from core.inference.district_llm import DistrictLLM
            return DistrictLLM(self.district, self.name)
        except Exception as e:
            logger.debug(f"[VECTOR][city] DistrictLLM init skipped for {self.name}: {e}")
            return None

    def vchat(self, messages: list[dict], timeout: float = 30.0,
               inject_md: bool = True) -> str:
        """Convenience: call vectorcode LLM chain with optional .md system prompt.

        Preferred over importing ollama_safe directly â€” routes through the full
        Ollama â†’ Gemini â†’ Anthropic â†’ OpenRouter provider chain.
        """
        if self._district_llm is not None:
            return self._district_llm.chat(
                model=self.model or "vector-focus",
                messages=messages,
                timeout=timeout,
                inject_md=inject_md,
            )
        # Fallback to raw ollama_safe if DistrictLLM unavailable
        try:
            from core.inference.ollama_safe import chat
            return chat(model=self.model or "vector-focus",
                        messages=messages, timeout=timeout)
        except Exception:
            return ""

    def _calculate_model(self) -> str:
        # HP tier thresholds â€” override via CONFIG["hp_tiers"] dict
        tiers = CONFIG.get("hp_tiers", {})
        t_elite  = tiers.get("elite",    800)
        t_strong  = tiers.get("strong",  600)
        t_healthy = tiers.get("healthy", 400)
        t_weak    = tiers.get("weak",    200)
        if self.health_points >= t_elite:
            return CONFIG['models']['cloud_coder']
        elif t_strong <= self.health_points < t_elite:
            return CONFIG['models']['cloud_orchestrator']
        elif t_healthy <= self.health_points < t_strong:
            return CONFIG['models']['focus']
        elif t_weak <= self.health_points < t_healthy:
            return CONFIG['models']['reasoning']
        elif 1 <= self.health_points < t_weak:
            return CONFIG['models']['ambient']
        else:
            return None

    def _validate_hp_delta(self, delta: float, reason: str) -> float:
        """Run HP delta through the validator; return the validated delta."""
        try:
            from core.security.hp_validator import get_hp_validator
            result = get_hp_validator().validate(
                delta=delta,
                agent_id=self.id,
                source_district=getattr(self, "district", "unknown"),
                context={"reason": reason},
            )
            if result.issues:
                logger.warning(
                    "[VECTOR][hp] {} delta={} issues: {}",
                    self.name, delta, "; ".join(result.issues),
                )
            return result.validated_delta
        except Exception as _hpe:
            logger.debug("[VECTOR][hp] validator unavailable: {}", _hpe)
            return delta

    def award_points(self, points, reason) -> dict:
        validated = self._validate_hp_delta(float(points), reason)
        old_hp = self.health_points
        self.health_points = min(1000, self.health_points + validated)
        old_model = self.model
        self.model = self._calculate_model()
        model_changed = self.model != old_model
        logger.info(f'[VECTOR][city] {self.name} +{validated:.1f}HP ({reason}) | {old_hp}->{self.health_points}')
        if model_changed:
            logger.info(f'[VECTOR][city] {self.name} model upgraded: {old_model} -> {self.model}')
        return {
            "old_hp": old_hp,
            "new_hp": self.health_points,
            "model_changed": model_changed,
            "new_model": self.model,
            "reason": reason
        }

    def deduct_points(self, points, reason) -> dict:
        validated = abs(self._validate_hp_delta(-float(points), reason))
        old_hp = self.health_points
        self.health_points = max(0, self.health_points - validated)
        old_model = self.model
        self.model = self._calculate_model()
        model_changed = self.model != old_model
        logger.warning(f'[VECTOR][city] {self.name} -{validated:.1f}HP ({reason}) | {old_hp}->{self.health_points}')
        if self.health_points == 0:
            ghost = self.die()
            return {
                "old_hp": old_hp,
                "new_hp": 0,
                "model_changed": True,
                "new_model": None,
                "reason": reason,
                "died": True,
                "ghost": ghost,
            }
        return {
            "old_hp": old_hp,
            "new_hp": self.health_points,
            "model_changed": model_changed,
            "new_model": self.model,
            "reason": reason,
            "died": False,
        }

    def die(self) -> dict:
        ghost = {
            'name': self.name, 'district': self.district,
            'generation': self.generation, 'final_hp': 0,
            'lessons_learned': self.lessons[-20:],
            'best_decisions': self.best_decisions[-10:],
            'personality_traits': self.personality_traits,
            'died_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self.ghost_memory = ghost
        logger.warning(f'[VECTOR][city] Agent {self.name} gen {self.generation} DIED. Ghost preserved with {len(self.lessons)} lessons.')
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

    async def handle_event(self, event: dict) -> dict:
        """Receive an event published by another agent. Override in subclasses."""
        self.last_active = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._inbox.append(event)
        logger.debug("[VECTOR][agent_base] {} got event type={}", self.name, event.get("event_type"))
        return {"status": "queued", "agent": self.name, "event": event.get("event_type", "?")}

    def subscribe_to(self, event_type: str) -> None:
        """Subscribe to a cross-district event by EventType value."""
        self.subscribed_events.add(event_type)
        logger.debug("[VECTOR][agent_base] {} subscribed to {}", self.name, event_type)

    async def run(self, task: dict) -> dict:
        """Standard dispatch interface. Governor calls this.
        Subclasses override to handle task['type'] and task['params']."""
        self.last_active = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return {"status": "ok", "agent": self.name, "task": task.get("type", "?"), "note": "base handler"}

    async def request_agent_help(self, target_agent_id: str, task: dict) -> dict:
        """Delegate a task to another agent via WorkflowRunner.

        Enqueues a single-step workflow targeting `target_agent_id` and injects it
        into the WorkflowRunner. The receiving agent processes it in its next
        think tick. Returns immediately with a workflow_id.

        Example:
            await self.request_agent_help("research_hub", {
                "type": "search", "params": {"query": "blockchain trading bots"}
            })
        """
        try:
            from core.loop.workflow_runner import WorkflowRunner
            runner = WorkflowRunner()
            workflow_id = await runner.trigger_workflow(
                name=f"agent_help_{self.name}_to_{target_agent_id}",
                steps=[{
                    "agent_id": target_agent_id,
                    "task": task,
                    "requester": self.id,
                    "priority": "high",
                }],
            )
            logger.info(
                f"[VECTOR][agent_base] {self.name} â†’ {target_agent_id} "
                f"workflow_id={workflow_id} task={task.get('type', '?')}"
            )
            return {"workflow_id": workflow_id, "status": "queued"}
        except Exception as e:
            logger.warning(f"[VECTOR][agent_base] request_agent_help failed: {e}")
            return {"status": "error", "error": str(e)}

    # â”€â”€ Gap 8: Shared fact store â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def know(self, key: str, value: str, confidence: float = 0.7) -> None:
        """Publish a fact to the shared cross-agent fact store."""
        try:
            from core.memory.shared_facts import SharedFacts
            SharedFacts.get().set(key, value, confidence=confidence, source_agent=self.name)
        except Exception as e:
            logger.debug(f"[VECTOR][agent_base] know() failed: {e}")

    def recall_fact(self, key: str, default: str | None = None) -> str | None:
        """Look up a fact from the shared cross-agent fact store."""
        try:
            from core.memory.shared_facts import SharedFacts
            return SharedFacts.get().get(key, default)
        except Exception as e:
            logger.debug(f"[VECTOR][agent_base] recall_fact() failed: {e}")
            return default

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
    sys.stdout.reconfigure(encoding="utf-8")
    a = AgentBase(str(uuid.uuid4()), 'TestAgent', 'coding')
    assert a.health_points == 500
    assert a.model == CONFIG['models']['focus']
    a.award_points(350, 'test award')
    assert a.health_points == 850
    assert a.is_elite is True
    a.deduct_points(900, 'test death')
    assert a.health_points == 0
    assert 'died_at' in a.ghost_memory
    print('âœ… agent_base.py OK')
