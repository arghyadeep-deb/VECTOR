"""System prompt assembly — identity, platform hints, skills, context files."""

from pathlib import Path
from typing import Optional

from vectorcode.src.context.vectormd import VectorMD


def build_system_prompt(
    identity: str = "You are VectorCode, a terminal-native coding agent.",
    *,
    personality: Optional[str] = None,
    skills_index: str = "",
    project_context: str = "",
    tool_list: str = "",
    platform_hints: str = "Platform: CLI terminal. Use markdown code fences.",
) -> str:
    """Assemble the system prompt from components.

    Order: identity -> personality -> project context -> skills -> tools -> platform
    """
    parts = [identity]

    if personality:
        parts.append(f"\n{personality}")

    if project_context:
        parts.append(f"\n{project_context}")

    if skills_index:
        parts.append(f"\nAvailable skills:\n{skills_index}")

    if tool_list:
        parts.append(f"\nAvailable tools:\n{tool_list}")

    parts.append(f"\n{platform_hints}")
    return "\n".join(parts)


def build_tool_list(tools: list[dict]) -> str:
    """Build a formatted tool list string from tool metadata."""
    lines = []
    for t in tools:
        name = t.get("name", "?")
        desc = t.get("description", "")[:80]
        lines.append(f"  {name} — {desc}")
    return "\n".join(lines)


def load_project_context(project_dir: Optional[Path] = None) -> str:
    """Load VECTOR.md project config if it exists."""
    if not project_dir:
        return ""
    return VectorMD(project_dir).as_system_block()
