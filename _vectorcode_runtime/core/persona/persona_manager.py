from __future__ import annotations

from datetime import datetime

from loguru import logger

from core.persona.schemas import PersonaState, ToneContext
from core.persona.identity import PersonaIdentityLoader
from core.persona.voice_tone import ToneModulator
from core.persona.evolution import PersonaEvolution
from core.persona.consistency import ConsistencyEnforcer

__all__ = ["PersonaManager"]


class PersonaManager:
    _instance: PersonaManager | None = None

    def __init__(self) -> None:
        self._identity_loader = PersonaIdentityLoader()
        self._tone = ToneModulator()
        self._evolution = PersonaEvolution()
        self._consistency = ConsistencyEnforcer()

    @classmethod
    def get(cls) -> PersonaManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_persona_state(self, person_id: str | None = None) -> PersonaState:
        identity = self._identity_loader.load()
        evolved = self._evolution.get_evolved_traits()
        prefs: dict = {}
        if person_id:
            prefs = self._identity_loader.adjust_for_owner(person_id)
        now = datetime.now()
        tod = self._tone.infer_time_of_day(now.hour)
        tone_ctx = ToneContext(time_of_day=tod)
        return PersonaState(
            identity=identity,
            current_tone=tone_ctx,
            evolution_level=self._evolution.get_evolution_level(),
            learned_preferences=prefs,
            relationship_depth=evolved,
        )

    def inject_persona(
        self,
        system_prompt: str,
        person_id: str | None = None,
        context: ToneContext | None = None,
    ) -> str:
        identity_fragment = self._identity_loader.get_system_prompt_fragment()
        tone_ctx = context or self._auto_tone_context()
        tone_instructions = self._tone.get_tone_instructions(tone_ctx)
        parts = [identity_fragment, tone_instructions]
        if person_id:
            style = self._identity_loader.adjust_for_owner(person_id)
            if style:
                style_line = (
                    f"[ADJUSTED STYLE for {person_id}] "
                    f"formality={style.get('formality', 0.7):.1f}, "
                    f"verbosity={style.get('verbosity', 0.5):.1f}, "
                    f"technicality={style.get('technicality', 0.8):.1f}, "
                    f"directness={style.get('directness', 0.7):.1f}"
                )
                parts.append(style_line)
        evolved = self._evolution.get_evolved_traits()
        if evolved:
            trait_parts = [f"{k}={v:.2f}" for k, v in evolved.items()]
            parts.append(f"[EVOLVED TRAITS] {', '.join(trait_parts)}")
        persona_block = "\n\n".join(parts)
        if system_prompt:
            return persona_block + "\n\n---\n\n" + system_prompt
        return persona_block

    def record_interaction(self, person_id: str, outcome: str) -> None:
        signal_map = {
            "positive": "owner_interaction",
            "correction": "owner_correction",
            "prediction_correct": "correct_prediction",
            "task_completed": "task_completed",
        }
        signal_type = signal_map.get(outcome, "owner_interaction")
        self._evolution.record_signal(signal_type, {"person_id": person_id})
        logger.debug(
            "[VECTOR][persona_manager] recorded interaction: person={} outcome={}",
            person_id,
            outcome,
        )

    def health_check(self) -> dict:
        return {
            "identity_loaded": self._identity_loader.load() is not None,
            "evolution_level": self._evolution.get_evolution_level(),
            "evolved_traits": len(self._evolution.get_evolved_traits()),
        }

    def _auto_tone_context(self) -> ToneContext:
        now = datetime.now()
        tod = self._tone.infer_time_of_day(now.hour)
        return ToneContext(time_of_day=tod)
