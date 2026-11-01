from __future__ import annotations

from core.coding_assistant.core.skills.builtins.vibe import SKILL as VIBE_SKILL
from core.coding_assistant.core.skills.models import SkillInfo

BUILTIN_SKILLS: dict[str, SkillInfo] = {skill.name: skill for skill in [VIBE_SKILL]}
