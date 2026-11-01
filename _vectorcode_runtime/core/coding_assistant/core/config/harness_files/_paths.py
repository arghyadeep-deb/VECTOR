from __future__ import annotations

__all__ = [
    "GLOBAL_AGENTS_DIR",
    "GLOBAL_PROMPTS_DIR",
    "GLOBAL_SKILLS_DIR",
    "GLOBAL_TOOLS_DIR",
]


from core.coding_assistant.core.paths import VECTOR_CA_HOME, GlobalPath

GLOBAL_TOOLS_DIR = GlobalPath(lambda: VECTOR_CA_HOME.path / "tools")
GLOBAL_SKILLS_DIR = GlobalPath(lambda: VECTOR_CA_HOME.path / "skills")
GLOBAL_AGENTS_DIR = GlobalPath(lambda: VECTOR_CA_HOME.path / "agents")
GLOBAL_PROMPTS_DIR = GlobalPath(lambda: VECTOR_CA_HOME.path / "prompts")
