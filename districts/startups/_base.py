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
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        """Call the LLM with RULE 1 session hydration. Shared across all startup agents."""
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        try:
            hydration = ContextEngine().session_hydration_prompt()
        except Exception as _e:
            logger.debug("[VECTOR][startups] hydration failed: {}", _e)
            hydration = ""
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def _parse_json_response(self, text: str, fallback: dict) -> dict:
        """Extract the first JSON object from an LLM response, with fallback."""
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except (json.JSONDecodeError, AttributeError):
            pass
        return fallback

    def _store_result(
        self,
        event_type: str,
        content: str,
        tags: list[str],
        result: dict,
    ) -> None:
        """Persist an agent result to episodic memory."""
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
