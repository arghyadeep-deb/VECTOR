# DORMANT (2026-09-24, docs/design/core-module-triage.md): not imported by the running VECTOR.
# Superseded by vectorcode_llm / provider_client via AgentBase. Kept on purpose (personal-use build); do not add a second live path --
# route through the existing mechanism so the Governor and PermissionGateway stay the only way in.
"""
DistrictLLM — vectorcode-backed LLM caller with auto .md system prompt injection.

Each VECTOR district agent gets a DistrictLLM that:
  1. Finds the best matching .md file in its district folder
  2. Loads the system prompt from that .md
  3. Routes all LLM calls through vectorcode_llm (Ollama → Gemini → Anthropic chain)

AgentBase exposes self._district_llm so every agent gets this for free.
Agents that already build their own system prompts are not overridden —
the .md context is only injected when no system message is already present.
"""
from __future__ import annotations

__all__ = [
    "DistrictLLM",
    "load_district_prompt",
]


import re
from pathlib import Path
from functools import lru_cache


from loguru import logger
from core.resilience.circuit_breaker import CircuitBreakerOpenError
from core.breaker_registry import get_registry

# Root of all district agent folders
_DISTRICTS_ROOT = Path(__file__).parent.parent.parent / "agents" / "districts"

# Cached system prompt storage: (district, agent_name) → system_prompt str
_prompt_cache: dict[tuple[str, str], str] = {}


def _slug(name: str) -> str:
    """Normalise to lowercase-hyphenated for fuzzy matching."""
    return re.sub(r"[_\s]+", "-", name.lower().strip())


def _score_match(md_stem: str, agent_slug: str) -> int:
    """Return how well a .md filename matches an agent name. Higher = better."""
    md_slug = _slug(md_stem)
    if agent_slug == md_slug:
        return 100
    if agent_slug in md_slug:
        return 80
    # partial word match — count shared tokens
    a_tokens = set(agent_slug.split("-"))
    m_tokens = set(md_slug.split("-"))
    common = len(a_tokens & m_tokens)
    return common * 10 if common > 1 else 0


def _parse_md_body(path: Path) -> str:
    """Extract body (system prompt) from a frontmatter .md file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        # Strip HTML comment block
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()
        # Strip YAML frontmatter
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                text = text[end + 3:].strip()
        return text
    except Exception as e:
        logger.debug("[VECTOR][district_llm] failed to read {}: {}", path.name, e)
        return ""


def load_district_prompt(district: str, agent_name: str) -> str:
    """Find and return the best matching .md system prompt for an agent.

    Searches districts/<district>/*.md and returns the body of the
    best-scoring match. Returns empty string if nothing found.
    Results are cached in-process.
    """
    cache_key = (district, agent_name)
    if cache_key in _prompt_cache:
        return _prompt_cache[cache_key]

    district_dir = _DISTRICTS_ROOT / district
    if not district_dir.exists():
        _prompt_cache[cache_key] = ""
        return ""

    agent_slug = _slug(agent_name)
    best_score = 0
    best_prompt = ""

    for md_file in district_dir.glob("*.md"):
        score = _score_match(md_file.stem, agent_slug)
        if score > best_score:
            body = _parse_md_body(md_file)
            if body:
                best_score = score
                best_prompt = body

    if best_prompt:
        logger.debug(
            "[VECTOR][district_llm] {} → matched .md (score={}, {} chars)",
            agent_name, best_score, len(best_prompt),
        )
    _prompt_cache[cache_key] = best_prompt
    return best_prompt


class DistrictLLM:
    """
    LLM caller for a specific district agent.

    - Loads matching .md system prompt from districts/<district>/
    - Routes calls through vectorcode_llm (Ollama → free cloud → paid cloud)
    - Injects system prompt only when caller hasn't already set one
    """

    def __init__(self, district: str, agent_name: str):
        self.district = district
        self.agent_name = agent_name
        self._system_prompt: str | None = None  # lazy-loaded on first call

    def _get_system_prompt(self) -> str:
        if self._system_prompt is None:
            self._system_prompt = load_district_prompt(self.district, self.agent_name)
        return self._system_prompt

    def chat(
        self,
        model: str,
        messages: list[dict],
        timeout: float = 30.0,
        *,
        inject_md: bool = True,
        allow_cloud: bool = True,
    ) -> str:
        """
        Call LLM through vectorcode's multi-provider chain.

        Args:
            model:        Ollama model tag or cloud model ID
            messages:     Standard chat messages list
            timeout:      Per-provider HTTP timeout
            inject_md:    If True, prepend .md system prompt when no system
                          message is already present (default True)
            allow_cloud:  If False, stay strictly local (Ollama only)
        """
        from core.inference.vectorcode_llm import chat as _vc_chat

        final_messages = list(messages)

        if inject_md:
            has_system = any(m.get("role") == "system" for m in messages)
            if not has_system:
                prompt = self._get_system_prompt()
                if prompt:
                    final_messages = [{"role": "system", "content": prompt}] + final_messages

        try:
            import asyncio as _asyncio
            cb = get_registry().get("district_llm")
            if cb:
                _coro = cb.call(lambda: _vc_chat(
                    model=model,
                    messages=final_messages,
                    timeout=timeout,
                    allow_cloud=allow_cloud,
                ))
                try:
                    return _asyncio.run(_coro)
                except RuntimeError:
                    _coro.close()
            return _vc_chat(
                model=model,
                messages=final_messages,
                timeout=timeout,
                allow_cloud=allow_cloud,
            )
        except (CircuitBreakerOpenError, RuntimeError):
            return _vc_chat(
                model=model,
                messages=final_messages,
                timeout=timeout,
                allow_cloud=allow_cloud,
            )

    def chat_no_md(self, model: str, messages: list[dict], timeout: float = 30.0) -> str:
        """Call LLM without .md injection — for when agent has its own system prompt."""
        return self.chat(model=model, messages=messages, timeout=timeout, inject_md=False)

    def __repr__(self) -> str:
        loaded = self._system_prompt is not None
        return (
            f"DistrictLLM(district={self.district!r}, agent={self.agent_name!r}, "
            f"md_loaded={loaded})"
        )


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    # Smoke test — check a few districts
    tests = [
        ("coding", "code_reviewer"),
        ("marketing", "seo_specialist"),
        ("security", "threat_detection_engineer"),
        ("qa", "reality_checker"),
        ("finance", "financial_analyst"),
    ]
    for district, agent in tests:
        prompt = load_district_prompt(district, agent)
        llm = DistrictLLM(district, agent)
        print(f"[OK] {district}/{agent}: {len(prompt)} chars system prompt — {llm}")

    print("district_llm.py OK")
