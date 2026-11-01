"""
VectorCode Checkpoint Tool — ported from VectorCode checkpoint_manager.py.

Provides transparent filesystem snapshots via shadow git repos.
Shadow repo lives at: ~/.vector/checkpoints/{sha256(abs_dir)[:16]}/

Uses GIT_DIR + GIT_WORK_TREE env vars — no .git pollution in the work dir.

Public API (also exposed as OpenAI function schemas):
  - create_checkpoint(label)          -> {ok, commit_hash, message}
  - list_checkpoints()                -> [{hash, label, timestamp, files_changed}]
  - restore_checkpoint(commit_hash, force) -> {ok, restored_files, message}
  - diff_from_checkpoint(commit_hash) -> unified diff string

DEFAULT_EXCLUDES: node_modules/, dist/, .env, __pycache__, *.pyc, .git/
"""
import sys
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHECKPOINT_BASE: Path = Path.home() / ".vector" / "checkpoints"

DEFAULT_EXCLUDES: List[str] = [
    "node_modules/",
    "dist/",
    "build/",
    ".env",
    ".env.*",
    "__pycache__/",
    "*.pyc",
    ".DS_Store",
    "*.log",
    ".git/",
]

_GIT_TIMEOUT: int = int(os.environ.get("VECTOR_CHECKPOINT_TIMEOUT", "30"))
_COMMIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate_commit_hash(commit_hash: str) -> Optional[str]:
    """Return error string if invalid, None if valid."""
    if not commit_hash or not commit_hash.strip():
        return "Empty commit hash"
    if commit_hash.startswith("-"):
        return f"Invalid commit hash (must not start with '-'): {commit_hash!r}"
    if not _COMMIT_HASH_RE.match(commit_hash):
        return f"Invalid commit hash (expected 4-64 hex chars): {commit_hash!r}"
    return None


# ---------------------------------------------------------------------------
# Shadow repo helpers
# ---------------------------------------------------------------------------

def _normalize(path: str) -> Path:
    """Return canonical absolute Path."""
    return Path(path).expanduser().resolve()


def _shadow_path(work_dir: Path) -> Path:
    """Return the shadow repo path for a work directory."""
    h = hashlib.sha256(str(work_dir).encode()).hexdigest()[:16]
    return CHECKPOINT_BASE / h


def _git_env(shadow: Path, work_dir: Path) -> dict:
    """Build env dict that redirects git to the shadow repo without polluting work_dir."""
    env = os.environ.copy()
    env["GIT_DIR"] = str(shadow)
    env["GIT_WORK_TREE"] = str(work_dir)
    env.pop("GIT_INDEX_FILE", None)
    env.pop("GIT_NAMESPACE", None)
    # Isolate from user's global git config (gpgsign, hooks, etc.)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _run_git(
    args: List[str],
    shadow: Path,
    work_dir: Path,
    timeout: int = _GIT_TIMEOUT,
    allowed_rc: Optional[set] = None,
) -> tuple:
    """Run git command against shadow repo. Returns (ok, stdout, stderr)."""
    if not work_dir.exists() or not work_dir.is_dir():
        return False, "", f"work_dir not found: {work_dir}"
    env = _git_env(shadow, work_dir)
    cmd = ["git"] + list(args)
    allowed_rc = allowed_rc or set()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(work_dir),
        )
        ok = result.returncode == 0
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if not ok and result.returncode not in allowed_rc:
            logger.debug("[VECTOR][checkpoint] git %s rc=%d stderr=%s", " ".join(args), result.returncode, stderr)
        return ok, stdout, stderr
    except subprocess.TimeoutExpired:
        msg = f"git timed out: {' '.join(cmd)}"
        logger.error("[VECTOR][checkpoint] %s", msg)
        return False, "", msg
    except FileNotFoundError:
        return False, "", "git executable not found"
    except Exception as e:
        logger.error("[VECTOR][checkpoint] git error: %s", e)
        return False, "", str(e)


def _init_shadow_repo(shadow: Path, work_dir: Path) -> Optional[str]:
    """Initialise shadow repo if needed. Returns error string or None."""
    if (shadow / "HEAD").exists():
        return None

    shadow.mkdir(parents=True, exist_ok=True)

    ok, _, err = _run_git(["init"], shadow, work_dir)
    if not ok:
        return f"Shadow repo init failed: {err}"

    _run_git(["config", "user.email", "vector@local"], shadow, work_dir)
    _run_git(["config", "user.name", "VECTOR Checkpoint"], shadow, work_dir)
    _run_git(["config", "commit.gpgsign", "false"], shadow, work_dir)
    _run_git(["config", "tag.gpgSign", "false"], shadow, work_dir)

    info_dir = shadow / "info"
    info_dir.mkdir(exist_ok=True)
    (info_dir / "exclude").write_text("\n".join(DEFAULT_EXCLUDES) + "\n", encoding="utf-8")
    (shadow / "VECTOR_WORKDIR").write_text(str(work_dir) + "\n", encoding="utf-8")

    logger.debug("[VECTOR][checkpoint] initialised shadow repo at %s", shadow)
    return None


def _has_staged_changes(shadow: Path, work_dir: Path) -> bool:
    """Return True if there are staged or unstaged changes in work_dir."""
    # Stage everything first so we can check
    _run_git(["add", "-A"], shadow, work_dir, timeout=_GIT_TIMEOUT * 2)
    ok_diff, _, _ = _run_git(
        ["diff", "--cached", "--quiet"],
        shadow,
        work_dir,
        allowed_rc={1},
    )
    # ok_diff == True means no diff (exit 0), False means there are changes (exit 1)
    return not ok_diff


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------

class CheckpointManager:
    """Manages filesystem snapshots via a shadow git repo.

    Parameters
    ----------
    work_dir : Path
        The working directory to snapshot.
    max_snapshots : int
        Maximum number of checkpoints to keep in the log view.
    """

    def __init__(self, work_dir: Path, max_snapshots: int = 50):
        self.work_dir: Path = _normalize(str(work_dir))
        self.max_snapshots = max_snapshots
        self._shadow: Path = _shadow_path(self.work_dir)
        self._git_ok: Optional[bool] = None

    def _check_git(self) -> bool:
        """Lazy check: is git available?"""
        if self._git_ok is None:
            self._git_ok = shutil.which("git") is not None
        return self._git_ok

    def _ensure_init(self) -> Optional[str]:
        """Ensure shadow repo is initialised. Returns error string or None."""
        if not self._check_git():
            return "git not found in PATH"
        err = _init_shadow_repo(self._shadow, self.work_dir)
        return err

    # ── Public methods ────────────────────────────────────────────────────

    def create_checkpoint(self, label: str = "") -> Dict[str, Any]:
        """Create a checkpoint (git commit in shadow repo) of the current state.

        Args:
            label: Human-readable description for the checkpoint.

        Returns:
            {ok, commit_hash, message}
        """
        err = self._ensure_init()
        if err:
            return {"ok": False, "commit_hash": None, "message": err}

        commit_label = label.strip() or "checkpoint"

        try:
            ok_add, _, add_err = _run_git(
                ["add", "-A"], self._shadow, self.work_dir, timeout=_GIT_TIMEOUT * 2
            )
            if not ok_add:
                return {"ok": False, "commit_hash": None, "message": f"git add failed: {add_err}"}

            # Check if there's anything new to commit
            ok_diff, _, _ = _run_git(
                ["diff", "--cached", "--quiet"],
                self._shadow,
                self.work_dir,
                allowed_rc={1},
            )
            if ok_diff:
                # Exit 0 = no diff = nothing to commit
                # Try to get HEAD hash anyway so caller has a reference
                ok_head, head_hash, _ = _run_git(
                    ["rev-parse", "HEAD"], self._shadow, self.work_dir
                )
                existing_hash = head_hash if ok_head else None
                return {
                    "ok": True,
                    "commit_hash": existing_hash,
                    "message": "No changes — checkpoint already up to date",
                }

            ok_commit, _, commit_err = _run_git(
                ["commit", "-m", commit_label, "--allow-empty-message", "--no-gpg-sign"],
                self._shadow,
                self.work_dir,
                timeout=_GIT_TIMEOUT * 2,
            )
            if not ok_commit:
                return {"ok": False, "commit_hash": None, "message": f"git commit failed: {commit_err}"}

            ok_hash, commit_hash, _ = _run_git(
                ["rev-parse", "HEAD"], self._shadow, self.work_dir
            )
            logger.info("[VECTOR][checkpoint] created checkpoint '%s' -> %s", commit_label,
                        commit_hash[:8] if commit_hash else "?")
            return {
                "ok": True,
                "commit_hash": commit_hash if ok_hash else None,
                "message": f"Checkpoint created: {commit_label}",
            }
        except Exception as e:
            logger.error("[VECTOR][checkpoint] create_checkpoint error: %s", e)
            return {"ok": False, "commit_hash": None, "message": str(e)}

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List available checkpoints, most recent first.

        Returns:
            List of {hash, label, timestamp, files_changed}
        """
        if not (self._shadow / "HEAD").exists():
            return []

        try:
            ok, stdout, _ = _run_git(
                ["log", "--format=%H|%h|%aI|%s", "-n", str(self.max_snapshots)],
                self._shadow,
                self.work_dir,
            )
            if not ok or not stdout:
                return []

            results = []
            for line in stdout.splitlines():
                parts = line.split("|", 3)
                if len(parts) == 4:
                    entry: Dict[str, Any] = {
                        "hash": parts[0],
                        "short_hash": parts[1],
                        "timestamp": parts[2],
                        "label": parts[3],
                        "files_changed": 0,
                    }
                    # Get diffstat (ignore errors for first commit that has no parent)
                    stat_ok, stat_out, _ = _run_git(
                        ["diff", "--shortstat", f"{parts[0]}~1", parts[0]],
                        self._shadow,
                        self.work_dir,
                        allowed_rc={128, 129},
                    )
                    if stat_ok and stat_out:
                        m = re.search(r"(\d+) file", stat_out)
                        if m:
                            entry["files_changed"] = int(m.group(1))
                    results.append(entry)
            return results
        except Exception as e:
            logger.error("[VECTOR][checkpoint] list_checkpoints error: %s", e)
            return []

    def restore_checkpoint(self, commit_hash: str, force: bool = False) -> Dict[str, Any]:
        """Restore working directory to a checkpoint state.

        Safety: blocks restore if work_dir has uncommitted changes unless force=True.
        Before restoring, takes a pre-rollback checkpoint so the restore is reversible.

        Args:
            commit_hash: Full or short SHA of checkpoint to restore.
            force:       Skip uncommitted-changes safety check (default False).

        Returns:
            {ok, restored_files, message}
        """
        hash_err = _validate_commit_hash(commit_hash)
        if hash_err:
            return {"ok": False, "restored_files": [], "message": hash_err}

        err = self._ensure_init()
        if err:
            return {"ok": False, "restored_files": [], "message": err}

        try:
            # Safety check for uncommitted changes
            if not force and _has_staged_changes(self._shadow, self.work_dir):
                return {
                    "ok": False,
                    "restored_files": [],
                    "message": (
                        "Work directory has uncommitted changes. "
                        "Use force=True to override, or create a checkpoint first."
                    ),
                }

            # Verify commit exists
            ok_cat, _, cat_err = _run_git(
                ["cat-file", "-t", commit_hash], self._shadow, self.work_dir
            )
            if not ok_cat:
                return {
                    "ok": False,
                    "restored_files": [],
                    "message": f"Checkpoint '{commit_hash}' not found",
                }

            # Pre-rollback snapshot so the restore itself is undoable
            self.create_checkpoint(f"pre-rollback (restoring to {commit_hash[:8]})")

            # Restore the complete tracked tree. ``checkout <hash> -- .``
            # leaves files added after the target snapshot behind.
            ok_restore, _, restore_err = _run_git(
                ["read-tree", "--reset", "-u", commit_hash],
                self._shadow,
                self.work_dir,
                timeout=_GIT_TIMEOUT * 2,
            )
            if not ok_restore:
                return {
                    "ok": False,
                    "restored_files": [],
                    "message": f"Restore failed: {restore_err}",
                }

            # List files that were restored
            ok_files, files_out, _ = _run_git(
                ["diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
                self._shadow,
                self.work_dir,
            )
            restored = files_out.splitlines() if ok_files and files_out else []

            logger.info("[VECTOR][checkpoint] restored to %s (%d files)", commit_hash[:8], len(restored))
            return {
                "ok": True,
                "restored_files": restored,
                "message": f"Restored to checkpoint {commit_hash[:8]} ({len(restored)} files)",
            }
        except Exception as e:
            logger.error("[VECTOR][checkpoint] restore_checkpoint error: %s", e)
            return {"ok": False, "restored_files": [], "message": str(e)}

    def diff_from_checkpoint(self, commit_hash: str) -> str:
        """Return unified diff between a checkpoint and current working tree.

        Args:
            commit_hash: Checkpoint hash to diff against.

        Returns:
            Unified diff string, or an error message string.
        """
        hash_err = _validate_commit_hash(commit_hash)
        if hash_err:
            return f"Error: {hash_err}"

        if not (self._shadow / "HEAD").exists():
            return "Error: No checkpoints exist for this directory"

        try:
            # Verify commit exists
            ok_cat, _, _ = _run_git(
                ["cat-file", "-t", commit_hash], self._shadow, self.work_dir
            )
            if not ok_cat:
                return f"Error: Checkpoint '{commit_hash}' not found"

            # Stage current state for comparison
            _run_git(["add", "-A"], self._shadow, self.work_dir, timeout=_GIT_TIMEOUT * 2)

            ok_diff, diff_out, diff_err = _run_git(
                ["diff", commit_hash, "--cached", "--no-color"],
                self._shadow,
                self.work_dir,
            )

            # Unstage to avoid polluting the shadow index
            _run_git(["reset", "HEAD", "--quiet"], self._shadow, self.work_dir)

            if not ok_diff and not diff_out:
                return f"Error: Could not generate diff: {diff_err}"

            return diff_out if diff_out else "(no differences)"
        except Exception as e:
            logger.error("[VECTOR][checkpoint] diff_from_checkpoint error: %s", e)
            return f"Error: {e}"


# ---------------------------------------------------------------------------
# OpenAI Function Schemas
# ---------------------------------------------------------------------------

CREATE_CHECKPOINT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_checkpoint",
        "description": (
            "Create a filesystem checkpoint (snapshot) of the current project state. "
            "Uses a shadow git repo — no .git pollution in the work directory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Human-readable label for this checkpoint (optional)",
                },
            },
            "required": [],
        },
    },
    "_meta": {"risk": "medium", "read_only": False},
}

LIST_CHECKPOINTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_checkpoints",
        "description": "List available checkpoints for the current project, most recent first.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "_meta": {"risk": "safe", "read_only": True},
}

RESTORE_CHECKPOINT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "restore_checkpoint",
        "description": (
            "Restore the project to a previous checkpoint. "
            "Blocked if there are uncommitted changes unless force=True. "
            "Automatically creates a pre-rollback checkpoint so the restore is reversible."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "commit_hash": {
                    "type": "string",
                    "description": "Full or short commit hash from list_checkpoints",
                },
                "force": {
                    "type": "boolean",
                    "description": "Override uncommitted-changes safety check (default: false)",
                    "default": False,
                },
            },
            "required": ["commit_hash"],
        },
    },
    "_meta": {"risk": "high", "read_only": False},
}

DIFF_FROM_CHECKPOINT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "diff_from_checkpoint",
        "description": "Show the unified diff between a checkpoint and the current working tree.",
        "parameters": {
            "type": "object",
            "properties": {
                "commit_hash": {
                    "type": "string",
                    "description": "Commit hash from list_checkpoints",
                },
            },
            "required": ["commit_hash"],
        },
    },
    "_meta": {"risk": "safe", "read_only": True},
}


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile

    if not shutil.which("git"):
        print("WARNING: git not found — checkpoint self-test skipped")
        print("tools/checkpoint.py OK")
        raise SystemExit(0)

    with tempfile.TemporaryDirectory() as tmp_dir:
        work = Path(tmp_dir)
        mgr = CheckpointManager(work_dir=work)

        # Write a file and create first checkpoint
        (work / "hello.txt").write_text("hello world", encoding="utf-8")
        r1 = mgr.create_checkpoint("initial")
        assert r1["ok"], f"create_checkpoint failed: {r1}"
        assert r1["commit_hash"] is not None, f"no hash in: {r1}"

        # Modify file and create second checkpoint
        (work / "hello.txt").write_text("modified content", encoding="utf-8")
        r2 = mgr.create_checkpoint("after-change")
        assert r2["ok"], f"second checkpoint failed: {r2}"

        # List checkpoints
        checkpoints = mgr.list_checkpoints()
        assert len(checkpoints) >= 2, f"expected >= 2 checkpoints, got {len(checkpoints)}"
        assert checkpoints[0]["label"] == "after-change", f"most-recent label: {checkpoints[0]}"

        # Diff from first checkpoint
        first_hash = checkpoints[-1]["hash"]  # oldest
        diff = mgr.diff_from_checkpoint(first_hash)
        assert "modified content" in diff or "hello.txt" in diff or "(no differences)" in diff, \
            f"unexpected diff: {diff[:200]}"

        # Restore to first checkpoint
        r3 = mgr.restore_checkpoint(first_hash, force=True)
        assert r3["ok"], f"restore failed: {r3}"
        content = (work / "hello.txt").read_text(encoding="utf-8")
        assert content == "hello world", f"expected 'hello world' after restore, got: {content!r}"

        # Validate bad hash
        hash_err = _validate_commit_hash("--bad")
        assert hash_err is not None

        hash_ok = _validate_commit_hash("abc123")
        assert hash_ok is None

    # Schema checks
    assert CREATE_CHECKPOINT_SCHEMA["function"]["name"] == "create_checkpoint"
    assert LIST_CHECKPOINTS_SCHEMA["function"]["name"] == "list_checkpoints"
    assert RESTORE_CHECKPOINT_SCHEMA["function"]["name"] == "restore_checkpoint"
    assert DIFF_FROM_CHECKPOINT_SCHEMA["function"]["name"] == "diff_from_checkpoint"

    print("tools/checkpoint.py OK")
