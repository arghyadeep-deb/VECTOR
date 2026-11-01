"""Toolset manager — enable/disable groups of tools per session or task type.

Usage from the REPL (repl.py should call get_toolset_manager()):
  /tools              → print status() + list_toolsets()
  /tools coding       → get_toolset_manager().enable("coding")
  /tools full         → get_toolset_manager().enable("full")   # re-enable all

The agent loop should call:
  mgr = get_toolset_manager()
  if mgr.is_allowed(tool_name):
      run_tool(tool_name, ...)
"""

import sys
from pathlib import Path
from loguru import logger

from typing import Optional

# ── Built-in toolsets ─────────────────────────────────────────────────────────

TOOLSETS: dict[str, list[str]] = {
    "coding": [
        "read_file",
        "write_file",
        "edit_file",
        "bash",
        "git_commit",
        "git_diff",
        "search_files",
        "create_checkpoint",
        "restore_checkpoint",
    ],
    "research": [
        "web_search",
        "web_extract",
        "read_file",
        "write_file",
    ],
    "readonly": [
        "read_file",
        "search_files",
        "bash",   # bash is read-only by convention in this toolset
    ],
    "minimal": [
        "read_file",
        "write_file",
        "bash",
    ],
    "full": [],  # empty list = all tools enabled (no restriction)
    "voice": [
        "text_to_speech",
        "speech_to_text",
        "read_file",
    ],
    "media": [
        "generate_image",
        "describe_image",
        "text_to_speech",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────

class ToolsetManager:
    """
    Maintains the set of currently allowed tool names for the session.

    Semantics:
      • _active is empty  → ALL tools are allowed  ("full" / unrestricted mode)
      • _active non-empty → ONLY tools in _active are allowed

    This makes the common case ("all tools") zero-cost and explicit restrictions
    additive from there.
    """

    def __init__(self) -> None:
        self._active: set[str] = set()   # empty = all enabled
        self._mode: str = "full"

    # ── Public API ────────────────────────────────────────────────────────────

    def enable(self, toolset_name: str) -> dict:
        """Switch to a named toolset (replacing the current restriction).

        Calling enable("full") lifts all restrictions.

        Returns:
            {"toolset": name, "tools": [...]}
        """
        if toolset_name not in TOOLSETS:
            known = list(TOOLSETS.keys())
            logger.warning(
                "[VECTOR][toolset] unknown toolset '%s'. Known: %s", toolset_name, known
            )
            return {"error": f"Unknown toolset '{toolset_name}'", "known": known}

        tools = TOOLSETS[toolset_name]
        if toolset_name == "full" or not tools:
            # full = no restriction
            self._active = set()
            self._mode = "full"
        else:
            self._active = set(tools)
            self._mode = toolset_name

        logger.info(
            "[VECTOR][toolset] activated '%s' — %s",
            self._mode,
            f"{len(self._active)} tool(s)" if self._active else "all tools allowed",
        )
        return {"toolset": self._mode, "tools": sorted(self._active)}

    def disable(self, toolset_name: str) -> None:
        """Remove a toolset's tools from the current active set.

        If no tools remain, reverts to "full" (unrestricted).
        """
        if toolset_name not in TOOLSETS:
            logger.warning("[VECTOR][toolset] disable: unknown toolset '%s'", toolset_name)
            return
        to_remove = set(TOOLSETS.get(toolset_name, []))
        self._active -= to_remove
        if not self._active:
            self._mode = "full"
        logger.info(
            "[VECTOR][toolset] disabled toolset '%s', %d tool(s) remain active",
            toolset_name, len(self._active),
        )

    def add_tool(self, tool_name: str) -> None:
        """Add a single tool to the active (allowed) set.

        If currently in "full" mode this starts a restriction with just this tool,
        which is probably not what the caller wants — log a warning.
        """
        if not self._active:
            logger.warning(
                "[VECTOR][toolset] add_tool('%s') called in 'full' mode — "
                "this will restrict to ONLY this tool. Use enable() instead.",
                tool_name,
            )
        self._active.add(tool_name)
        logger.debug("[VECTOR][toolset] added tool: %s", tool_name)

    def remove_tool(self, tool_name: str) -> None:
        """Remove a single tool from the active set."""
        self._active.discard(tool_name)
        if not self._active:
            self._mode = "full"
        logger.debug("[VECTOR][toolset] removed tool: %s", tool_name)

    def get_active_tools(self) -> set[str]:
        """Return the active set. Empty set means ALL tools are allowed."""
        return set(self._active)

    def is_allowed(self, tool_name: str) -> bool:
        """Return True if the tool is permitted in the current mode.

        Empty _active → all tools allowed.
        """
        if not self._active:
            return True
        return tool_name in self._active

    def list_toolsets(self) -> dict[str, list[str]]:
        """Return the TOOLSETS dict for display."""
        return dict(TOOLSETS)

    def status(self) -> dict:
        """Return current mode, active tools count, and toolset name."""
        return {
            "mode": self._mode,
            "restricted": bool(self._active),
            "active_tool_count": len(self._active) if self._active else "all",
            "active_tools": sorted(self._active) if self._active else [],
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_toolset_manager: Optional[ToolsetManager] = None


def get_toolset_manager() -> ToolsetManager:
    """Return the process-wide singleton ToolsetManager."""
    global _toolset_manager
    if _toolset_manager is None:
        _toolset_manager = ToolsetManager()
    return _toolset_manager


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    # ── Task 1: CronManager smoke (imported here to keep a single __main__ per spec) ──
    from tools.cron_tools import CronManager

    with tempfile.TemporaryDirectory() as tmp:
        storage = Path(tmp) / "cron_jobs.json"
        cm = CronManager(storage_path=storage)

        r = cm.add_job("test_job", "every 1m", "echo hello")
        assert r["status"] == "created", r

        jobs = cm.list_jobs()
        assert len(jobs) == 1, f"expected 1, got {len(jobs)}"
        assert jobs[0]["name"] == "test_job"

        rd = cm.remove_job("test_job")
        assert rd["removed"] is True, rd
        assert len(cm.list_jobs()) == 0

        logger.info("[VECTOR][toolset] CronManager sub-smoke OK")

    # ── Task 2: ToolsetManager smoke ──────────────────────────────────────────
    mgr = ToolsetManager()

    # initial state: full (no restriction)
    assert mgr.is_allowed("read_file") is True
    assert mgr.is_allowed("generate_image") is True
    s = mgr.status()
    assert s["mode"] == "full"
    assert s["restricted"] is False

    # enable "coding"
    result = mgr.enable("coding")
    assert result["toolset"] == "coding"
    assert "read_file" in result["tools"]

    assert mgr.is_allowed("read_file") is True
    assert mgr.is_allowed("generate_image") is False, (
        "generate_image should NOT be allowed in coding toolset"
    )

    # check status
    s2 = mgr.status()
    assert s2["mode"] == "coding"
    assert s2["restricted"] is True

    # add a single extra tool
    mgr.add_tool("generate_image")
    assert mgr.is_allowed("generate_image") is True

    # remove it
    mgr.remove_tool("generate_image")
    assert mgr.is_allowed("generate_image") is False

    # switch back to full
    mgr.enable("full")
    assert mgr.is_allowed("generate_image") is True
    assert mgr.status()["restricted"] is False

    # list_toolsets
    ts = mgr.list_toolsets()
    assert "coding" in ts
    assert "research" in ts
    assert "full" in ts

    # singleton
    s1 = get_toolset_manager()
    s2 = get_toolset_manager()
    assert s1 is s2, "get_toolset_manager() must return the same instance"

    logger.info("[VECTOR][toolset] ToolsetManager smoke OK")
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ tools/toolset.py OK")
