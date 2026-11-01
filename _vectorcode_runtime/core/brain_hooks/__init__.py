"""
VECTOR Brain Hooks — core/brain_hooks

TypeScript lifecycle hooks for VECTOR's Obsidian Brain vault.
TypeScript lifecycle hooks for VECTOR's Obsidian Brain vault.

Provides:
- SessionStart hook: inject ~2K tokens of context (North Star, tasks, vault listing)
- UserPromptSubmit hook: classify prompt type (DECISION, INCIDENT, 1:1, etc.)
- PostToolUse hook: validate frontmatter + wikilinks after writes
- PreCompact hook: back up transcript before context compaction
- Stop hook: wrap-up checklist

Also exposes Python-callable utilities for listing commands, agents, and skills
installed in VECTOR Brain's .claude/ directory.

Hook scripts run via: node --experimental-strip-types <script>.ts
Requires: Node 22.6+ (stable --experimental-strip-types)

VECTOR Brain vault path:
  C:\\Users\\Arghyadeep\\Desktop\\V.E.C.T.O.R\\V.E.C.T.O.R. Brain\\

Vault QMD index: "vector-brain"
"""

import os
import re
import subprocess
from pathlib import Path

from core.config import CONFIG

_BRAIN_DIR = Path(CONFIG["VECTOR_VAULT_PATH"]) if "VECTOR_VAULT_PATH" in CONFIG else Path.home() / "V.E.C.T.O.R Brain"
_HOOKS_DIR = Path(__file__).parent / "scripts"

# run_hook() builds f"{hook_name}.ts" under _HOOKS_DIR and executes it via
# node -- an unvalidated name like "../../x" would run an arbitrary .ts file.
# core/mcp_tools/expansion_modules/hooks.py's own _run_hook() wrapper already
# validates hook_name with this identical pattern before calling run_hook()
# (that was the actual fix for this bug class), but that only covers its one
# current caller -- this module's own public function was still unguarded
# for any other/future caller. Fixed at the primitive so every caller is
# covered, matching this cycle's established "fix at the primitive, not just
# the one known caller" pattern.
_HOOK_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


def list_commands() -> list[str]:
    """List all slash commands installed in VECTOR Brain."""
    commands_dir = _BRAIN_DIR / ".claude" / "commands"
    if not commands_dir.exists():
        return []
    return sorted(f.stem for f in commands_dir.glob("*.md"))


def list_agents() -> list[str]:
    """List all subagents installed in VECTOR Brain."""
    agents_dir = _BRAIN_DIR / ".claude" / "agents"
    if not agents_dir.exists():
        return []
    return sorted(f.stem for f in agents_dir.glob("*.md"))


def list_skills() -> list[str]:
    """List all skills installed in VECTOR Brain."""
    skills_dir = _BRAIN_DIR / ".claude" / "skills"
    if not skills_dir.exists():
        return []
    return sorted(d.name for d in skills_dir.iterdir() if d.is_dir())


def run_hook(hook_name: str, stdin_data: str = "") -> tuple[str, int]:
    """
    Run a lifecycle hook script via Node.

    hook_name: one of session-start, classify-message, validate-write,
               pre-compact, stop-checklist, qmd-refresh
    stdin_data: JSON string passed to hook via stdin (see hook-io.ts format)

    Returns: (stdout_text, exit_code)
    """
    if not _HOOK_NAME_RE.match(hook_name or ""):
        return f"invalid hook name: {hook_name!r}", 1
    script = _HOOKS_DIR / f"{hook_name}.ts"
    if not script.exists():
        return f"Hook script not found: {script}", 1
    try:
        result = subprocess.run(
            ["node", "--experimental-strip-types", str(script)],
            input=stdin_data,
            capture_output=True,
            text=True,
            cwd=str(_BRAIN_DIR),
            timeout=30,
        )
        return result.stdout, result.returncode
    except FileNotFoundError:
        return "node not found — install Node 22.6+", 1
    except subprocess.TimeoutExpired:
        return "hook timed out after 30s", 1
    except Exception as e:
        return str(e), 1


def vault_stats() -> dict:
    """Return basic stats about the VECTOR Brain vault."""
    stats = {
        "vault_path": str(_BRAIN_DIR),
        "commands": len(list_commands()),
        "agents": len(list_agents()),
        "skills": len(list_skills()),
        "vault_exists": _BRAIN_DIR.exists(),
    }
    # Count markdown files
    if _BRAIN_DIR.exists():
        md_count = sum(1 for _ in _BRAIN_DIR.rglob("*.md")
                       if ".obsidian" not in str(_) and "node_modules" not in str(_))
        stats["markdown_files"] = md_count
    return stats


if __name__ == "__main__":
    stats = vault_stats()
    print("VECTOR Brain Hooks")
    print(f"  Vault: {stats['vault_path']} (exists={stats['vault_exists']})")
    print(f"  Commands: {stats['commands']}")
    print(f"  Agents:   {stats['agents']}")
    print(f"  Skills:   {stats['skills']}")
    if stats.get("markdown_files"):
        print(f"  MD files: {stats['markdown_files']}")
    print(f"\nCommands: {list_commands()[:5]}...")
    print(f"Agents:   {list_agents()[:5]}...")
    print(f"Skills:   {list_skills()[:5]}...")
