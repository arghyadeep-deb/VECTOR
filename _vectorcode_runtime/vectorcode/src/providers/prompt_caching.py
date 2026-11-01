"""Prompt caching — Anthropic cache_control breakpoint management.

Manages up to 4 cache breakpoints per the Anthropic prompt caching spec:
  - Position 0: system prompt (cached if >= MIN_CACHEABLE_TOKENS)
  - Position 1: last tool definition (cached if combined tools >= MIN_CACHEABLE_TOKENS)
  - Positions 2-3: reserved for long user context injections (future use)

Reference: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
"""


import copy
from typing import Union

from loguru import logger

__all__ = ["PromptCacheManager", "get_prompt_cache_manager"]

_SINGLETON: "PromptCacheManager | None" = None


class PromptCacheManager:
    """Manages cache_control breakpoints for Anthropic prompt caching.

    Anthropic allows up to 4 cache breakpoints. We use:
      - Position 0: system prompt (always cache if > 1024 tokens)
      - Position 1: first few tool definitions (if tools list > 1024 tokens combined)
      - Positions 2-3: reserved for long user context injections

    All methods return new objects — originals are never mutated.
    """

    MIN_CACHEABLE_TOKENS = 1024  # Anthropic minimum cacheable block size
    MAX_BREAKPOINTS = 4

    # ------------------------------------------------------------------
    # Token estimation
    # ------------------------------------------------------------------

    def estimate_tokens(self, content) -> int:
        """Rough char/4 estimate of token count for arbitrary content."""
        if content is None:
            return 0
        if isinstance(content, str):
            return max(1, len(content) // 4)
        if isinstance(content, list):
            total = 0
            for block in content:
                if isinstance(block, dict):
                    total += self.estimate_tokens(
                        block.get("text") or block.get("content") or ""
                    )
                else:
                    total += self.estimate_tokens(str(block))
            return max(1, total)
        if isinstance(content, dict):
            return self.estimate_tokens(
                content.get("text") or content.get("content") or ""
            )
        return max(1, len(str(content)) // 4)

    # ------------------------------------------------------------------
    # Should-cache predicates
    # ------------------------------------------------------------------

    def should_cache_system(self, system: Union[str, list]) -> bool:
        """Returns True if the system prompt is large enough to be worth caching."""
        return self.estimate_tokens(system) >= self.MIN_CACHEABLE_TOKENS

    def should_cache_tools(self, tools: list[dict]) -> bool:
        """Returns True if the combined tools list is large enough to be worth caching."""
        if not tools:
            return False
        total = sum(
            self.estimate_tokens(str(t.get("input_schema", "")) + str(t.get("description", "")))
            for t in tools
        )
        return total >= self.MIN_CACHEABLE_TOKENS

    # ------------------------------------------------------------------
    # Core method
    # ------------------------------------------------------------------

    def apply_cache_control(
        self,
        system: Union[str, list, None],
        tools: Union[list[dict], None],
        messages: list[dict],
    ) -> tuple[Union[str, list, None], Union[list[dict], None], list[dict]]:
        """Apply cache_control breakpoints at appropriate positions.

        Breakpoint allocation:
          - Breakpoint 0 → system prompt (if large enough)
          - Breakpoint 1 → last tool definition (if tools combined large enough)

        Args:
            system:   System prompt as string or list of content blocks.
            tools:    List of tool definition dicts.
            messages: Conversation message list.

        Returns:
            Tuple of (system_with_cache, tools_with_cache, messages_with_cache).
            Messages are returned unchanged (future: inject context breakpoints here).
            Originals are never mutated.
        """
        breakpoints_used = 0
        out_system = system
        out_tools = tools

        # --- Breakpoint 0: system prompt ---
        if system is not None and breakpoints_used < self.MAX_BREAKPOINTS:
            if self.should_cache_system(system):
                out_system = self._apply_cache_to_system(system)
                breakpoints_used += 1
                logger.debug(
                    f"[prompt_caching] system cache breakpoint applied "
                    f"(~{self.estimate_tokens(system)} tokens)"
                )
            else:
                logger.debug(
                    f"[prompt_caching] system prompt too small to cache "
                    f"(~{self.estimate_tokens(system)} tokens < {self.MIN_CACHEABLE_TOKENS})"
                )

        # --- Breakpoint 1: last tool definition ---
        if tools and breakpoints_used < self.MAX_BREAKPOINTS:
            if self.should_cache_tools(tools):
                out_tools = self._apply_cache_to_tools(tools)
                breakpoints_used += 1
                logger.debug(
                    f"[prompt_caching] tools cache breakpoint applied "
                    f"({len(tools)} tools)"
                )
            else:
                logger.debug(
                    f"[prompt_caching] tools list too small to cache"
                )

        # Messages returned as-is (breakpoints 2-3 reserved for future use)
        return out_system, out_tools, messages

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_cache_to_system(
        self, system: Union[str, list]
    ) -> Union[str, list]:
        """Return system with cache_control on the last content block.

        - str  → convert to list with one text block + cache_control
        - list → deep-copy and add cache_control to last element
        """
        _cache_mark = {"cache_control": {"type": "ephemeral"}}

        if isinstance(system, str):
            return [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        # list — deep-copy and annotate the last element
        result = copy.deepcopy(system)
        if result:
            last = result[-1]
            if isinstance(last, dict):
                last["cache_control"] = {"type": "ephemeral"}
        return result

    def _apply_cache_to_tools(self, tools: list[dict]) -> list[dict]:
        """Return tools with cache_control added to the last tool definition."""
        result = copy.deepcopy(tools)
        if result:
            last = result[-1]
            if isinstance(last, dict):
                last["cache_control"] = {"type": "ephemeral"}
        return result

    # ------------------------------------------------------------------
    # Strip helper (for non-Anthropic providers)
    # ------------------------------------------------------------------

    def strip_cache_control(self, messages: list[dict]) -> list[dict]:
        """Remove all cache_control keys recursively from message dicts.

        Use this when routing to non-Anthropic providers that don't
        understand cache_control.
        """
        return [self._strip_dict(copy.deepcopy(m)) for m in messages]

    def _strip_dict(self, obj):
        """Recursively remove cache_control from any nested structure."""
        if isinstance(obj, dict):
            obj.pop("cache_control", None)
            for k, v in obj.items():
                obj[k] = self._strip_dict(v)
        elif isinstance(obj, list):
            obj = [self._strip_dict(item) for item in obj]
        return obj


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

def get_prompt_cache_manager() -> PromptCacheManager:
    """Return the module-level singleton PromptCacheManager."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = PromptCacheManager()
        logger.debug("[prompt_caching] PromptCacheManager singleton created")
    return _SINGLETON


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mgr = get_prompt_cache_manager()
    assert mgr is get_prompt_cache_manager(), "Singleton must return same instance"

    # --- should_cache_system ---
    short_sys = "Be helpful."
    long_sys = "You are VECTOR. " * 300  # ~4800 chars → ~1200 tokens
    assert not mgr.should_cache_system(short_sys), "Short system should not cache"
    assert mgr.should_cache_system(long_sys), "Long system should cache"

    # --- apply_cache_control: string system ---
    sys_out, tools_out, msgs_out = mgr.apply_cache_control(long_sys, None, [])
    assert isinstance(sys_out, list), "String system should be converted to list"
    assert sys_out[0].get("cache_control") == {"type": "ephemeral"}, (
        "cache_control must be present on system block"
    )

    # --- apply_cache_control: list system ---
    list_sys = [{"type": "text", "text": "You are VECTOR. " * 300}]
    sys_out2, _, _ = mgr.apply_cache_control(list_sys, None, [])
    assert isinstance(sys_out2, list)
    assert sys_out2[-1].get("cache_control") == {"type": "ephemeral"}, (
        "cache_control must be applied to last block of list system"
    )

    # --- original not mutated ---
    assert "cache_control" not in list_sys[0], "Original system list must not be mutated"

    # --- apply_cache_control: tools ---
    big_tools = [
        {
            "name": f"tool_{i}",
            "description": "Does something important. " * 50,
            "input_schema": {"type": "object", "properties": {}},
        }
        for i in range(5)
    ]
    _, tools_out2, _ = mgr.apply_cache_control(long_sys, big_tools, [])
    assert tools_out2 is not None
    assert tools_out2[-1].get("cache_control") == {"type": "ephemeral"}, (
        "cache_control must be applied to last tool"
    )
    assert "cache_control" not in big_tools[-1], "Original tools must not be mutated"

    # --- strip_cache_control ---
    tagged_msgs = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hello", "cache_control": {"type": "ephemeral"}}
            ],
        }
    ]
    stripped = mgr.strip_cache_control(tagged_msgs)
    assert "cache_control" not in stripped[0]["content"][0], (
        "cache_control must be stripped from messages"
    )
    # Original untouched
    assert "cache_control" in tagged_msgs[0]["content"][0], (
        "Original must not be mutated by strip_cache_control"
    )

    # --- short system: no cache breakpoint ---
    short_out, _, _ = mgr.apply_cache_control("Be brief.", None, [])
    assert short_out == "Be brief.", "Short system should pass through unchanged as string"

    print("PASS: prompt_caching.py OK")
