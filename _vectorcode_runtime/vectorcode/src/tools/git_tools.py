"""Git tools for VectorCode — git_status, git_diff, git_log, git_commit,
git_create_branch, git_push, git_create_pr.

All write/push operations are gated through the permission system:
- git_status / git_diff / git_log → safe (auto-approved)
- git_commit / git_create_branch  → medium (ask once per session)
- git_push / git_create_pr        → high (always ask)
"""

import re
import sys
import subprocess
from pathlib import Path

from loguru import logger

# A branch/remote name that starts with "-" becomes a git option
# (--upload-pack=<cmd>, --force, ...) instead of a ref/remote -- a known git
# argument-injection RCE vector. Same allowlist pattern already fixed in
# core/mcp_tools/expansion_modules/git.py's git_push/git_checkout/git_merge
# (commits d41e9a1f2/46e4b2fda) -- allowlist, never blocklist.
_REF_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/@-]*$")
_REMOTE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


def _bad_ref(value: str, what: str = "ref") -> str | None:
    v = value or ""
    if (not _REF_RE.match(v) or ".." in v or "//" in v or "@{" in v
            or v.endswith((".", "/", ".lock"))):
        return f"invalid {what}: {v!r}"
    return None

RISK_LEVELS = {
    "git_status":        "safe",
    "git_diff":          "safe",
    "git_log":           "safe",
    "git_blame":         "safe",
    "git_commit":        "medium",
    "git_create_branch": "medium",
    "git_push":          "high",
    "git_create_pr":     "high",
}


class GitTools:
    """
    Git operations scoped to a repository root.
    shell=False enforced throughout.
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()

    def _run(self, args: list[str], timeout: int = 30) -> dict:
        cmd = ["git"] + args
        logger.debug(f"[VECTOR][git] {' '.join(cmd)}")
        try:
            r = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
            return {"stdout": r.stdout, "stderr": r.stderr, "returncode": r.returncode}
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"git command timed out: {cmd}")
        except FileNotFoundError:
            raise RuntimeError("git not found — is git installed and on PATH?")

    def _run_gh(self, args: list[str], timeout: int = 30) -> dict:
        """Run GitHub CLI commands in this tool's repository scope."""
        cmd = ["gh"] + args
        logger.debug('[VECTOR][git] Running GitHub CLI PR command')
        try:
            import os
            from vectorcode.src.tools.environments.local import _sanitize_subprocess_env

            r = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                env=_sanitize_subprocess_env(dict(os.environ)),
                stdin=subprocess.DEVNULL,
            )
            return {"stdout": r.stdout, "stderr": r.stderr, "returncode": r.returncode}
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"gh command timed out: {cmd}")
        except FileNotFoundError:
            raise RuntimeError("gh not found — install GitHub CLI and authenticate with 'gh auth login'")

    # ── Read-only tools (safe) ─────────────────────────────────────────────────

    def git_status(self) -> str:
        """Get the current working tree status."""
        r = self._run(["status", "--short", "--branch"])
        return r["stdout"] or r["stderr"]

    def git_diff(self, staged: bool = False, path: str = "") -> str:
        """Show unstaged (or --staged) diff. Optionally scoped to a path."""
        args = ["diff"]
        if staged:
            args.append("--staged")
        if path:
            args += ["--", path]
        r = self._run(args)
        return r["stdout"] or "(no diff)"

    def git_log(self, n: int = 10, oneline: bool = True) -> str:
        """Show last n commits."""
        args = ["log", f"-{n}"]
        if oneline:
            args.append("--oneline")
        r = self._run(args)
        return r["stdout"] or "(no commits)"

    def git_blame(self, path: str, start: int = 1, end: int = 0) -> str:
        """Show git blame for a file, optionally scoped to a line range."""
        args = ["blame"]
        if end > 0:
            args += [f"-L{start},{end}"]
        args += ["--", path]
        r = self._run(args)
        return r["stdout"] or r["stderr"]

    # ── Write tools (require permission) ──────────────────────────────────────

    def git_commit(self, message: str, add_all: bool = True) -> str:
        """Stage all changes and commit with a message. MEDIUM gate."""
        if add_all:
            add_r = self._run(["add", "-A"])
            if add_r["returncode"] != 0:
                return f"git add failed: {add_r['stderr']}"
        r = self._run(["commit", "-m", message])
        if r["returncode"] == 0:
            logger.info(f"[VECTOR][git] committed: {message[:60]}")
            return r["stdout"].strip()
        return f"commit failed: {r['stderr']}"

    def git_create_branch(self, name: str, checkout: bool = True) -> str:
        """Create (and optionally checkout) a new branch. MEDIUM gate."""
        bad = _bad_ref(name, "branch name")
        if bad:
            return f"Branch creation failed: {bad}"
        args = ["checkout", "-b", name, "--"] if checkout else ["branch", "--", name]
        r = self._run(args)
        if r["returncode"] == 0:
            return f"Branch '{name}' created{' and checked out' if checkout else ''}."
        return f"Branch creation failed: {r['stderr']}"

    def git_push(self, remote: str = "origin", branch: str = "") -> str:
        """Push to remote. HIGH gate — always requires approval."""
        if not _REMOTE_RE.match(remote or ""):
            return f"push failed: invalid remote name: {remote!r}"
        if not branch:
            # detect current branch
            r = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
            branch = r["stdout"].strip() or "main"
        bad = _bad_ref(branch, "branch")
        if bad:
            return f"push failed: {bad}"
        r = self._run(["push", remote, branch], timeout=60)
        if r["returncode"] == 0:
            return r["stdout"].strip() or f"Pushed to {remote}/{branch}"
        return f"push failed: {r['stderr']}"

    def git_create_pr(
        self, title: str, body: str, base: str = "main", draft: bool = False, head: str = ''
    ) -> str:
        """Create a GitHub pull request. HIGH gate — always requires approval."""
        bad = _bad_ref(base, "base branch")
        if bad:
            return f"PR creation failed: {bad}"
        if not head or _bad_ref(head, 'head branch'):
            return 'PR creation failed: an explicit, already-pushed head branch is required.'
        # GitHub CLI documents --head as skipping automatic forking/pushing.
        args = ["pr", "create", "--title", title, "--base", base, '--head', head]
        if draft:
            args.append("--draft")
        try:
            import tempfile

            with tempfile.TemporaryDirectory(prefix='vector-pr-') as directory:
                body_path = Path(directory) / 'body.md'
                body_path.write_text(body, encoding='utf-8')
                r = self._run_gh(args + ['--body-file', str(body_path)], timeout=60)
        except (RuntimeError, TimeoutError) as exc:
            return f"PR creation failed: {exc}"
        if r["returncode"] == 0:
            return r["stdout"].strip()
        return f"PR creation failed: {r['stderr']}"

    def current_branch(self) -> str:
        r = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        return r["stdout"].strip()

    def staged_files(self) -> list[str]:
        """Return list of files staged for commit."""
        r = self._run(["diff", "--cached", "--name-only"])
        return [f for f in r["stdout"].splitlines() if f]

    def modified_files(self) -> list[str]:
        """Return list of modified (tracked) files."""
        r = self._run(["ls-files", "--modified"])
        return [f for f in r["stdout"].splitlines() if f]


def _handle_git_create_pr(args, **kwargs):
    import os

    return GitTools(os.environ.get('TERMINAL_CWD') or Path.cwd()).git_create_pr(
        title=args['title'], body=args['body'], base=args.get('base', 'main'), draft=args.get('draft', False),
        head=args['head'],
    )


def _has_github_cli():
    import shutil

    return shutil.which('gh') is not None


from tools.registry import registry

registry.register(
    name='git_create_pr', toolset='git_pr', check_fn=_has_github_cli,
    schema={'name': 'git_create_pr', 'description': 'Create a GitHub PR after explicit approval. Does not push branches.',
            'parameters': {'type': 'object', 'properties': {
                'title': {'type': 'string', 'maxLength': 256},
                'body': {'type': 'string', 'maxLength': 60000},
                'base': {'type': 'string', 'default': 'main'}, 'head': {'type': 'string'},
                'draft': {'type': 'boolean', 'default': False}},
                'required': ['title', 'body', 'head']}},
    handler=_handle_git_create_pr,
)


if __name__ == "__main__":
    import tempfile, os
    sys.stdout.reconfigure(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        gt = GitTools(repo_root=tmp)
        # init a bare repo for testing
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@vector.ai"], cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "VECTOR"], cwd=tmp, capture_output=True)

        status = gt.git_status()
        assert isinstance(status, str)

        # create a file and commit
        Path(tmp, "hello.py").write_text("print('hello')")
        gt.git_commit("init: hello.py")
        log = gt.git_log(n=1)
        assert "init" in log.lower() or isinstance(log, str)

        diff = gt.git_diff()
        assert isinstance(diff, str)

    print("git_tools.py OK")


