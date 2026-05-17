
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
        # ── Role system — load specialist role by name/district ──────────────
        self.role = self._load_role(name, district)
        if self.role:
            logger.debug(
                "[VECTOR][city] {} loaded role={} tier={}",
                name, self.role.name, self.role.tier,
            )
        # ── Vectorcode-backed LLM caller (auto-loads .md system prompt) ──────
        self._district_llm = self._make_district_llm()
        logger.info(f'[VECTOR][city] Agent {name} gen {generation} born at 500 HP using {self.model}')

    def _make_district_llm(self):
        """Lazy-init DistrictLLM — routes calls through vectorcode_llm + .md prompt."""
        try:
            from core.inference.district_llm import DistrictLLM
            return DistrictLLM(self.district, self.name)
        except Exception as e:
            logger.debug(f"[VECTOR][city] DistrictLLM init skipped for {self.name}: {e}")
            return None

    def vchat(self, messages: list[dict], timeout: float = 30.0,
               inject_md: bool = True) -> str:
        """Convenience: call vectorcode LLM chain with optional .md system prompt.

        Preferred over importing ollama_safe directly — routes through the full
        Ollama → Gemini → Anthropic → OpenRouter provider chain.
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

    def award_points(self, points, reason) -> dict:
        old_hp = self.health_points
        self.health_points = min(1000, self.health_points + points)
        old_model = self.model
        self.model = self._calculate_model()
        model_changed = self.model != old_model
        logger.info(f'[VECTOR][city] {self.name} +{points}HP ({reason}) | {old_hp}->{self.health_points}')
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
        old_hp = self.health_points
        self.health_points = max(0, self.health_points - points)
        old_model = self.model
        self.model = self._calculate_model()
        model_changed = self.model != old_model
        logger.warning(f'[VECTOR][city] {self.name} -{points}HP ({reason}) | {old_hp}->{self.health_points}')
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

    async def run(self, task: dict) -> dict:
        """Standard dispatch interface. Governor calls this.
        Subclasses override to handle task['type'] and task['params']."""
        self.last_active = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return {"status": "ok", "agent": self.name, "task": task.get("type", "?"), "note": "base handler"}

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
    print('✅ agent_base.py OK')
