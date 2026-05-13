"""Checkpoint manager — git-based filesystem snapshots before mutations."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CheckpointManager:
    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path.cwd()
        self._enabled = self._is_git_repo()

    def _is_git_repo(self) -> bool:
        try:
            subprocess.run(["git", "rev-parse", "--git-dir"],
                           cwd=self.repo_root, capture_output=True, check=True)
            return True
        except Exception:
            return False

    def create_checkpoint(self, label: str = "auto") -> Optional[str]:
        if not self._enabled:
            return None
        try:
            result = subprocess.run(
                ["git", "stash", "push", "-m", f"vc-checkpoint: {label}"],
                cwd=self.repo_root, capture_output=True, text=True, timeout=30,
            )
            if "No local changes" in result.stdout:
                return None
            sha = subprocess.run(
                ["git", "stash", "list", "-1", "--format=%H"],
                cwd=self.repo_root, capture_output=True, text=True, timeout=10,
            )
            sha_str = sha.stdout.strip()
            logger.info(f"Checkpoint created: {sha_str or '?'}")
            return sha_str or "created"
        except Exception as e:
            logger.warning(f"Checkpoint failed: {e}")
            return None

    def restore(self, checkpoint_id: str = "0") -> bool:
        if not self._enabled:
            return False
        try:
            subprocess.run(["git", "stash", "apply", f"stash@{{{checkpoint_id}}}"],
                           cwd=self.repo_root, capture_output=True, timeout=30, check=True)
            logger.info(f"Restored checkpoint: {checkpoint_id}")
            return True
        except Exception as e:
            logger.warning(f"Restore failed: {e}")
            return False
