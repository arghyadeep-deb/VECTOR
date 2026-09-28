"""
PromptAgent — base class for .md-driven VECTOR district districts.

Loads a vectorcode/districts/*.md file, parses its system prompt and frontmatter,
and wraps it as a full VECTOR AgentBase citizen (HP, EpisodicMemory, governor routing).

LLM calls route through vectorcode_llm.chat() — local Ollama first, cloud fallback.

Usage:
    class RefactorCleaner(PromptAgent):
        def __init__(self):
            super().__init__("vector-refactor-cleaner.md", "refactor_cleaner_001", "coding")

The .md file IS the agent — Python just gives it VECTOR district infrastructure.
"""
from __future__ import annotations

import re
import asyncio
from pathlib import Path


from loguru import logger
from core.city.agent_base import AgentBase
from core.loop.context_engine import ContextEngine
from core.memory.episodic import EpisodicMemory
from core.config import CONFIG

# Location of all agent .md prompts — districts/ at codebase root
_AGENTS_DIR = Path(__file__).parent.parent.parent / "districts"


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
            logger.warning("[VECTOR][prompt_agent] .md not found: {} — agent has no personality", self._md_path)
            return {}, f"You are a VECTOR AI assistant. Your definition file ({self._md_path.name}) is missing."
        try:
            return _parse_md(self._md_path)
        except Exception as e:
            logger.error("[VECTOR][prompt_agent] failed to parse {}: {}", self._md_path.name, e)
            return {}, f"You are a VECTOR AI assistant. Your definition file ({self._md_path.name}) failed to parse: {e}"

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
        # Review finding (verified real by Claude, 2026-09-29): this is the shared LLM call site for
        # every PromptAgent-based district citizen (12 agents across coding/research/finance/qa/
        # governance/data_analytics) that never override run()/ask() -- it was missing RULE 1's
        # session_hydration_prompt() entirely. Fixed once here rather than per-agent.
        hydration = ContextEngine().session_hydration_prompt({"agent": self.name, "query": query[:200]})
        messages = [{"role": "system", "content": hydration}, {"role": "system", "content": self._system_prompt}]
        if context:
            messages.append({"role": "user", "content": f"[Context]\n{context}"})
        messages.append({"role": "user", "content": query})
        # KNOWN_ISSUES #24: this used to swallow the real exception into a
        # bare "" — run() then only ever surfaced the generic "Empty response
        # from LLM" no matter what actually went wrong (all providers
        # rate-limited, a single provider erroring, a timeout, ...).
        # chat() itself already retries across ~13 free-tier providers before
        # giving up (confirmed: groq/mistral/etc. cooldowns visible in the
        # live provider_client logs) — a naive extra retry here would just
        # double the worst-case latency without addressing the actual
        # capacity limits of a ₹0-forever free-tier stack. What IS worth
        # fixing: keeping the real failure reason around so run() can be
        # specific instead of generic when one is available.
        #
        # Follow-up (issue #24, latency pass): `timeout=` here is a
        # *per-provider* HTTP timeout (see vectorcode_llm.chat()'s own
        # docstring), not a ceiling on the whole call — chat() is a
        # blocking sync function that (a) tries the multi-provider
        # ProviderClient chain with its own internal `timeout + 15`
        # ceiling, then (b) on failure falls through to a legacy
        # gemini -> openrouter -> ollama chain at up to `timeout` seconds
        # each. Worst case with no outer bound: (timeout+15) + 3*timeout —
        # ~195s at the default 45s, matching the 148s+ real-world cases
        # this issue was opened for. governor.py's sibling LLM call sites
        # (_answer_conversationally, classify_chat_intent, commands.py's
        # _llm_answer) all already wrap their call in asyncio.wait_for()
        # for exactly this reason (issue #31) — this was the one call
        # site using that pattern that hadn't gotten it. The ceiling below
        # is timeout+35: enough slack to let the primary (well-optimized,
        # circuit-breaker-aware) ProviderClient path always reach its own
        # timeout+15 budget, plus room for one legacy-chain attempt if
        # that path genuinely fails — not the full 3-attempt legacy tail.
        # chat() itself can't be awaited (it's sync), so it's run in a
        # thread and wait_for wraps that, matching the same outer-deadline
        # shape as the other three call sites.
        self._last_ask_error: str = ""
        outer_ceiling = timeout + 35.0
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(chat, model=self._model, messages=messages, timeout=timeout),
                timeout=outer_ceiling,
            )
            if not result:
                self._last_ask_error = "all configured LLM providers returned empty (likely rate-limited)"
            return result
        except asyncio.TimeoutError:
            logger.warning("[VECTOR][prompt_agent] {} ask timed out (>{:.0f}s)", self.name, outer_ceiling)
            self._last_ask_error = f"reasoning engine still working after {outer_ceiling:.0f}s — provider chain likely saturated"
            return ""
        except Exception as e:
            logger.warning("[VECTOR][prompt_agent] {} ask failed: {}", self.name, e)
            self._last_ask_error = str(e)
            return ""

    async def run(self, task: dict) -> dict:
        """
        Default run: extract query from task, call ask(), return response.
        Subclasses can override for multi-step workflows.
        """
        # 2026-07-28: real chat dispatch (governor.py's _dispatch_to_district
        # -> agent.run(task)) puts the user's actual text at
        # task["params"]["query"] (see governor.py's own read of it at
        # ~line 1686), NOT top-level task["query"]. This base class only
        # checked the top-level keys, so any of the 12 PromptAgent-based
        # district agents (coding, research, finance, qa, governance,
        # data_analytics) that never override run() were handing the LLM a
        # stringified repr of the whole task dict — not the real question —
        # for every real conversational query. Same bug CLASS as issues
        # #1/#14/#15/#21/#33 (wrong/garbage default instead of the real
        # question), just a different shape (mangled input, not a wrong
        # action). Same precedence order used by the district-level fixes.
        query = (
            (task.get("params") or {}).get("query")
            or task.get("query")
            or task.get("prompt")
            or task.get("input")
            or (task.get("params") or {}).get("user_message")
            or task.get("text")
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
                reason = getattr(self, "_last_ask_error", "") or "Empty response from LLM"
                logger.warning("[VECTOR][prompt_agent] {} returned empty response ({})", self.name, reason)
                self.deduct_points(10, f"{self.name}_empty_response")
                return {"status": "error", "error": f"Empty response from LLM: {reason}", "agent": self.name}
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
