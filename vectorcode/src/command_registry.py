"""
VectorCode Command Registry — loads brain commands and makes them callable.
Every brain/.claude/commands/*.md becomes a VectorCode command callable via:
  - Governor task dispatch: {"type": "run_command", "params": {"command": "research"}}
  - MCP tool: run_command(name, params)
  - Direct Python: CommandRegistry().execute("research", {"topic": "AI"})
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import asyncio
from typing import Any
from loguru import logger
from core.config import CONFIG


BRAIN_COMMANDS_DIR = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain\.claude\commands")
FALLBACK_COMMANDS_DIR = Path(__file__).parent.parent.parent / "brain" / ".claude" / "commands"


class CommandDef:
    """Parsed brain command definition."""
    def __init__(self, name: str, description: str, body: str, path: Path):
        self.name = name
        self.description = description
        self.body = body
        self.path = path

    def __repr__(self):
        return f"CommandDef({self.name!r}: {self.description[:60]})"


class CommandRegistry:
    """Registry of all brain/.claude/commands/ commands."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
            cls._instance._commands: dict[str, CommandDef] = {}
        return cls._instance

    def _get_commands_dir(self) -> Path | None:
        for d in [BRAIN_COMMANDS_DIR, FALLBACK_COMMANDS_DIR]:
            if d.exists():
                return d
        return None

    def load(self) -> dict[str, CommandDef]:
        """Load all commands from brain vault."""
        if self._loaded:
            return self._commands

        cmd_dir = self._get_commands_dir()
        if not cmd_dir:
            logger.warning("[VECTOR][commands] Brain commands dir not found")
            self._loaded = True
            return self._commands

        count = 0
        for md_file in cmd_dir.glob("**/*.md"):
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                name = md_file.stem

                # Parse frontmatter
                description = ""
                body = content
                if content.startswith("---"):
                    end = content.find("---", 3)
                    if end > 0:
                        fm = content[3:end]
                        body = content[end + 3:].strip()
                        for line in fm.splitlines():
                            if line.startswith("description:"):
                                description = line.split(":", 1)[1].strip().strip('"\'')

                if not description:
                    # Use first non-empty line as description
                    for line in body.splitlines():
                        line = line.strip().lstrip("#").strip()
                        if line:
                            description = line[:120]
                            break

                self._commands[name] = CommandDef(name, description, body, md_file)
                count += 1
            except Exception as e:
                logger.debug("[VECTOR][commands] Failed to load {}: {}", md_file, e)

        logger.info("[VECTOR][commands] Loaded {} commands from {}", count, cmd_dir)
        self._loaded = True
        return self._commands

    def list_commands(self) -> list[dict]:
        """Return all commands as dicts."""
        self.load()
        return [{"name": c.name, "description": c.description} for c in self._commands.values()]

    def get(self, name: str) -> CommandDef | None:
        """Get a command by name."""
        self.load()
        return self._commands.get(name) or self._commands.get(name.lstrip("/"))

    async def execute(self, name: str, params: dict | None = None) -> dict:
        """
        Execute a brain command using the LLM via provider_client.
        The command's body becomes the system prompt; params become user message.
        """
        cmd = self.get(name)
        if not cmd:
            available = list(self._commands.keys())[:10]
            return {
                "status": "error",
                "error": f"Command '{name}' not found. Available: {available}",
            }

        try:
            from core.inference.provider_client import get_client
            from core.loop.context_engine import ContextEngine

            client = get_client()
            ctx = ContextEngine()
            hydration = ctx.session_hydration_prompt()

            # Build user message from params
            if params:
                user_msg = (
                    params.get("query")
                    or params.get("topic")
                    or params.get("input")
                    or str(params)
                )
            else:
                user_msg = "Execute this command."

            system = f"{hydration}\n\n---\nCOMMAND: /{cmd.name}\n{cmd.body}"

            response = await client.complete(
                model=CONFIG.get("models", {}).get("focus", "vector-focus"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=2000,
            )

            return {
                "status": "ok",
                "command": name,
                "result": response.content,
                "params": params,
            }
        except Exception as e:
            logger.error("[VECTOR][commands] execute '{}' failed: {}", name, e)
            return {"status": "error", "command": name, "error": str(e)}


# Module-level singleton
_registry = CommandRegistry()


def get_command_registry() -> CommandRegistry:
    return _registry


if __name__ == "__main__":
    reg = CommandRegistry()
    cmds = reg.load()
    print(f"✅ command_registry OK: {len(cmds)} commands loaded")
    print(f"Sample: {list(cmds.keys())[:5]}")
