"""
VECTOR Code Conductor — Git Commit Accuracy Evaluator
Python port of codebuff/evals/git-evals/run-git-evals.ts

Measures coding agent accuracy by reconstructing git commits:
  Given: commit message + pre-commit file state
  Task: reproduce the exact file changes
  Score: % of diff hunks correctly reproduced

This is how codebuff validates real-world coding performance (61% accuracy vs 53% for single-model tools).

Usage:
    runner = GitEvalRunner(cwd="/path/to/repo")
    result = asyncio.run(runner.run_single("abc1234"))
    logger.info(result["score"])   # 0.0 to 1.0


    suite = asyncio.run(runner.run_suite(num_commits=10))
    logger.info(suite["avg_score"])

"""
from __future__ import annotations

__all__ = [
    "EvalResult",
    "GitEvalRunner",
    "HunkResult",
]


import asyncio
import difflib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


@dataclass
class HunkResult:
    file: str
    hunk_index: int
    matched: bool
    target_hunk: str
    agent_hunk: str


@dataclass
class EvalResult:
    commit_sha: str
    commit_message: str
    score: float               # 0.0 to 1.0
    hunks_correct: int
    hunks_total: int
    hunk_results: list[HunkResult] = field(default_factory=list)
    agent_diff: str = ""
    target_diff: str = ""
    error: str = ""


def _reject_option_like(sha: str) -> None:
    """commit_sha is caller-supplied to run_single(); a value starting with
    "-" (e.g. "--output=<path>", a real arbitrary-file-write primitive on
    both `git log`/`git diff`) would be parsed as an option, not a
    revision. A plain "--" separator does NOT fix this here the way it
    does for other git subcommands this cycle (vectorcode/src/tools/
    git_tools.py, worktree.py) -- `git log`/`git diff` give `--` its own
    revision/path-separator meaning, so inserting one would silently
    change these calls to filter by path instead of looking up the
    commit (verified: `git log --pretty=%s -- <sha>` returns empty where
    `git log --pretty=%s <sha>` returns the real message). Validate
    instead. The one real production caller (run_suite(), via
    districts/coding/code_conductor_agent.py) only ever passes SHAs it
    just read from `git log --pretty=%H` itself, so this is dormant
    today -- fixed anyway, same bar as this cycle's other narrow/
    no-legitimate-caller-risk findings."""
    if sha.startswith("-"):
        raise ValueError(f"invalid commit sha: {sha!r}")


def _run_git(args: list[str], cwd: str, check: bool = True) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr[:200]}")
    return result.stdout.strip()


def _parse_hunks(diff_text: str) -> list[dict]:
    """Split a unified diff into individual hunks per file."""
    hunks: list[dict] = []
    current_file = ""
    current_hunk: list[str] = []
    in_hunk = False

    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git"):
            if in_hunk and current_hunk:
                hunks.append({"file": current_file, "hunk": "".join(current_hunk)})
                current_hunk = []
            in_hunk = False
        elif line.startswith("--- a/") or line.startswith("+++ b/"):
            if line.startswith("+++ b/"):
                current_file = line[6:].strip()
        elif line.startswith("@@"):
            if current_hunk:
                hunks.append({"file": current_file, "hunk": "".join(current_hunk)})
            current_hunk = [line]
            in_hunk = True
        elif in_hunk:
            current_hunk.append(line)

    if in_hunk and current_hunk:
        hunks.append({"file": current_file, "hunk": "".join(current_hunk)})

    return hunks


def _hunk_similarity(hunk_a: str, hunk_b: str) -> float:
    """Similarity ratio between two diff hunks."""
    return difflib.SequenceMatcher(None, hunk_a, hunk_b).ratio()


class GitEvalRunner:
    """
    Evaluates coding agent accuracy on real git commits.
    Port of codebuff's git-evals methodology.
    """

    def __init__(self, cwd: str | None = None, similarity_threshold: float = 0.8) -> None:
        self._cwd = cwd or os.getcwd()
        self._threshold = similarity_threshold

    def _verify_repo(self) -> bool:
        try:
            _run_git(["rev-parse", "--git-dir"], self._cwd)
            return True
        except Exception:
            return False

    def _get_commit_info(self, sha: str) -> tuple[str, str]:
        """Returns (message, parent_sha)."""
        _reject_option_like(sha)
        message = _run_git(["log", "-1", "--pretty=%s", sha], self._cwd)
        parent = _run_git(["rev-parse", f"{sha}^"], self._cwd)
        return message, parent

    def _get_target_diff(self, sha: str) -> str:
        """Get the actual diff introduced by this commit."""
        _reject_option_like(sha)
        return _run_git(["diff", f"{sha}^", sha], self._cwd)

    def _checkout_pre_commit(self, parent_sha: str, tmp_dir: str) -> str:
        """Create a worktree at the parent commit state."""
        _reject_option_like(parent_sha)
        worktree = os.path.join(tmp_dir, "pre_commit")
        _run_git(["worktree", "add", "--detach", worktree, parent_sha], self._cwd)
        return worktree

    def _cleanup_worktree(self, worktree: str) -> None:
        try:
            _run_git(["worktree", "remove", "--force", worktree], self._cwd, check=False)
        except Exception as e:
            logger.warning("[VECTOR][git_eval] worktree cleanup failed for {}: {}", worktree, e)

    def _score_diffs(
        self, target_diff: str, agent_diff: str, sha: str, message: str
    ) -> EvalResult:
        """Compare target and agent diffs hunk by hunk."""
        target_hunks = _parse_hunks(target_diff)
        agent_hunks  = _parse_hunks(agent_diff)

        if not target_hunks:
            return EvalResult(
                commit_sha=sha, commit_message=message,
                score=1.0, hunks_correct=0, hunks_total=0,
                target_diff=target_diff, agent_diff=agent_diff,
            )

        hunk_results: list[HunkResult] = []
        matched = 0

        for i, t_hunk in enumerate(target_hunks):
            best_score = 0.0
            best_match = False
            for a_hunk in agent_hunks:
                if a_hunk["file"] == t_hunk["file"]:
                    sim = _hunk_similarity(t_hunk["hunk"], a_hunk["hunk"])
                    best_score = max(best_score, sim)

            matched_this = best_score >= self._threshold
            if matched_this:
                matched += 1

            hunk_results.append(HunkResult(
                file=t_hunk["file"],
                hunk_index=i,
                matched=matched_this,
                target_hunk=t_hunk["hunk"][:200],
                agent_hunk="",
            ))

        score = matched / len(target_hunks) if target_hunks else 1.0

        return EvalResult(
            commit_sha=sha,
            commit_message=message,
            score=score,
            hunks_correct=matched,
            hunks_total=len(target_hunks),
            hunk_results=hunk_results,
            target_diff=target_diff,
            agent_diff=agent_diff,
        )

    async def run_single(self, commit_sha: str) -> dict:
        """
        Evaluate agent accuracy on one commit.
        Returns {commit_sha, message, score, hunks_correct, hunks_total, error}.
        """
        if not self._verify_repo():
            return {"error": f"Not a git repo: {self._cwd}", "score": 0.0}

        try:
            message, parent_sha = self._get_commit_info(commit_sha)
            target_diff = self._get_target_diff(commit_sha)

            # Set up pre-commit state in a worktree
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    worktree = self._checkout_pre_commit(parent_sha, tmp)
                except Exception:
                    # Worktree may not be supported — use git show instead
                    worktree = self._cwd

                # Run the coding orchestrator on the pre-commit state
                from core.code_conductor.orchestrator import CodingOrchestrator
                orch = CodingOrchestrator(cwd=worktree)
                await orch.run(message)

                # Get the agent's diff
                try:
                    agent_diff = _run_git(["diff", "HEAD"], worktree, check=False)
                except Exception:
                    agent_diff = ""

                self._cleanup_worktree(worktree)

            result = self._score_diffs(target_diff, agent_diff, commit_sha, message)
            logger.info("[VECTOR][git_eval] {} score={:.2f} ({}/{})",
                        commit_sha[:8], result.score, result.hunks_correct, result.hunks_total)

            return {
                "commit_sha":    result.commit_sha,
                "message":       result.commit_message,
                "score":         round(result.score, 3),
                "hunks_correct": result.hunks_correct,
                "hunks_total":   result.hunks_total,
                "error":         result.error,
            }

        except Exception as e:
            logger.error("[VECTOR][git_eval] error on {}: {}", commit_sha[:8], e)
            return {"commit_sha": commit_sha, "score": 0.0, "error": str(e)}

    async def run_suite(self, num_commits: int = 10) -> dict:
        """
        Run accuracy eval across multiple recent commits.
        Returns {avg_score, results, num_commits}.
        """
        if not self._verify_repo():
            return {"error": f"Not a git repo: {self._cwd}", "avg_score": 0.0}

        # Get recent non-merge commits
        log = _run_git(
            ["log", f"-{num_commits * 2}", "--no-merges", "--pretty=%H"],
            self._cwd
        )
        shas = log.splitlines()[:num_commits]

        if not shas:
            return {"avg_score": 0.0, "results": [], "error": "No commits found"}

        results = []
        for sha in shas:
            r = await self.run_single(sha)
            results.append(r)

        scores = [r["score"] for r in results if "error" not in r or not r.get("error")]
        avg = sum(scores) / len(scores) if scores else 0.0

        return {
            "avg_score":   round(avg, 3),
            "num_commits": len(results),
            "results":     results,
        }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        runner = GitEvalRunner()
        is_repo = runner._verify_repo()
        print(f"OK git_eval.py — GitEvalRunner init")
        print(f"  cwd={runner._cwd}")
        print(f"  is_git_repo={is_repo}")
        if is_repo:
            recent = _run_git(["log", "-1", "--pretty=%H %s"], runner._cwd, check=False)
            print(f"  latest commit: {recent[:80]}")
        print(f"  run_suite(5) ready — starts CodingOrchestrator per commit")

    asyncio.run(_smoke())
