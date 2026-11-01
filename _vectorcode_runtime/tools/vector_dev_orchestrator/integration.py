"""Integration stage: collect passed task branches on ONE reviewable branch.

Merges each PASSED + committed task branch into a dedicated
`vector-integration` branch (checked out in its own sibling worktree), so
the owner can review and promote the whole batch with one command.

Hard rules (covered by the self-test):
  - the owner's live branch is never checked out, merged into, or moved
  - each task branch is merged with --no-commit, the item's targeted tests
    run on the merged tree, and the merge is committed ONLY if they pass;
    a conflict or a test failure cancels that one merge (git merge --abort
    inside the integration worktree only) and flags the item
  - the live branch's newest commits are merged INTO the integration branch
    first, so it stays promotable; a conflict there stops the whole stage
  - nothing is pushed, reset, cleaned or deleted; failing items stay
    unintegrated with their task branches intact
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

INTEGRATION_BRANCH = "vector-integration"
_TASK_PREFIX = "vector-dev/"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("git")

    if executable is None:
        raise RuntimeError("git executable was not found")

    return subprocess.run(
        [executable, "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )


@dataclass(slots=True)
class IntegrationOutcome:
    item_id: str
    result: str  # merged | conflict | tests_failed
    commit: str | None = None
    detail: str = ""


@dataclass(slots=True)
class IntegrationReport:
    live_branch: str = ""
    outcomes: list[IntegrationOutcome] = field(default_factory=list)
    stopped: str = ""


class IntegrationStage:
    def __init__(self, repo_root: Path, worktree_root: Path | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        root = worktree_root or self.repo_root.parent / ".vector_dev_worktrees"
        self.worktree = Path(root) / "_integration"

    def live_branch(self) -> str:
        proc = _git(self.repo_root, "rev-parse", "--abbrev-ref", "HEAD")
        return proc.stdout.strip() if proc.returncode == 0 else ""

    def _ensure_worktree(self, live: str) -> str:
        """Create the integration worktree if needed; return '' or an error."""

        if self.worktree.exists():
            return ""

        self.worktree.parent.mkdir(parents=True, exist_ok=True)
        exists = _git(
            self.repo_root, "show-ref", "--verify", "--quiet",
            f"refs/heads/{INTEGRATION_BRANCH}",
        ).returncode == 0

        args = (
            ["worktree", "add", str(self.worktree), INTEGRATION_BRANCH]
            if exists
            else ["worktree", "add", "-b", INTEGRATION_BRANCH,
                  str(self.worktree), live]
        )
        proc = _git(self.repo_root, *args)

        return "" if proc.returncode == 0 else proc.stderr.strip()[-300:]

    def _merge_in_progress(self) -> bool:
        return _git(
            self.worktree, "rev-parse", "-q", "--verify", "MERGE_HEAD"
        ).returncode == 0

    def integrate(
        self,
        items: list,
        run_tests_fn: Callable[[Path, list[str]], bool],
    ) -> IntegrationReport:
        """Merge each pending item (needs .item_id/.commit/.test_targets/.title)."""

        report = IntegrationReport(live_branch=self.live_branch())
        live = report.live_branch

        if not live or live.startswith((_TASK_PREFIX, INTEGRATION_BRANCH)) or live == "HEAD":
            report.stopped = f"Unsafe or detached live branch: {live!r}"
            return report

        error = self._ensure_worktree(live)

        if error:
            report.stopped = f"Could not create integration worktree: {error}"
            return report

        branch = _git(self.worktree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

        if branch != INTEGRATION_BRANCH:
            report.stopped = f"Integration worktree is on {branch!r}, not {INTEGRATION_BRANCH}."
            return report

        if self._merge_in_progress() or _git(self.worktree, "status", "--porcelain").stdout.strip():
            report.stopped = "Integration worktree is dirty or mid-merge; needs a human."
            return report

        # Keep the integration branch current with the live branch.
        sync = _git(self.worktree, "merge", "--no-edit", live)

        if sync.returncode != 0:
            _git(self.worktree, "merge", "--abort")
            report.stopped = f"Live branch {live!r} conflicts with integration branch; needs a human."
            return report

        for item in items:
            outcome = self._merge_item(item, run_tests_fn)
            report.outcomes.append(outcome)

        return report

    def _merge_item(
        self,
        item,
        run_tests_fn: Callable[[Path, list[str]], bool],
    ) -> IntegrationOutcome:
        if _git(self.worktree, "cat-file", "-e", f"{item.commit}^{{commit}}").returncode != 0:
            return IntegrationOutcome(item.item_id, "conflict", detail="Task commit not found.")

        merge = _git(self.worktree, "merge", "--no-ff", "--no-commit", item.commit)

        if merge.returncode != 0:
            _git(self.worktree, "merge", "--abort")
            return IntegrationOutcome(
                item.item_id, "conflict",
                detail=(merge.stdout + merge.stderr).strip()[-300:],
            )

        if not self._merge_in_progress():
            # Already contained in the integration branch.
            head = _git(self.worktree, "rev-parse", "HEAD").stdout.strip()
            return IntegrationOutcome(item.item_id, "merged", head, "already contained")

        if not run_tests_fn(self.worktree, list(item.test_targets)):
            _git(self.worktree, "merge", "--abort")
            return IntegrationOutcome(
                item.item_id, "tests_failed",
                detail="Targeted tests failed on the merged tree; merge cancelled.",
            )

        title = getattr(item, "title", "") or item.item_id
        commit = _git(
            self.worktree, "commit", "-m",
            f"integrate: {title}\n\nBacklog item {item.item_id}; targeted tests passed "
            "on the merged tree. Not promoted to the live branch.",
        )

        if commit.returncode != 0:
            _git(self.worktree, "merge", "--abort")
            return IntegrationOutcome(
                item.item_id, "conflict",
                detail=f"Merge commit failed: {(commit.stderr or commit.stdout).strip()[-200:]}",
            )

        return IntegrationOutcome(
            item.item_id, "merged",
            _git(self.worktree, "rev-parse", "HEAD").stdout.strip(),
        )

    def summary(self) -> dict:
        """Read-only view for `status`: how far the integration branch is ahead."""

        live = self.live_branch()
        exists = _git(
            self.repo_root, "show-ref", "--verify", "--quiet",
            f"refs/heads/{INTEGRATION_BRANCH}",
        ).returncode == 0

        if not exists or not live:
            return {"branch": INTEGRATION_BRANCH, "exists": exists}

        ahead = _git(
            self.repo_root, "rev-list", "--count", f"{live}..{INTEGRATION_BRANCH}"
        ).stdout.strip()

        return {
            "branch": INTEGRATION_BRANCH,
            "exists": True,
            "commits_ahead_of_live": int(ahead or 0),
            "promote_command": f"git merge --no-ff {INTEGRATION_BRANCH}  (run on {live}, after reviewing)",
        }


def _self_test() -> None:
    import tempfile
    from types import SimpleNamespace

    temp = Path(tempfile.mkdtemp(prefix="vector_integ_test_"))

    def sh(cwd: Path, *args: str) -> str:
        proc = _git(cwd, *args)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    try:
        repo = temp / "repo"
        repo.mkdir()
        sh(repo, "init", "-b", "livebranch")
        sh(repo, "config", "user.email", "integ@example.invalid")
        sh(repo, "config", "user.name", "Integ Test")
        (repo / "shared.txt").write_text("line1\nline2\n", encoding="utf-8")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        (repo / "b.txt").write_text("b\n", encoding="utf-8")
        sh(repo, "add", ".")
        sh(repo, "commit", "-m", "base")
        base = sh(repo, "rev-parse", "HEAD")

        def task_branch(name: str, files: dict[str, str]) -> str:
            sh(repo, "checkout", "-q", "-b", f"vector-dev/{name}", base)
            for rel, text in files.items():
                (repo / rel).write_text(text, encoding="utf-8")
            sh(repo, "add", ".")
            sh(repo, "commit", "-m", f"task {name}")
            sha = sh(repo, "rev-parse", "HEAD")
            sh(repo, "checkout", "-q", "livebranch")
            return sha

        def item(item_id: str, sha: str) -> SimpleNamespace:
            return SimpleNamespace(
                item_id=item_id, commit=sha, test_targets=["t.py"], title=f"title {item_id}"
            )

        ok_sha = task_branch("ok", {"a.txt": "a changed\n"})
        clash1 = task_branch("clash1", {"shared.txt": "line1 X\nline2\n"})
        clash2 = task_branch("clash2", {"shared.txt": "line1 Y\nline2\n"})
        bad_sha = task_branch("bad", {"b.txt": "b broken\n"})

        stage = IntegrationStage(repo, temp / "wts")
        seen_dirty: list[bool] = []

        def tests(wt: Path, targets: list[str]) -> bool:
            seen_dirty.append(True)
            return not (wt / "b.txt").read_text(encoding="utf-8").startswith("b broken")

        report = stage.integrate(
            [item("ok", ok_sha), item("clash1", clash1), item("clash2", clash2), item("bad", bad_sha)],
            tests,
        )
        results = {o.item_id: o.result for o in report.outcomes}

        assert report.stopped == "", report.stopped
        assert results == {
            "ok": "merged", "clash1": "merged",
            "clash2": "conflict", "bad": "tests_failed",
        }, results

        wt = stage.worktree
        assert sh(wt, "rev-parse", "--abbrev-ref", "HEAD") == INTEGRATION_BRANCH
        assert (wt / "a.txt").read_text(encoding="utf-8") == "a changed\n"
        assert (wt / "shared.txt").read_text(encoding="utf-8").startswith("line1 X")
        assert (wt / "b.txt").read_text(encoding="utf-8") == "b\n", "failed item not merged"
        assert sh(wt, "status", "--porcelain") == "", "tree clean after aborts"
        assert not stage._merge_in_progress()

        # The live branch never moved and is still the checked-out branch.
        assert sh(repo, "rev-parse", "livebranch") == base
        assert sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "livebranch"
        assert sh(repo, "status", "--porcelain") == ""

        # Idempotent re-run over the same already-merged item.
        again = stage.integrate([item("ok", ok_sha)], lambda w, t: True)
        assert again.outcomes[0].result == "merged"
        assert again.outcomes[0].detail == "already contained"

        # New live commits are merged INTO the integration branch.
        (repo / "live_only.txt").write_text("live\n", encoding="utf-8")
        sh(repo, "add", "live_only.txt")
        sh(repo, "commit", "-m", "live moves on")
        live_tip = sh(repo, "rev-parse", "livebranch")
        stage.integrate([], lambda w, t: True)
        assert (wt / "live_only.txt").exists()
        assert sh(repo, "rev-parse", "livebranch") == live_tip

        summary = stage.summary()
        assert summary["exists"] and summary["commits_ahead_of_live"] >= 2
        assert "git merge --no-ff vector-integration" in summary["promote_command"]

        # A dirty integration worktree stops the stage (needs a human).
        (wt / "stray.txt").write_text("x", encoding="utf-8")
        blocked = stage.integrate([item("ok", ok_sha)], lambda w, t: True)
        assert "dirty" in blocked.stopped and blocked.outcomes == []
        (wt / "stray.txt").unlink()

        # Refuses to run when the repo is on a task or integration branch.
        sh(repo, "checkout", "-q", "vector-dev/ok")
        assert "Unsafe" in stage.integrate([], lambda w, t: True).stopped
        sh(repo, "checkout", "-q", "livebranch")
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    _self_test()
