"""Skill utilities -- load, preprocess, and execute skills.

NOTE: this module has zero callers anywhere in the repo (confirmed via
grep) -- the real, live skill-loading module is vectorcode/src/agent/
skill_utils.py (a separate, much larger file with the same confusingly
similar name). This file is dormant, not deleted, so the same CWE-22 fix
below is applied defensively per this audit's established "dormant
doesn't mean low priority" rule -- but agent/skill_utils.py's own
load_skill()-equivalent should be checked for the identical unconfined-
skill_name-into-path shape by whoever covers that file.
"""

from loguru import logger
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path.home() / ".vector" / "skills"

def list_skills() -> list[str]:
    if not SKILLS_DIR.exists(): return []
    return sorted(d.name for d in SKILLS_DIR.iterdir() if d.is_dir())

def load_skill(skill_name: str) -> Optional[str]:
    # skill_name must be a single path component -- SKILLS_DIR / skill_name
    # with no confinement check would let "../../etc" (or an absolute path,
    # which Path's / operator treats as a full replacement) escape SKILLS_DIR.
    if not skill_name or skill_name in (".", "..") or "/" in skill_name or "\\" in skill_name:
        logger.warning("Refusing unsafe skill_name {!r}", skill_name)
        return None
    skill_dir = SKILLS_DIR / skill_name
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        try: return skill_file.read_text(encoding="utf-8")
        except Exception as e: logger.warning("Failed to load skill {}: {}", skill_name, e)
    return None

def preprocess_skill(content: str, context: str = "") -> str:
    parts = [content]
    if context: parts.insert(0, f"Context:\n{context}")
    return "\n\n".join(parts)
