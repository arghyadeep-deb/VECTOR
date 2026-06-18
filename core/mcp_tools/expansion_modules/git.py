from __future__ import annotations

from pathlib import Path


from core.config import CONFIG
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)


def add_git_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).resolve().parents[3]

    # â”€â”€ git_* (12) — wired via subprocess git â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @mcp.tool
    def git_commit(message: str, files: str = "") -> str:
        """Create a git commit with a message."""
        try:
            if files:
                for f in files.split(","):
                    _subprocess.run(["git", "add", f.strip()], cwd=str(ROOT), capture_output=True, timeout=10)
            result = _subprocess.run(["git", "commit", "-m", message], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_diff(staged: bool = False) -> str:
        """Show git diff for staged or unstaged changes."""
        try:
            cmd = ["git", "diff", "--staged"] if staged else ["git", "diff"]
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=10)
            return _safe_json({"diff": result.stdout[:10000] or "No changes"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_log(n: int = 10) -> str:
        """Show recent git log."""
        try:
            result = _subprocess.run(["git", "log", f"-{n}", "--oneline"], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
            return _safe_json({"commits": result.stdout.strip().split("\n")})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_branch(name: str = "") -> str:
        """List branches or create a new one."""
        try:
            if name:
                result = _subprocess.run(["git", "branch", name], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
                return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
            result = _subprocess.run(["git", "branch", "-v"], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
            return _safe_json({"branches": result.stdout.strip().split("\n")})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_blame(file_path: str) -> str:
        """Show git blame for a file."""
        try:
            result = _subprocess.run(["git", "blame", "-n", file_path], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"file": file_path, "blame": result.stdout[:5000] or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_checkout(branch: str) -> str:
        """Checkout a branch."""
        try:
            result = _subprocess.run(["git", "checkout", branch], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_stash(action: str = "save", message: str = "") -> str:
        """Stash or pop working changes."""
        try:
            cmd = ["git", "stash"]
            if action == "pop":
                cmd.append("pop")
            elif action == "save" and message:
                cmd.extend(["push", "-m", message])
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=10)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_merge(branch: str) -> str:
        """Merge a branch (RED gate — use with caution)."""
        try:
            result = _subprocess.run(["git", "merge", branch], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_rebase(onto: str) -> str:
        """Rebase onto a branch (RED gate — use with caution)."""
        try:
            result = _subprocess.run(["git", "rebase", onto], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_push(remote: str = "origin", branch: str = "") -> str:
        """Push current branch to remote (RED gate)."""
        try:
            cmd = ["git", "push", remote]
            if branch:
                cmd.append(branch)
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_pr_create(title: str, body: str = "", base: str = "main") -> str:
        """Create a GitHub pull request via gh CLI."""
        try:
            cmd = ["gh", "pr", "create", "--title", title, "--base", base]
            if body:
                cmd.extend(["--body", body])
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except FileNotFoundError:
            return _safe_json({"error": "gh CLI not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})
