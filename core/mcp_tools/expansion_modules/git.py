from __future__ import annotations

from pathlib import Path


from core.config import CONFIG
from core.mcp_tools.expansion_modules import is_secret_path, resolve_in_root
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)


_ROOT = Path(__file__).resolve().parents[3]  # module-level so tests can point it at a tmp dir


def add_git_tools(mcp) -> None:
    import json as _json
    import re as _re
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _ROOT

    # Caller-supplied refs/remotes/paths are attacker-influenceable. A value that
    # starts with "-" becomes a git option (--upload-pack, --output=...), and a
    # remote can be a transport URL (ext::sh -c ...). Allowlist, never blocklist.
    _REF_RE = _re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/@-]*$")
    _REMOTE_RE = _re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")

    def _bad_ref(value: str, what: str = "ref") -> str | None:
        v = value or ""
        if (not _REF_RE.match(v) or ".." in v or "//" in v or "@{" in v
                or v.endswith((".", "/", ".lock"))):
            return _safe_json({"ok": False, "error": f"invalid {what}: {v!r}"})
        return None

    def _run(cmd: list[str], timeout: int = 10):
        return _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)

    def _res(result) -> str:
        return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})

    # â”€â”€ git_* (12) — wired via subprocess git â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @mcp.tool
    def git_commit(message: str, files: str = "") -> str:
        """Create a git commit with a message."""
        try:
            for f in [x.strip() for x in files.split(",") if x.strip()]:
                p = resolve_in_root(ROOT, f)
                if p is None or is_secret_path(ROOT, p):
                    return _safe_json({"ok": False, "error": f"refusing to stage path: {f!r}"})
                add = _run(["git", "add", "--", f], timeout=10)
                if add.returncode != 0:
                    return _safe_json({"ok": False, "error": f"git add failed for {f!r}: {add.stderr.strip()}"})
            return _res(_run(["git", "commit", "-m", message], timeout=30))
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_diff(staged: bool = False) -> str:
        """Show git diff for staged or unstaged changes."""
        try:
            cmd = ["git", "diff", "--staged"] if staged else ["git", "diff"]
            result = _run(cmd)
            if result.returncode != 0:
                return _safe_json({"ok": False, "error": result.stderr.strip()})
            return _safe_json({"diff": result.stdout[:10000] or "No changes"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_log(n: int = 10) -> str:
        """Show recent git log."""
        try:
            n = max(1, min(int(n), 200))
            result = _run(["git", "log", f"-{n}", "--oneline"])
            if result.returncode != 0:
                return _safe_json({"ok": False, "error": result.stderr.strip()})
            return _safe_json({"commits": result.stdout.strip().split("\n") if result.stdout.strip() else []})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_branch(name: str = "") -> str:
        """List branches or create a new one."""
        try:
            if name:
                bad = _bad_ref(name, "branch name")
                if bad:
                    return bad
                return _res(_run(["git", "branch", name]))
            result = _run(["git", "branch", "-v"])
            if result.returncode != 0:
                return _safe_json({"ok": False, "error": result.stderr.strip()})
            return _safe_json({"branches": result.stdout.strip().split("\n")})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_blame(file_path: str) -> str:
        """Show git blame for a file."""
        try:
            p = resolve_in_root(ROOT, file_path)
            if p is None or is_secret_path(ROOT, p):
                return _safe_json({"ok": False, "error": f"path not allowed: {file_path!r}"})
            result = _run(["git", "blame", "-n", "--", file_path], timeout=30)
            if result.returncode != 0:
                return _safe_json({"ok": False, "file": file_path, "error": result.stderr.strip()})
            return _safe_json({"file": file_path, "blame": result.stdout[:5000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_checkout(branch: str) -> str:
        """Checkout a branch."""
        try:
            bad = _bad_ref(branch, "branch")
            if bad:
                return bad
            return _res(_run(["git", "checkout", branch, "--"]))
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_stash(action: str = "save", message: str = "") -> str:
        """Stash or pop working changes."""
        try:
            if action not in ("save", "pop"):
                return _safe_json({"ok": False, "error": f"unsupported stash action: {action!r}"})
            cmd = ["git", "stash"]
            if action == "pop":
                cmd.append("pop")
            elif action == "save" and message:
                cmd.extend(["push", "-m", message])
            return _res(_run(cmd))
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_merge(branch: str) -> str:
        """Merge a branch (RED gate — use with caution)."""
        try:
            bad = _bad_ref(branch, "branch")
            if bad:
                return bad
            return _res(_run(["git", "merge", branch], timeout=30))
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_rebase(onto: str) -> str:
        """Rebase onto a branch (RED gate — use with caution)."""
        try:
            bad = _bad_ref(onto, "rebase target")
            if bad:
                return bad
            return _res(_run(["git", "rebase", onto], timeout=30))
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_push(remote: str = "origin", branch: str = "") -> str:
        """Push current branch to remote (RED gate)."""
        try:
            if not _REMOTE_RE.match(remote or ""):
                return _safe_json({"ok": False, "error": f"invalid remote name: {remote!r}"})
            cmd = ["git", "push", remote]
            if branch:
                bad = _bad_ref(branch, "branch")
                if bad:
                    return bad
                cmd.append(branch)
            return _res(_run(cmd, timeout=30))
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_pr_create(title: str, body: str = "", base: str = "main") -> str:
        """Create a GitHub pull request via gh CLI."""
        try:
            bad = _bad_ref(base, "base branch")
            if bad:
                return bad
            cmd = ["gh", "pr", "create", "--title", title, "--base", base]
            if body:
                cmd.extend(["--body", body])
            return _res(_run(cmd, timeout=30))
        except FileNotFoundError:
            return _safe_json({"error": "gh CLI not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})
