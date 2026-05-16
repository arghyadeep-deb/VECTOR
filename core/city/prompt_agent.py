"""
PromptAgent — base class for .md-driven VECTOR district agents.

Loads a vectorcode/agents/*.md file, parses its system prompt and frontmatter,
and wraps it as a full VECTOR AgentBase citizen (HP, EpisodicMemory, governor routing).

LLM calls route through vectorcode_llm.chat() — local Ollama first, cloud fallback.

Usage:
    class RefactorCleaner(PromptAgent):
        def __init__(self):
            super().__init__("vector-refactor-cleaner.md", "refactor_cleaner_001", "coding")

The .md file IS the agent — Python just gives it VECTOR district infrastructure.
"""
from __future__ import annotations

import sys
import re
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.config import CONFIG

# Location of all agent .md prompts — colocated with Python agents in districts
_AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"


def _parse_md(path: Path) -> tuple[dict, str]:
    """Parse frontmatter + body from a YAML-frontmatter .md file.
    Returns (frontmatter_dict, body_str).
    """
    text = path.read_text(encoding="utf-8", errors="replace")

    # Strip VECTOR-INGESTED comment block at top if present
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()

    frontmatter: dict = {}
    body = text

    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            yaml_block = text[3:end].strip()
            body = text[end + 3:].strip()
            for line in yaml_block.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    frontmatter[k.strip()] = v.strip().strip('"').strip("'")

    return frontmatter, body


class PromptAgent(AgentBase):
    """
    Base class for agents whose behavior is defined by a vectorcode .md file.

    Subclasses just specify which .md file to load and which district they
    belong to. All LLM interaction uses the .md system prompt + vectorcode_llm.
    """

    def __init__(self, md_filename: str, agent_id: str, district: str):
        self._md_path = self._resolve_md_path(md_filename)
        self._frontmatter, self._system_prompt = self._load_definition()

        name = self._frontmatter.get("name", md_filename.replace(".md", "").replace("-", "_"))
        model_hint = self._frontmatter.get("model", CONFIG.get("models", {}).get("reasoning", "vector-reasoning"))

        super().__init__(agent_id=agent_id, name=name, district=district)
        self._model = model_hint
        self._memory: EpisodicMemory | None = None
        logger.info("[VECTOR][prompt_agent] {} loaded ({} chars system prompt)",
                    name, len(self._system_prompt))

    @staticmethod
    def _resolve_md_path(md_filename: str) -> Path:
        """Find the .md file — checks flat location first, then all district subfolders."""
        # Direct path given (absolute or relative)
        direct = Path(md_filename)
        if direct.is_absolute() and direct.exists():
            return direct
        # Flat in agents dir (legacy)
        flat = _AGENTS_DIR / md_filename
        if flat.exists():
            return flat
        # Search district subfolders
        for subdir in _AGENTS_DIR.iterdir():
            if subdir.is_dir():
                candidate = subdir / md_filename
                if candidate.exists():
                    return candidate
        return flat  # Return non-existent path; caller handles missing

    def _load_definition(self) -> tuple[dict, str]:
        """Load and parse the .md definition file."""
        if not self._md_path.exists():
            logger.warning("[VECTOR][prompt_agent] .md not found: {}", self._md_path)
            return {}, "You are a helpful VECTOR AI assistant."
        try:
            return _parse_md(self._md_path)
        except Exception as e:
            logger.error("[VECTOR][prompt_agent] failed to parse {}: {}", self._md_path.name, e)
            return {}, "You are a helpful VECTOR AI assistant."

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    @property
    def description(self) -> str:
        return self._frontmatter.get("description", self.name)

    async def ask(self, query: str, context: str = "", timeout: float = 45.0) -> str:
        """
        Core method: call LLM with this agent's system prompt + query.
        Routes through vectorcode_llm (Ollama → Gemini → Anthropic chain).
        """
        from core.inference.vectorcode_llm import chat
        messages = [{"role": "system", "content": self._system_prompt}]
        if context:
            messages.append({"role": "user", "content": f"[Context]\n{context}"})
        messages.append({"role": "user", "content": query})
        try:
            result = chat(model=self._model, messages=messages, timeout=timeout)
            return result
        except Exception as e:
            logger.warning("[VECTOR][prompt_agent] {} ask failed: {}", self.name, e)
            return ""

    async def run(self, task: dict) -> dict:
        """
        Default run: extract query from task, call ask(), return response.
        Subclasses can override for multi-step workflows.
        """
        query = (
            task.get("query")
            or task.get("prompt")
            or task.get("input")
            or str(task)
        )
        context = task.get("context", "")
        timeout = float(task.get("timeout", 45.0))

        try:
            response = await self.ask(query, context=context, timeout=timeout)
            if response:
                self._get_memory().store(
                    event_type=f"{self.name}_response",
                    content=f"Q: {query[:80]} → {len(response)} chars",
                    tags=[self.district, self.name.lower()],
                    source=self.name,
                )
                self.award_points(20, f"{self.name}_task_done")
                return {"status": "ok", "response": response, "agent": self.name}
            else:
                logger.warning("[VECTOR][prompt_agent] {} returned empty response", self.name)
                self.deduct_points(10, f"{self.name}_empty_response")
                return {"status": "error", "error": "Empty response from LLM", "agent": self.name}
        except Exception as e:
            logger.error("[VECTOR][prompt_agent] {} run error: {}", self.name, e)
            self.deduct_points(30, f"{self.name}_run_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        # Test loading a known .md file
        class _TestAgent(PromptAgent):
            def __init__(self):
                super().__init__("vector-refactor-cleaner.md", "test_001", "coding")

        agent = _TestAgent()
        print(f"[OK] loaded: name={agent.name} district={agent.district}")
        print(f"[OK] system_prompt: {len(agent._system_prompt)} chars")
        print(f"[OK] description: {agent.description[:80]}")
        print(f"[OK] model: {agent._model}")
        print("prompt_agent.py OK")

    asyncio.run(_smoke())
