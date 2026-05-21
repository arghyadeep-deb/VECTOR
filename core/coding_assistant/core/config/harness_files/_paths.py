from __future__ import annotations

from core.coding_assistant.core.paths import VECTOR_CA_HOME, GlobalPath

GLOBAL_TOOLS_DIR = GlobalPath(lambda: VECTOR_CA_HOME.path / "tools")
GLOBAL_SKILLS_DIR = GlobalPath(lambda: VECTOR_CA_HOME.path / "skills")
GLOBAL_AGENTS_DIR = GlobalPath(lambda: VECTOR_CA_HOME.path / "agents")
GLOBAL_PROMPTS_DIR = GlobalPath(lambda: VECTOR_CA_HOME.path / "prompts")
