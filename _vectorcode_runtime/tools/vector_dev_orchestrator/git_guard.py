"""Baseline-aware Git change detection for the VECTOR dev orchestrator."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileState:
    """Git-visible state for one working-tree path."""

    status: str
    content_hash: str | None


@dataclass(frozen=True, slots=True)
class GitSnapshot:
    """Point-in-time snapshot of Git-visible working-tree changes."""

    files: dict[str, FileState] = field(default_factory=dict)
    head: str | None = None


@dataclass(frozen=True, slots=True)
class GitDelta:
    """Files that changed between two snapshots."""

    changed_files: tuple[str, ...]
    added_files: tuple[str, ...]
    removed_files: tuple[str, ...]
    head_changed: bool = False

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_files)


class GitGuard:
    """Inspect working-tree changes without mutating Git state."""

    def __init__(
        self,
        repo_root: Path,
        *,
        executable: str | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()

        resolved = executable or shutil.which("git")

        if not resolved:
            raise RuntimeError("git executable was not found")

        self.executable = resolved

        self._verify_repository()

    def snapshot(self) -> GitSnapshot:
        """Capture Git-visible dirty/untracked paths and their contents."""

        statuses = self._status_entries()

        files: dict[str, FileState] = {}

        for path_text, status in statuses.items():
            path = self.repo_root / path_text

            files[path_text] = FileState(
                status=status,
                content_hash=self._hash_path(path),
            )

        return GitSnapshot(
            files=files,
            head=self._current_head(),
        )

    def diff(
        self,
        before: GitSnapshot,
        after: GitSnapshot,
    ) -> GitDelta:
        """Return files whose state/content changed across the task.

        A provider CLI can run a hook that commits mid-task despite the
        orchestrator's hook suppression flags. A commit leaves the working
        tree clean, so working-tree-status comparison alone would miss it.
        Detect an advancing HEAD and fold in the committed file paths so a
        real change is never misreported as "no files changed".
        """

        before_paths = set(before.files)
        after_paths = set(after.files)

        added = set(after_paths - before_paths)
        removed = sorted(before_paths - after_paths)

        changed: set[str] = set(added)
        changed.update(removed)

        for path in before_paths & after_paths:
            if before.files[path] != after.files[path]:
                changed.add(path)

        head_changed = (
            before.head is not None
            and after.head is not None
            and before.head != after.head
        )

        if head_changed:
            committed_files = self._committed_files(
                before.head,
                after.head,
            )

            changed.update(committed_files)
            added.update(
                path
                for path in committed_files
                if path not in before_paths
            )

        return GitDelta(
            changed_files=tuple(sorted(changed)),
            added_files=tuple(sorted(added)),
            removed_files=tuple(removed),
            head_changed=head_changed,
        )

    def _current_head(self) -> str | None:
        result = self._run(
            [
                "rev-parse",
                "HEAD",
            ]
        )

        head = result.stdout.strip()

        return head or None

    def _committed_files(
        self,
        before_head: str,
        after_head: str,
    ) -> list[str]:
        result = self._run(
            [
                "diff",
                "--name-only",
                before_head,
                after_head,
            ]
        )

        return [
            line
            for line in result.stdout.splitlines()
            if line.strip()
        ]

    def _verify_repository(self) -> None:
        result = self._run(
            [
                "rev-parse",
                "--is-inside-work-tree",
            ]
        )

        if result.stdout.strip() != "true":
            raise RuntimeError(
                f"Not inside a Git working tree: {self.repo_root}"
            )

    def _status_entries(self) -> dict[str, str]:
        result = self._run(
            [
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ]
        )

        payload = result.stdout

        if not payload:
            return {}

        parts = payload.split("\0")
        entries: dict[str, str] = {}

        index = 0

        while index < len(parts):
            entry = parts[index]

            if not entry:
                index += 1
                continue

            if len(entry) < 4:
                raise RuntimeError(
                    f"Unexpected git status entry: {entry!r}"
                )

            status = entry[:2]
            path_text = entry[3:]

            if status.startswith("R") or status.startswith("C"):
                index += 1

                if index >= len(parts):
                    raise RuntimeError(
                        "Malformed Git rename/copy status output"
                    )

                destination = parts[index]

                if not destination:
                    raise RuntimeError(
                        "Git rename/copy destination was empty"
                    )

                entries[path_text] = status
                entries[destination] = status
            else:
                entries[path_text] = status

            index += 1

        return entries

    @staticmethod
    def _hash_path(path: Path) -> str | None:
        """Hash a file's current contents; deleted paths return None."""

        if not path.exists() or not path.is_file():
            return None

        digest = hashlib.sha256()

        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)

                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()

    def _run(
        self,
        args: list[str],
    ) -> subprocess.CompletedProcess[str]:
        command = [
            self.executable,
            "-C",
            str(self.repo_root),
            *args,
        ]

        result = subprocess.run(
            command,
            cwd=self.repo_root,
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Git command failed:\n"
                f"command: {' '.join(command)}\n"
                f"exit: {result.returncode}\n"
                f"stderr: {result.stderr.strip()}"
            )

        return result


def _self_test() -> None:
    """Use an isolated temporary repository; never touch VECTOR Git state."""

    with tempfile.TemporaryDirectory(
        prefix="vector_git_guard_"
    ) as temp_dir:
        repo = Path(temp_dir)

        git = shutil.which("git")

        if not git:
            raise RuntimeError(
                "git executable was not found"
            )

        def run_git(*args: str) -> None:
            result = subprocess.run(
                [
                    git,
                    "-C",
                    str(repo),
                    *args,
                ],
                shell=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    result.stderr
                )

        run_git("init")
        run_git(
            "config",
            "user.email",
            "vector-orchestrator@test.local",
        )
        run_git(
            "config",
            "user.name",
            "VECTOR Orchestrator Test",
        )

        tracked = repo / "tracked.txt"
        tracked.write_text(
            "baseline\n",
            encoding="utf-8",
        )

        run_git("add", "tracked.txt")
        run_git(
            "commit",
            "-m",
            "baseline",
        )

        preexisting = repo / "preexisting.txt"
        preexisting.write_text(
            "already dirty\n",
            encoding="utf-8",
        )

        guard = GitGuard(repo)

        before = guard.snapshot()

        assert "preexisting.txt" in before.files
        assert "tracked.txt" not in before.files

        tracked.write_text(
            "changed by task\n",
            encoding="utf-8",
        )

        preexisting.write_text(
            "changed during task\n",
            encoding="utf-8",
        )

        new_file = repo / "new_file.txt"
        new_file.write_text(
            "new\n",
            encoding="utf-8",
        )

        after = guard.snapshot()

        delta = guard.diff(
            before,
            after,
        )

        assert delta.has_changes

        assert delta.changed_files == (
            "new_file.txt",
            "preexisting.txt",
            "tracked.txt",
        )

        assert delta.added_files == (
            "new_file.txt",
            "tracked.txt",
        )

        assert delta.removed_files == ()

        assert not delta.head_changed

        # A provider hook can commit mid-task and leave the working tree
        # clean, hiding the change from working-tree-status comparison.
        # HEAD-aware detection must still catch the real file change.
        hidden_before = guard.snapshot()

        hook_file = repo / "hook_committed.txt"
        hook_file.write_text(
            "committed by hook\n",
            encoding="utf-8",
        )

        run_git("add", "hook_committed.txt")
        run_git(
            "commit",
            "-m",
            "auto: hook_committed.txt",
        )

        hidden_after = guard.snapshot()

        hidden_delta = guard.diff(
            hidden_before,
            hidden_after,
        )

        assert hidden_delta.head_changed
        assert hidden_delta.has_changes
        assert "hook_committed.txt" in hidden_delta.changed_files
        assert "hook_committed.txt" in hidden_delta.added_files


if __name__ == "__main__":
    _self_test()
