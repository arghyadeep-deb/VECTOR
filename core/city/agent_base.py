
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from loguru import logger
import datetime, uuid

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
        # Per-agent voice style — empty string means "use global personality"
        self.voice_style: str = (
            _AGENT_NAME_VOICE_STYLES.get(name.lower(), "")
            or _DISTRICT_VOICE_STYLES.get(district, "")
        )
        logger.info(f'[VECTOR][city] Agent {name} gen {generation} born at 500 HP using {self.model}')

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
            return self.die()
        return {
            "old_hp": old_hp,
            "new_hp": self.health_points,
            "model_changed": model_changed,
            "new_model": self.model,
            "reason": reason
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
        """Register interest in an event type. No-op until event_bus wiring is implemented."""
        pass

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
    a.award_points(350, 'test award')
    assert a.health_points == 850
    assert a.is_elite is True
    a.deduct_points(900, 'test death')
    assert a.health_points == 0
    assert 'died_at' in a.ghost_memory
    print('??? agent_base.py OK')
