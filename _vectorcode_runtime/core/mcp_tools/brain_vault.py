"""MCP brain vault tools."""

from pathlib import Path

from loguru import logger


def add_brain_vault_tools(mcp) -> None:
    """Expose brain vault commands, skills, and agents to MCP clients (3 tools)."""
    import os as _os

    @mcp.tool
    async def run_command(command: str, params: str = "") -> str:
        """Run a brain/.claude/commands/ command by name. params is a JSON string."""
        try:
            from vectorcode.src.command_registry import get_command_registry
            import json as _json
            p = _json.loads(params) if params.strip() else {}
            reg = get_command_registry()
            result = await reg.execute(command, p)
            return str(result.get("result", result))
        except Exception as e:
            return f"Error running command '{command}': {e}"

    @mcp.tool
    def list_commands() -> str:
        """List all available brain commands from brain/.claude/commands/."""
        try:
            from vectorcode.src.command_registry import get_command_registry
            reg = get_command_registry()
            cmds = reg.list_commands()
            return "\n".join(f"/{c['name']}: {c['description']}" for c in cmds[:30])
        except Exception as e:
            return f"Error listing commands: {e}"

    @mcp.tool
    def list_skills() -> str:
        """List available brain skills from brain/.claude/skills/."""
        brain = str(Path.home() / "V.E.C.T.O.R Brain" / ".claude" / "skills")
        fallback = str(Path(__file__).parent.parent / "brain" / ".claude" / "skills")
        for skills_dir in [brain, fallback]:
            if _os.path.exists(skills_dir):
                skills = sorted(_os.listdir(skills_dir))
                return f"{len(skills)} skills available:\n" + "\n".join(skills[:50])
        return "Brain skills directory not accessible"

    logger.info("[VECTOR][mcp] Brain vault tools registered: run_command, list_commands, list_skills")
