"""MCP browser absorption tools."""

from loguru import logger

from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.security import mcp_secure_call as _mcp_secure_call


def add_browser_tools(mcp) -> None:
    """Expose browser absorption tools (auto-browser-main) to MCP clients.
    3 tools: browser_prune_dom, browser_list_auth_profiles, browser_save_auth_profile."""
    try:
        from core.browser.dom_pruner import get_dom_pruner as _get_pruner
        from core.browser.auth_profiles import get_auth_store as _get_store
        from core.browser.pii_scrub import scrub_text as _scrub_text
        from core.browser.governance import get_browser_governance as _get_governance
    except Exception as e:
        logger.warning(f"[VECTOR][mcp] browser tools unavailable: {e}")
        return

    @mcp.tool
    def browser_prune_dom(elements_json: str, task_goal: str = "", max_elements: int = 20) -> str:
        """Prune a raw DOM interactable-element list to the top-N most relevant for task_goal.
        elements_json: JSON array of element dicts (from browser observe).
        Returns pruned JSON array — reduces ~18k token observations to ~500."""
        if not _mcp_secure_call("browser_prune_dom", "browser", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            import json as _json
            elements = _json.loads(elements_json)
            pruner = _get_pruner()
            pruned = pruner.prune(elements, task_goal=task_goal, max_elements=max_elements)
            return _safe_json({"pruned": pruned, "count": len(pruned), "original_count": len(elements)})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def browser_list_auth_profiles() -> str:
        """List all saved named browser auth profiles (login-once, reuse-later)."""
        if not _mcp_secure_call("browser_list_auth_profiles", "browser", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            return _safe_json({"profiles": _get_store().list()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def browser_save_auth_profile(profile_name: str, state_json: str) -> str:
        """Save a Playwright storage state (cookies + localStorage) under profile_name.
        state_json: JSON string from `await context.storage_state()`.
        Returns saved profile metadata."""
        if not _mcp_secure_call("browser_save_auth_profile", "browser", {"profile": profile_name}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            import json as _json
            decision = _get_governance().classify(
                "save_auth_profile",
                inputs={"profile_name": profile_name},
            )
            if not decision.allowed:
                return _safe_json({
                    "error": "blocked by browser governance",
                    "level": decision.level,
                    "reason": decision.reason,
                })
            state = _json.loads(state_json)
            result = _get_store().save(profile_name, state)
            result["governance"] = {
                "level": decision.level,
                "requires_owner": decision.requires_owner,
                "reason": decision.reason,
            }
            return _safe_json(result)
        except Exception as e:
            return _safe_json({"error": str(e)})
