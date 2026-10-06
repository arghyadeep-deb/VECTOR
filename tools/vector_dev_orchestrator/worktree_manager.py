"""Safe Git worktree management for VECTOR development tasks."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorktreeInfo:
    task_id: str
    branch_name: str
    path: Path
    base_ref: str


class WorktreeManager:
    """Create and remove isolated task worktrees without touching unrelated state."""

    def __init__(
        self,
        repo_root: Path,
        worktree_root: Path | None = None,
        *,
        git_executable: str | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()

        executable = git_executable or shutil.which("git")

        if executable is None:
            raise RuntimeError("Git executable not found.")

        self.git_executable = executable

        self.worktree_root = (
            Path(worktree_root).resolve()
            if worktree_root is not None
            else self.repo_root.parent / ".vector_dev_worktrees"
        )

        self._verify_repo()

    def create(
        self,
        task_id: str,
        *,
        base_ref: str = "HEAD",
    ) -> WorktreeInfo:
        safe_task_id = self._sanitize_task_id(task_id)

        branch_name = f"vector-dev/{safe_task_id}"
        path = self.worktree_root / safe_task_id

        if path.exists():
            raise RuntimeError(
                f"Worktree path already exists: {path}"
            )

        if self._branch_exists(branch_name):
            raise RuntimeError(
                f"Task branch already exists: {branch_name}"
            )

        self.worktree_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._run(
            [
                "worktree",
                "add",
                "-b",
                branch_name,
                "--",
                str(path),
                base_ref,
            ]
        )

        return WorktreeInfo(
            task_id=task_id,
            branch_name=branch_name,
            path=path,
            base_ref=base_ref,
        )

    def attach(self, task_id: str) -> WorktreeInfo:
        """Re-open an EXISTING task worktree (never creates or alters one).

        Used to resume a task that stopped at WAITING_REVIEW. Fails closed
        if the directory or branch is missing or the checkout is on another
        branch.
        """

        safe_task_id = self._sanitize_task_id(task_id)
        branch_name = f"vector-dev/{safe_task_id}"
        path = self.worktree_root / safe_task_id

        if not path.is_dir() or not self._branch_exists(branch_name):
            raise RuntimeError(f"No existing worktree/branch for task {task_id}")

        proc = subprocess.run(
            [self.git_executable, "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, shell=False, check=False,
        )

        if proc.returncode != 0 or proc.stdout.strip() != branch_name:
            raise RuntimeError(
                f"Worktree {path} is not on {branch_name} "
                f"(found {proc.stdout.strip()!r}); refusing to resume."
            )

        return WorktreeInfo(task_id=task_id, branch_name=branch_name, path=path, base_ref="")

    def remove(
        self,
        info: WorktreeInfo,
        *,
        delete_branch: bool = False,
    ) -> None:
        if info.path.exists():
            self._run(
                [
                    "worktree",
                    "remove",
                    str(info.path),
                ]
            )

        if delete_branch and self._branch_exists(
            info.branch_name
        ):
            self._run(
                [
                    "branch",
                    "-D",
                    info.branch_name,
                ]
            )

    def list_porcelain(self) -> str:
        result = self._run(
            [
                "worktree",
                "list",
                "--porcelain",
            ]
        )

        return result.stdout

    def _verify_repo(self) -> None:
        result = self._run(
            [
                "rev-parse",
                "--show-toplevel",
            ]
        )

        detected = Path(
            result.stdout.strip()
        ).resolve()

        if detected != self.repo_root:
            raise RuntimeError(
                "repo_root does not match Git top-level. "
                f"Expected {self.repo_root}, got {detected}."
            )

    def _branch_exists(
        self,
        branch_name: str,
    ) -> bool:
        result = subprocess.run(
            [
                self.git_executable,
                "-C",
                str(self.repo_root),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{branch_name}",
            ],
            capture_output=True,
            text=True,
            shell=False,
        )

        if result.returncode == 0:
            return True

        if result.returncode == 1:
            return False

        raise RuntimeError(
            "Git branch lookup failed: "
            f"{result.stderr.strip()}"
        )

    def _run(
        self,
        args: list[str],
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                self.git_executable,
                "-C",
                str(self.repo_root),
                *args,
            ],
            capture_output=True,
            text=True,
            shell=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Git command failed: "
                f"{' '.join(args)}\n"
                f"{result.stderr.strip()}"
            )

        return result

    @staticmethod
    def _sanitize_task_id(
        task_id: str,
    ) -> str:
        cleaned = re.sub(
            r"[^A-Za-z0-9._-]+",
            "-",
            task_id.strip(),
        )

        cleaned = cleaned.strip(".-_")

        if not cleaned:
            raise ValueError(
                "task_id must contain at least one safe character."
            )

        if len(cleaned) > 80:
            cleaned = cleaned[:80].rstrip(".-_")

        if not cleaned:
            raise ValueError(
                "task_id became empty after sanitization."
            )

        return cleaned


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()

        git = shutil.which("git")

        if git is None:
            raise RuntimeError("Git executable not found.")

        def run(*args: str) -> None:
            result = subprocess.run(
                [
                    git,
                    "-C",
                    str(root),
                    *args,
                ],
                capture_output=True,
                text=True,
                shell=False,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    result.stderr
                )

        run("init")
        run(
            "config",
            "user.email",
            "vector-test@example.invalid",
        )
        run(
            "config",
            "user.name",
            "VECTOR Test",
        )

        tracked = root / "tracked.txt"
        tracked.write_text(
            "baseline\n",
            encoding="utf-8",
        )

        run("add", "tracked.txt")
        run(
            "commit",
            "-m",
            "baseline",
        )

        worktree_root = (
            Path(temp_dir)
            / "worktrees"
        )

        manager = WorktreeManager(
            root,
            worktree_root,
            git_executable=git,
        )

        info = manager.create(
            "task 123",
        )

        assert info.branch_name == (
            "vector-dev/task-123"
        )

        assert info.path.exists()

        assert (
            info.path
            / "tracked.txt"
        ).read_text(
            encoding="utf-8"
        ) == "baseline\n"

        listing = manager.list_porcelain()

        assert str(info.path).replace(
            "\\",
            "/",
        ).lower() in listing.replace(
            "\\",
            "/",
        ).lower()

        manager.remove(
            info,
            delete_branch=True,
        )

        assert not info.path.exists()

        assert not manager._branch_exists(
            info.branch_name
        )


if __name__ == "__main__":
    _self_test()
