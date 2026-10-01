"""Git worktree isolation — create isolated copies for risky operations."""
import re
import subprocess
import uuid
from pathlib import Path
from typing import Optional


try:
    from core.config import CONFIG  # noqa: F401
except Exception:
    CONFIG = {}

from loguru import logger

_WORKTREE_PREFIX = "vector_wt_"

# A ref/branch name starting with "-" becomes a git option instead of a ref
# (--upload-pack=<cmd> is a known git argument-injection RCE vector) when
# passed as a bare positional argument with no "--" separator. Same
# allowlist pattern already fixed in this package's git_tools.py
# (commit b1523366f) and core/mcp_tools/expansion_modules/git.py.
_REF_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/@-]*$")


def _bad_ref(value: str, what: str = "ref") -> Optional[str]:
    v = value or ""
    if (not _REF_RE.match(v) or ".." in v or "//" in v or "@{" in v
            or v.endswith((".", "/", ".lock"))):
        return f"invalid {what}: {v!r}"
    return None


class WorktreeManager:
    """Create, manage, and remove git worktrees for isolated operations."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()

    # ── Internal helper ───────────────────────────────────────────────────────

    def _git(self, *args: str, cwd: Optional[Path] = None,
             check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command, optionally under a specific working directory."""
        cmd = ["git", *args]
        cwd_str = str(cwd or self.repo_root)
        logger.debug(f"[VECTOR][worktree] git {' '.join(args)} (cwd={cwd_str})")
        try:
            return subprocess.run(
                cmd,
                cwd=cwd_str,
                capture_output=True,
                text=True,
                check=check,
            )
        except subprocess.CalledProcessError as e:
            logger.error(
                f"[VECTOR][worktree] git command failed: {e.cmd}\n"
                f"stdout: {e.stdout}\nstderr: {e.stderr}"
            )
            raise

    # ── Public API ────────────────────────────────────────────────────────────

    def create(self, branch_name: str = "", base: str = "HEAD") -> Path:
        """Create a new git worktree and return its path.

        Creates an isolated worktree under /tmp with a unique name.
        A new branch *branch_name* is created from *base*; if *branch_name*
        is empty a UUID-based name is generated automatically.
        """
        short_id = str(uuid.uuid4()).replace("-", "")[:12]
        if not branch_name:
            branch_name = f"{_WORKTREE_PREFIX}{short_id}"

        err = _bad_ref(branch_name, "branch name") or _bad_ref(base, "base ref")
        if err:
            raise ValueError(err)

        import tempfile
        tmp_dir = Path(tempfile.gettempdir())
        worktree_path = tmp_dir / f"{_WORKTREE_PREFIX}{short_id}"

        try:
            self._git(
                "worktree", "add",
                "-b", branch_name,
                str(worktree_path),
                "--",
                base,
            )
            logger.info(
                f"[VECTOR][worktree] created worktree at {worktree_path} "
                f"(branch={branch_name})"
            )
            return worktree_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to create worktree: {e.stderr.strip()}"
            ) from e

    def destroy(self, worktree_path: Path) -> bool:
        """Remove a git worktree by path.

        Returns True on success, False if the worktree does not exist or
        removal fails.
        """
        try:
            self._git("worktree", "remove", "--force", str(worktree_path))
            logger.info(f"[VECTOR][worktree] removed worktree {worktree_path}")
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(
                f"[VECTOR][worktree] could not remove {worktree_path}: "
                f"{e.stderr.strip()}"
            )
            return False

    def list_worktrees(self) -> list[dict]:
        """Return a list of dicts with keys path, HEAD, branch for each worktree."""
        try:
            result = self._git("worktree", "list", "--porcelain")
        except subprocess.CalledProcessError:
            return []

        worktrees: list[dict] = []
        current: dict = {}

        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                if current:
                    worktrees.append(current)
                current = {"path": line[len("worktree "):].strip(), "HEAD": "", "branch": ""}
            elif line.startswith("HEAD "):
                current["HEAD"] = line[len("HEAD "):].strip()
            elif line.startswith("branch "):
                current["branch"] = line[len("branch "):].strip()
        if current:
            worktrees.append(current)

        return worktrees

    def diff_from_main(self, worktree_path: Path) -> str:
        """Return the diff between *worktree_path* changes and the repo HEAD."""
        try:
            result = self._git(
                "diff", "HEAD",
                cwd=worktree_path,
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.warning(f"[VECTOR][worktree] diff failed: {e.stderr.strip()}")
            return ""

    def merge_to_main(self, worktree_path: Path, message: str = "") -> dict:
        """Merge the worktree's branch back into the repo's current branch.

        Returns a dict: {ok: bool, message: str, conflicts: list[str]}.
        """
        # Determine the branch name of the worktree
        branch = ""
        for wt in self.list_worktrees():
            if Path(wt["path"]).resolve() == Path(worktree_path).resolve():
                raw_branch = wt.get("branch", "")
                # "refs/heads/some-branch" → "some-branch"
                branch = raw_branch.replace("refs/heads/", "")
                break

        if not branch:
            return {"ok": False, "message": "worktree branch not found", "conflicts": []}

        merge_args = ["merge", branch]
        if message:
            merge_args += ["-m", message]

        try:
            result = self._git(*merge_args)
            logger.info(f"[VECTOR][worktree] merged branch '{branch}' into HEAD")
            return {"ok": True, "message": result.stdout.strip(), "conflicts": []}
        except subprocess.CalledProcessError as e:
            # Detect conflict file list from git output
            conflicts = [
                line.split("CONFLICT (content): Merge conflict in ", 1)[1].strip()
                for line in e.stdout.splitlines()
                if "CONFLICT" in line and "Merge conflict in" in line
            ]
            logger.error(
                f"[VECTOR][worktree] merge conflict for branch '{branch}': "
                f"{e.stderr.strip()}"
            )
            return {
                "ok": False,
                "message": e.stderr.strip() or e.stdout.strip(),
                "conflicts": conflicts,
            }

    def cleanup_all(self) -> int:
        """Remove all worktrees whose names start with the VECTOR prefix.

        Returns the number of worktrees removed.
        """
        removed = 0
        for wt in self.list_worktrees():
            path = Path(wt["path"])
            if path.name.startswith(_WORKTREE_PREFIX):
                if self.destroy(path):
                    removed += 1
        logger.info(f"[VECTOR][worktree] cleanup_all removed {removed} worktrees")
        return removed


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import tempfile
    import os

    # Create a minimal throwaway git repo for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir) / "test_repo"
        repo.mkdir()

        subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@vector.local"],
            cwd=str(repo), capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "VectorTest"],
            cwd=str(repo), capture_output=True, check=True,
        )
        # Create initial commit so HEAD exists
        (repo / "README.md").write_text("VECTOR test repo")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(repo), capture_output=True, check=True,
        )

        mgr = WorktreeManager(repo)

        # list_worktrees — should have at least the main worktree
        wts = mgr.list_worktrees()
        assert len(wts) >= 1, f"expected at least 1 worktree, got {wts}"

        # create + destroy
        wt_path = mgr.create()
        assert wt_path.exists(), f"worktree path {wt_path} does not exist"

        wts_after = mgr.list_worktrees()
        assert len(wts_after) == len(wts) + 1

        diff = mgr.diff_from_main(wt_path)
        assert isinstance(diff, str)

        ok = mgr.destroy(wt_path)
        assert ok is True
        assert not wt_path.exists()

        # cleanup_all — no VECTOR worktrees remaining
        count = mgr.cleanup_all()
        assert count == 0

    print("tools/worktree.py OK")
