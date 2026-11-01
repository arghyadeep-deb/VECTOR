from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from loguru import logger
from core.config import CONFIG
from core.runtime_paths import data_path
from core.persona.schemas import PersonaIdentity

__all__ = ["PersonaIdentityLoader"]

_DEFAULT_IDENTITY = PersonaIdentity()
_DATA_DIR = data_path("persona")


class PersonaIdentityLoader:
    def __init__(self, data_dir: Path | None = None) -> None:
        self._dir = data_dir or _DATA_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "identity.yaml"
        self._identity: PersonaIdentity | None = None

    def load(self) -> PersonaIdentity:
        if self._identity is not None:
            return self._identity
        if self._path.exists():
            try:
                raw = yaml.safe_load(self._path.read_text(encoding="utf-8"))
                self._identity = PersonaIdentity.model_validate(raw)
                logger.debug("[VECTOR][persona] identity loaded from {}", self._path)
                return self._identity
            except Exception as e:
                logger.warning("[VECTOR][persona] identity.yaml parse failed: {}", e)
        self._identity = _DEFAULT_IDENTITY.model_copy()
        self._save()
        return self._identity

    def get_system_prompt_fragment(self) -> str:
        identity = self.load()
        traits = ", ".join(identity.core_traits)
        defaults = identity.communication_defaults
        lines = [
            f"[IDENTITY — {identity.name}]",
            f"Full name: {identity.full_name}",
            f"Core traits: {traits}",
            f"Communication defaults: formality={defaults.get('formality', 0.7):.1f}, "
            f"verbosity={defaults.get('verbosity', 0.5):.1f}, "
            f"technicality={defaults.get('technicality', 0.8):.1f}, "
            f"directness={defaults.get('directness', 0.7):.1f}",
            f"Address owner as: {identity.owner_title}",
            identity.personality_note,
        ]
        return "\n".join(lines)

    def adjust_for_owner(self, person_id: str) -> dict[str, Any]:
        try:
            from core.brain.person_model import PersonModel
            pm = PersonModel()
            style = pm.infer_communication_style(person_id)
            if style:
                identity = self.load()
                merged = dict(identity.communication_defaults)
                for key in ("formality", "verbosity", "technicality", "directness"):
                    if key in style:
                        merged[key] = style[key]
                logger.debug(
                    "[VECTOR][persona] identity adjusted for person={}", person_id
                )
                return merged
        except Exception as e:
            logger.debug("[VECTOR][persona] adjust_for_owner failed: {}", e)
        return dict(self.load().communication_defaults)

    def _save(self) -> None:
        if self._identity is None:
            return
        try:
            self._path.write_text(
                yaml.dump(self._identity.model_dump(), default_flow_style=False),
                encoding="utf-8",
            )
            logger.debug("[VECTOR][persona] identity saved to {}", self._path)
        except Exception as e:
            logger.warning("[VECTOR][persona] identity save failed: {}", e)
