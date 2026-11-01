"""
Shared base class for all startups district agents.
Extracts the ~80% boilerplate that was copy-pasted across
market_scanner, idea_validator, competitor_spy, revenue_modeler.
"""
import json
import re
import uuid
import datetime
from typing import Optional

from loguru import logger

from core.city.agent_base import AgentBase
from core.config import CONFIG
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync


class StartupAgentBase(AgentBase):
    """Base class for all startups district agents."""

    def __init__(self, name: str):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name=name,
            district="startups",
            generation=1,
        )
        try:
            self.memory: EpisodicMemory | None = EpisodicMemory()
        except Exception as _e:
            logger.warning("[VECTOR][startups] episodic memory unavailable ({}): {}", name, _e)
            self.memory = None
        self.obsidian = ObsidianSync()

    def _call_ollama(self, prompt: str, model: Optional[str] = None, temperature: float = 0.7) -> str:
        """Call the LLM with RULE 1 session hydration + PromptLibrary system prompt."""
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        from core.prompt_library import get_library as _gl

        try:
            hydration = ContextEngine().session_hydration_prompt()
        except Exception as _e:
            logger.debug("[VECTOR][startups] hydration failed: {}", _e)
            hydration = ""

        agent_slug = re.sub(r"(?<!^)(?=[A-Z])", "_", self.name).lower()
        lib_sys = _gl().get_for_agent(agent_slug) or ""
        sys_content = lib_sys or hydration

        messages = []
        if sys_content:
            messages.append({"role": "system", "content": sys_content})
        messages.append({"role": "user", "content": prompt})

        return ollama_chat(
            model=model or self.model,
            messages=messages,
            timeout=120,
            temperature=temperature,
        )

    def _parse_json_response(self, text: str, fallback: dict) -> dict:
        """Extract the first JSON object from an LLM response, with fallback."""
        parsed = self._extract_json(text)
        return parsed if parsed is not None else fallback

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """First JSON object in an LLM response, or None when the LLM failed
        (empty reply) or returned unparseable text. Callers use None to fail
        closed instead of presenting canned fallback data as a real result."""
        try:
            match = re.search(r'\{.*\}', text or "", re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    @staticmethod
    def _llm_error(what: str, **extra) -> dict:
        """Uniform failure result: never mistaken for a successful scan/model."""
        logger.warning("[VECTOR][startups] {}: LLM returned no parseable result", what)
        return {"status": "error", "error": f"{what}: LLM unavailable or returned unparseable output", **extra}

    @staticmethod
    def _num(value, default: float = 0.0) -> float:
        """Coerce an LLM-supplied number (may be str/None/NaN) to a finite float."""
        try:
            f = float(value)
        except (TypeError, ValueError):
            return default
        return f if f == f and f not in (float("inf"), float("-inf")) else default

    def _store_result(
        self,
        event_type: str,
        content: str,
        tags: list[str],
        result: dict,
    ) -> None:
        """Persist an agent result to episodic memory."""
        if self.memory is None:
            return
        try:
            self.memory.store(
                event_type=event_type,
                content=content,
                tags=tags,
                context=result,
                source=self.name,
            )
        except Exception as _e:
            logger.warning("[VECTOR][startups] memory store failed: {}", _e)

    @staticmethod
    def _now_iso() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    async def answer_startup_question(self, query: str, extra_context: str = "") -> str:
        """Answer a free-text/unmatched-task_type question, grounded in the
        live regime and whatever real per-agent state the caller passes in
        (scan history, competitor profiles, validated ideas, revenue
        models — subclasses have their own real state, this stays generic).
        Same design-district #33 fix pattern: real content instead of a
        wrong hardcoded default action. Shared here so market_scanner,
        competitor_spy, idea_validator, and revenue_modeler don't each
        duplicate it."""
        regime = "unknown"
        try:
            from core.brain.blueprint_doctrine import get_regime
            regime = get_regime()
        except Exception:
            pass

        context = f"Current market regime: {regime}."
        if extra_context:
            context += f"\n{extra_context}"

        prompt = (
            f"You are VECTOR's {self.name} in the startups district. Answer the "
            f"owner's question using this real context — do not invent data you "
            f"don't have:\n\n{context}\n\nQuestion: {query}\n\nBe concrete and specific."
        )
        try:
            result = self._call_ollama(prompt, temperature=0.6)
            return result or context
        except Exception as e:
            logger.warning("[VECTOR][startups] answer_startup_question failed ({}): {}", self.name, e)
            return context

    async def answer_startup_task(self, query: str, extra_context: str = "") -> dict:
        """run() wrapper: a failed/empty LLM answer is an error, not status ok
        with the raw context echoed back as if it were the answer."""
        try:
            from core.brain.blueprint_doctrine import get_regime
            regime = get_regime()
        except Exception:
            regime = "unknown"
        context = f"Current market regime: {regime}."
        if extra_context:
            context += f"\n{extra_context}"
        prompt = (
            f"You are VECTOR's {self.name} in the startups district. Answer the "
            f"owner's question using this real context — do not invent data you "
            f"don't have:\n\n{context}\n\nQuestion: {query}\n\nBe concrete and specific."
        )
        try:
            answer = self._call_ollama(prompt, temperature=0.6)
        except Exception as e:
            logger.warning("[VECTOR][startups] answer failed ({}): {}", self.name, e)
            answer = ""
        if not answer or not answer.strip():
            return {"status": "error", "error": "LLM unavailable: no answer generated"}
        return {"status": "ok", "response": answer}
