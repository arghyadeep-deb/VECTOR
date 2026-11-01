"""
SkillAgent — loads and executes VECTOR/vectorcode skill .md files.

Skills live in brain/.claude/skills/ and districts/<district>/*.md.
This agent resolves skill names, loads the SKILL.md, and executes via LLM
(or runs the skill's bash commands if it has an executable section).
"""
from __future__ import annotations

import re
from pathlib import Path


from loguru import logger
from core.config import CONFIG

# Primary skill directories
_SKILL_DIRS = [
    Path.home() / ".claude" / "skills",                                          # global Claude skills
    Path(__file__).parent.parent.parent.parent / "brain" / ".claude" / "skills", # VECTOR brain skills
    Path(__file__).parent.parent.parent.parent / "agents" / "districts",          # district .md prompts
]


def _find_skill(name: str) -> Path | None:
    """Find a skill .md file by name across all skill directories."""
    slug = name.lower().strip().replace(" ", "-").replace("_", "-")
    for skill_dir in _SKILL_DIRS:
        if not skill_dir.exists():
            continue
        # Direct SKILL.md inside a named subfolder
        candidate = skill_dir / slug / "SKILL.md"
        if candidate.exists():
            return candidate
        # Flat .md file
        for pattern in [f"{slug}.md", f"vector-{slug}.md", f"vector-ag-*{slug}*.md"]:
            for match in skill_dir.rglob(pattern):
                return match
    return None


def _parse_skill(path: Path) -> dict:
    """Parse a SKILL.md file into {name, description, system_prompt, steps}."""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()
    frontmatter: dict = {}
    body = text
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    frontmatter[k.strip()] = v.strip().strip('"')
            body = text[end + 3:].strip()
    # Extract step sections
    steps = re.findall(r"^##\s+(.+)$", body, re.MULTILINE)
    return {
        "name": frontmatter.get("name", path.stem),
        "description": frontmatter.get("description", ""),
        "system_prompt": body,
        "steps": steps,
        "path": str(path),
    }


class SkillAgent:
    """
    Loads and executes vectorcode/VECTOR skills.

    A "skill" is a .md file defining a specialized capability.
    SkillAgent finds the skill, loads its system prompt, and invokes
    the LLM to execute it — or delegates to a Python agent if one exists.
    """

    def __init__(self):
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        self._skill_cache: dict[str, dict] = {}
        logger.info("[VECTOR][vc_skill] initialized with {} skill dirs", len(_SKILL_DIRS))

    def list_skills(self) -> list[dict]:
        """List all available skills across all skill directories."""
        skills = []
        seen = set()
        for skill_dir in _SKILL_DIRS:
            if not skill_dir.exists():
                continue
            for md in skill_dir.rglob("SKILL.md"):
                if md.stem not in seen:
                    try:
                        parsed = _parse_skill(md)
                        skills.append({"name": parsed["name"], "description": parsed["description"][:80],
                                       "path": parsed["path"]})
                        seen.add(parsed["name"])
                    except Exception:
                        logger.opt(exception=True).debug("[VECTOR] suppressed exception")
            for md in skill_dir.glob("*.md"):
                name = md.stem
                if name not in seen:
                    skills.append({"name": name, "description": "", "path": str(md)})
                    seen.add(name)
        return skills[:100]

    def load(self, skill_name: str) -> dict | None:
        """Load a skill by name. Returns parsed skill dict or None."""
        if skill_name in self._skill_cache:
            return self._skill_cache[skill_name]
        path = _find_skill(skill_name)
        if not path:
            logger.warning("[VECTOR][vc_skill] skill not found: {}", skill_name)
            return None
        parsed = _parse_skill(path)
        self._skill_cache[skill_name] = parsed
        logger.info("[VECTOR][vc_skill] loaded: {} ({} chars)", parsed["name"], len(parsed["system_prompt"]))
        return parsed

    def execute(self, skill_name: str, task_input: str, context: str = "") -> dict:
        """Execute a skill: load it, call LLM with its system prompt + task."""
        skill = self.load(skill_name)
        if not skill:
            return {"status": "error", "error": f"Skill '{skill_name}' not found"}

        try:
            from core.inference.vectorcode_llm import chat
            messages = [{"role": "system", "content": skill["system_prompt"]}]
            if context:
                messages.append({"role": "user", "content": f"[Context]\n{context}"})
            messages.append({"role": "user", "content": task_input})
            result = chat(model=self._model, messages=messages, timeout=45.0)
            return {"status": "ok", "skill": skill["name"], "result": result,
                    "steps": skill["steps"]}
        except Exception as e:
            logger.error("[VECTOR][vc_skill] execution failed: {}", e)
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    agent = SkillAgent()
    skills = agent.list_skills()
    print(f"[OK] list_skills: {len(skills)} skills available")
    if skills:
        print(f"  sample: {skills[0]['name']}")
    result = agent.execute("vector-coder", "Review this function for VECTOR compliance",
                           "def foo(): pass")
    print(f"[OK] execute: status={result['status']}")
    print("skill_agent.py OK")
