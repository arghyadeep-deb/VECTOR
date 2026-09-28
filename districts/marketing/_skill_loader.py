"""Shared skill loader and mixin for VECTOR marketing district agents.

Usage:
    from districts.marketing._skill_loader import load_skill, SkillMixin

    class MyAgent(AgentBase, SkillMixin):
        def __init__(self):
            super().__init__(...)
            self._skill_prompt = load_skill("ads", "analytics")

        async def some_task(self, prompt: str) -> str:
            return self._chat(prompt)   # skill context auto-prepended
"""
import sys
from pathlib import Path

from loguru import logger

_SKILLS_DIR = Path(__file__).parent / "skills"


def load_skill(*names: str) -> str:
    """Load one or more skill .md files and return combined expert prompt."""
    parts: list[str] = []
    for name in names:
        for filename in ("SKILL.md", "skill.md", "README.md"):
            p = _SKILLS_DIR / name / filename
            if p.exists():
                text = p.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(text)
                break
        else:
            logger.debug(f"[VECTOR][skill_loader] skill '{name}' not found in {_SKILLS_DIR}")
    return "\n\n---\n\n".join(parts)


class SkillMixin:
    """
    Mixin for marketing agents that prepends expert skill context to every LLM call.
    Set self._skill_prompt in __init__ after calling load_skill().
    Then use self._chat(prompt) instead of calling chat() directly.
    """

    _skill_prompt: str = ""
    _model: str = "vector-focus"

    def _chat(self, prompt: str, timeout: float = 25.0) -> str:
        """Synchronous chat() with session hydration (RULE 1) and skill prompt
        prepended as system messages."""
        from core.inference.vectorcode_llm import chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt({"query": prompt})
        messages: list[dict] = [{"role": "system", "content": self._with_skill_system(hydration)}]
        messages.append({"role": "user", "content": prompt})
        return chat(model=self._model, messages=messages, timeout=timeout)

    async def _achat(self, prompt: str, timeout: float = 25.0) -> str:
        """Async chat() with skill prompt prepended as system message."""
        import asyncio
        return await asyncio.to_thread(self._chat, prompt, timeout)

    def _build_messages(self, prompt: str) -> list[dict]:
        """Build messages list with skill context prepended."""
        messages: list[dict] = []
        if self._skill_prompt:
            messages.append({"role": "system", "content": self._skill_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _with_skill_system(self, hydration: str) -> str:
        """Prepend skill prompt to an existing hydration/system string."""
        if self._skill_prompt:
            return f"{self._skill_prompt}\n\n---\n\n{hydration}"
        return hydration

    async def answer_marketing_question(self, query: str) -> str:
        """Answer a free-text/unmatched-task_type question, grounded in this
        agent's own loaded skill context (same design-district #33 fix
        pattern: real content instead of a wrong hardcoded default action).
        Each of the 5 marketing agents shares this one implementation via
        SkillMixin rather than duplicating it."""
        prompt = (
            f"The owner asked: {query}\n\n"
            "Answer using your loaded expert context above. Be concrete and "
            "specific to what was actually asked — do not fall back to a "
            "generic template or unrelated example."
        )
        try:
            return await self._achat(prompt, timeout=45.0) or (
                "I don't have enough context to answer that specifically — "
                "try asking with more detail."
            )
        except Exception as e:
            logger.warning(f"[VECTOR][skill_loader] answer_marketing_question failed: {e}")
            return "I ran into a problem answering that — try again in a moment."


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sample = load_skill("ads", "seo-audit")
    print(f"✅ skill_loader OK — loaded {len(sample)} chars for ads+seo-audit")
