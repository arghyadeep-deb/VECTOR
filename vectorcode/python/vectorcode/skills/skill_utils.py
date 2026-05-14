"""Skill utilities — load, preprocess, and execute skills."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SKILLS_DIR = Path.home() / ".vector" / "skills"


def list_skills() -> list[str]:
    if not SKILLS_DIR.exists(): return []
    return sorted(d.name for d in SKILLS_DIR.iterdir() if d.is_dir())


def load_skill(skill_name: str) -> Optional[str]:
    skill_dir = SKILLS_DIR / skill_name
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        try: return skill_file.read_text(encoding="utf-8")
        except Exception as e: logger.warning(f"Failed to load skill {skill_name}: {e}")
    return None


def preprocess_skill(content: str, context: str = "") -> str:
    parts = [content]
    if context: parts.insert(0, f"Context:\n{context}")
    return "\n\n".join(parts)
