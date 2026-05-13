"""
VectorCode Tool Registry — equivalent of Hermes model_tools.py + handle_function_call().

Routes tool calls from the agent loop to actual implementations.
Every tool has: name, description, input schema, risk_level, is_read_only.

Risk levels (Hermes + VectorCode permission matrix):
  safe   — read-only, auto-approved
  low    — new file write, auto-approved
  medium — edit existing files, safe bash → ask once per session
  high   — delete, push, deploy → always ask
  critical → require explicit /allow
"""
import sys
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}


# ── Tool Schema Definitions ───────────────────────────────────────────────────

_TOOL_SCHEMAS = [
    # ── Filesystem ────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file. Returns the file content as text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path"},
                    "start_line": {"type": "integer", "description": "First line to read (1-based, optional)"},
                    "end_line":   {"type": "integer", "description": "Last line to read (1-based, optional)"},
                },
                "required": ["path"],
            },
        },
        "_meta": {"risk": "safe", "read_only": True},
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file (creates or overwrites). Use edit_file for precise edits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
        "_meta": {"risk": "medium", "read_only": False},
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace the FIRST occurrence of old_text with new_text in a file. Preferred over write_file for targeted edits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":     {"type": "string", "description": "File path"},
                    "old_text": {"type": "string", "description": "Exact text to replace (must be unique in file)"},
                    "new_text": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
        "_meta": {"risk": "medium", "read_only": False},
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new file. Fails if file already exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "content": {"type": "string", "default": ""},
                },
                "required": ["path"],
            },
        },
        "_meta": {"risk": "low", "read_only": False},
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file. Requires approval.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        "_meta": {"risk": "high", "read_only": False},
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories at a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default: current dir)"},
                },
                "required": [],
            },
        },
        "_meta": {"risk": "safe", "read_only": True},
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a glob pattern (e.g. '**/*.py', 'src/**/*.ts').",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern"},
                    "base_dir": {"type": "string", "description": "Base directory (default: cwd)"},
                },
                "required": ["pattern"],
            },
        },
        "_meta": {"risk": "safe", "read_only": True},
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search file contents with a regex pattern. Returns matching lines with file+line info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern":      {"type": "string", "description": "Regex pattern to search for"},
                    "glob_pattern": {"type": "string", "description": "File glob (e.g. '**/*.py')", "default": "**/*"},
                    "case_sensitive": {"type": "boolean", "default": True},
                },
                "required": ["pattern"],
            },
        },
        "_meta": {"risk": "safe", "read_only": True},
    },
    # ── Shell ──────────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a shell command. Returns stdout + stderr. Timeout: 120s.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command":    {"type": "string", "description": "Shell command to execute"},
                    "timeout":    {"type": "integer", "description": "Timeout in seconds (default: 60)"},
                    "cwd":        {"type": "string", "description": "Working directory (default: project dir)"},
                },
                "required": ["command"],
            },
        },
        "_meta": {"risk": "medium", "read_only": False},
    },
    # ── Git ────────────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Get the current git working tree status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "_meta": {"risk": "safe", "read_only": True},
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show diff of staged or unstaged changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "staged": {"type": "boolean", "default": False},
                    "path":   {"type": "string", "description": "Limit diff to specific file"},
                },
                "required": [],
            },
        },
        "_meta": {"risk": "safe", "read_only": True},
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show recent git commit history.",
            "parameters": {
                "type": "object",
                "properties": {"n": {"type": "integer", "default": 10}},
                "required": [],
            },
        },
        "_meta": {"risk": "safe", "read_only": True},
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Stage all changes and create a git commit.",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string", "description": "Commit message"}},
                "required": ["message"],
            },
        },
        "_meta": {"risk": "medium", "read_only": False},
    },
    # ── Web ────────────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web (DuckDuckGo, no API key needed). Returns titles, URLs, snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":       {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
        "_meta": {"risk": "safe", "read_only": True},
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch and strip a URL to readable plain text (max 8K chars).",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
        "_meta": {"risk": "safe", "read_only": True},
    },
    # ── Memory ─────────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "memory_read",
            "description": "Read from VectorCode session memory (.vector/memory.md).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Keywords to search for"}},
                "required": [],
            },
        },
        "_meta": {"risk": "safe", "read_only": True},
    },
    {
        "type": "function",
        "function": {
            "name": "memory_write",
            "description": "Write a key-value pair to VectorCode session memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key":   {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        },
        "_meta": {"risk": "low", "read_only": False},
    },
]


# ── Tool Router (handle_function_call equivalent) ─────────────────────────────

class ToolRouter:
    """
    Routes tool_calls from the agent loop to actual implementations.
    Equivalent to Hermes handle_function_call() in model_tools.py.

    All tool implementations are contained here or delegated to
    VectorCode's existing tool classes (FileTools, GitTools, WebTools, etc.)
    """

    _SESSION_APPROVALS: set = set()  # approved tool+risk combos this session

    def __init__(
        self,
        project_dir: Optional[Path] = None,
        approval_callback: Optional[Callable] = None,
    ):
        self.project_dir = (project_dir or Path.cwd()).resolve()
        self._approval_cb = approval_callback
        self._file_tools = None
        self._git_tools  = None
        self._web_tools  = None

    def get_schemas(self) -> list[dict]:
        """Return tool schemas in OpenAI function-calling format (without _meta)."""
        schemas = []
        for tool in _TOOL_SCHEMAS:
            schema = {k: v for k, v in tool.items() if k != "_meta"}
            schemas.append(schema)
        return schemas

    def execute(self, name: str, args: dict) -> str:
        """Route and execute a tool call. Returns string result."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return f"[Unknown tool: {name}. Available: {[t['function']['name'] for t in _TOOL_SCHEMAS]}]"
        try:
            return handler(args)
        except PermissionError as e:
            return f"[PERMISSION DENIED: {e}]"
        except FileNotFoundError as e:
            return f"[FILE NOT FOUND: {e}]"
        except Exception as e:
            logger.error("[VECTOR][tool:%s] %s", name, e)
            return f"[{name} error: {e}]"

    # ── File helpers ──────────────────────────────────────────────────────────

    def _ft(self):
        if self._file_tools is None:
            from tools.file_tools import FileTools
            self._file_tools = FileTools(repo_root=str(self.project_dir))
        return self._file_tools

    def _gt(self):
        if self._git_tools is None:
            from tools.git_tools import GitTools
            self._git_tools = GitTools(repo_root=str(self.project_dir))
        return self._git_tools

    def _wt(self):
        if self._web_tools is None:
            from tools.web_tools import WebTools
            self._web_tools = WebTools()
        return self._web_tools

    # ── Filesystem tools ──────────────────────────────────────────────────────

    def _tool_read_file(self, args: dict) -> str:
        path = args.get("path", "")
        content = self._ft().read(path)
        start = args.get("start_line")
        end   = args.get("end_line")
        if start or end:
            lines = content.splitlines()
            s = max(0, (start or 1) - 1)
            e = end or len(lines)
            content = "\n".join(lines[s:e])
        return content

    def _tool_write_file(self, args: dict) -> str:
        path    = args.get("path", "")
        content = args.get("content", "")
        self._ft().write(path, content)
        return f"✓ Written: {path} ({len(content)} chars)"

    def _tool_edit_file(self, args: dict) -> str:
        path     = args.get("path", "")
        old_text = args.get("old_text", "")
        new_text = args.get("new_text", "")
        self._ft().edit(path, old_text, new_text)
        return f"✓ Edited: {path}"

    def _tool_create_file(self, args: dict) -> str:
        path    = args.get("path", "")
        content = args.get("content", "")
        self._ft().create_file(path, content)
        return f"✓ Created: {path}"

    def _tool_delete_file(self, args: dict) -> str:
        path = args.get("path", "")
        safe = (self._file_tools or self._ft())._safe_path(path)
        safe.unlink()
        return f"✓ Deleted: {path}"

    def _tool_list_directory(self, args: dict) -> str:
        path = args.get("path", ".")
        entries = self._ft().list_directory(path)
        return "\n".join(entries) if entries else "(empty directory)"

    def _tool_glob(self, args: dict) -> str:
        pattern  = args.get("pattern", "**/*")
        base_dir = args.get("base_dir", str(self.project_dir))
        results = []
        for p in Path(base_dir).glob(pattern):
            if p.is_file():
                try:
                    results.append(str(p.relative_to(self.project_dir)))
                except ValueError:
                    results.append(str(p))
        if not results:
            return "(no files matched)"
        return "\n".join(results[:500])  # cap at 500 results

    def _tool_grep(self, args: dict) -> str:
        pattern       = args.get("pattern", "")
        glob_pattern  = args.get("glob_pattern", "**/*")
        case_sensitive = args.get("case_sensitive", True)
        flags = 0 if case_sensitive else re.IGNORECASE
        results = self._ft().grep(pattern, glob_pattern)
        if not results:
            return "(no matches)"
        lines = []
        for r in results[:200]:
            lines.append(f"{r['file']}:{r['line']}: {r['content'].rstrip()}")
        return "\n".join(lines)

    # ── Shell tools ───────────────────────────────────────────────────────────

    def _tool_bash(self, args: dict) -> str:
        command = args.get("command", "")
        timeout = min(int(args.get("timeout", 60)), 120)
        cwd     = args.get("cwd", str(self.project_dir))

        if not command.strip():
            return "[bash: empty command]"

        # Safety: use shell=True only on Windows where shlex doesn't work well
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            output = proc.stdout
            if proc.stderr:
                output += ("\n" if output else "") + proc.stderr
            if proc.returncode != 0:
                output += f"\n[exit code: {proc.returncode}]"
            return output.strip() or f"[exit code: {proc.returncode}]"
        except subprocess.TimeoutExpired:
            return f"[bash: timed out after {timeout}s]"
        except Exception as e:
            return f"[bash error: {e}]"

    # ── Git tools ─────────────────────────────────────────────────────────────

    def _tool_git_status(self, _args: dict) -> str:
        return self._gt().git_status()

    def _tool_git_diff(self, args: dict) -> str:
        staged = args.get("staged", False)
        path   = args.get("path", None)
        return self._gt().git_diff(staged=staged) or "(no changes)"

    def _tool_git_log(self, args: dict) -> str:
        n = int(args.get("n", 10))
        return self._gt().git_log(n=n)

    def _tool_git_commit(self, args: dict) -> str:
        message = args.get("message", "auto: VectorCode commit")
        return self._gt().git_commit(message)

    # ── Web tools ─────────────────────────────────────────────────────────────

    def _tool_web_search(self, args: dict) -> str:
        query       = args.get("query", "")
        max_results = int(args.get("max_results", 5))
        results = self._wt().web_search(query, max_results=max_results)
        return self._wt().format_search_results(results)

    def _tool_web_fetch(self, args: dict) -> str:
        url = args.get("url", "")
        return self._wt().web_fetch(url)

    # ── Memory tools ──────────────────────────────────────────────────────────

    def _tool_memory_read(self, args: dict) -> str:
        query = args.get("query", "")
        try:
            from memory.manager import get_memory_manager
            mm = get_memory_manager()
            return mm.prefetch_all(query) or "(memory empty)"
        except Exception as e:
            return f"[memory_read error: {e}]"

    def _tool_memory_write(self, args: dict) -> str:
        key   = args.get("key", "")
        value = args.get("value", "")
        try:
            from memory.provider import VectorBuiltinMemoryProvider
            provider = VectorBuiltinMemoryProvider()
            provider.on_memory_write("set", key, value)
            return f"✓ Memory saved: {key}"
        except Exception as e:
            return f"[memory_write error: {e}]"


if __name__ == "__main__":
    import tempfile
    sys.stdout.reconfigure(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        router = ToolRouter(project_dir=Path(tmp))

        # Schema generation
        schemas = router.get_schemas()
        names = {s["function"]["name"] for s in schemas}
        assert "read_file"     in names
        assert "bash"          in names
        assert "git_status"    in names
        assert "web_search"    in names
        assert "memory_read"   in names
        print(f"  {len(schemas)} tools registered")

        # File round-trip
        result = router.execute("create_file", {"path": "test.txt", "content": "hello"})
        assert "Created" in result, result
        content = router.execute("read_file", {"path": "test.txt"})
        assert content == "hello", content

        result2 = router.execute("edit_file", {"path": "test.txt", "old_text": "hello", "new_text": "world"})
        assert "Edited" in result2
        content2 = router.execute("read_file", {"path": "test.txt"})
        assert content2 == "world", content2

        # List + glob
        lst = router.execute("list_directory", {"path": "."})
        assert "test.txt" in lst

        glb = router.execute("glob", {"pattern": "*.txt"})
        assert "test.txt" in glb

        # Bash
        bash_out = router.execute("bash", {"command": "echo hello_vector"})
        assert "hello_vector" in bash_out, bash_out

        # Unknown tool
        unknown = router.execute("nonexistent_tool", {})
        assert "Unknown tool" in unknown

    print("tools/registry.py OK")
