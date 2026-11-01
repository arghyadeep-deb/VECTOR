"""SubdirectoryHintTracker — tracks explored paths, suggests unexplored areas.

When an agent is working in a large codebase and keeps focusing on the same
directories, this tracker notices which subdirectories haven't been explored
and injects hints like:
  "You haven't looked at src/auth/ yet (12 files). It may be relevant."
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


try:
    from core.config import CONFIG  # noqa: F401
except ImportError:
    CONFIG = {}

from loguru import logger


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class SubdirStats:
    path: str                   # relative path string (e.g. "src/auth")
    visit_count: int = 0
    last_visited: str = ""      # ISO-8601 UTC timestamp
    file_count: int = 0         # number of direct files (non-recursive)


# ── Tracker ───────────────────────────────────────────────────────────────────

# Directories that are never interesting to hint about
_IGNORE_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".eggs", "htmlcov", "site-packages",
})


class SubdirectoryHintTracker:
    """
    Tracks which subdirectories the agent has accessed during a session.
    Injects context hints about unexplored areas.

    Usage:
        tracker = SubdirectoryHintTracker(project_dir="/path/to/project")
        tracker.on_file_access("/path/to/project/src/auth/login.py")
        hints = tracker.get_hints()
        # ["Consider checking tests/ (8 files) — you haven't visited it yet."]
    """

    def __init__(
        self,
        project_dir: str = ".",
        *,
        max_depth: int = 3,
        top_k: int = 5,
    ) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.max_depth   = max_depth
        self.top_k       = top_k

        self._visited: dict[str, SubdirStats] = {}     # relative subdir → stats
        self._all_subdirs: Optional[set[str]] = None   # lazily populated

    # ── Public API ────────────────────────────────────────────────────────────

    def on_file_access(self, file_path: str) -> None:
        """Record that the agent accessed *file_path*. Update visited stats."""
        path = Path(file_path).resolve()
        try:
            rel = path.relative_to(self.project_dir)
        except ValueError:
            # File is outside the project directory — ignore
            return

        # Record each ancestor directory up to max_depth levels deep
        parts = rel.parts[:-1]   # strip the filename itself
        now_iso = datetime.now(timezone.utc).isoformat()

        for depth in range(min(len(parts), self.max_depth)):
            subdir = str(Path(*parts[:depth + 1]))
            if subdir not in self._visited:
                fc = self._count_files(subdir)
                self._visited[subdir] = SubdirStats(
                    path=subdir,
                    file_count=fc,
                )
            self._visited[subdir].visit_count += 1
            self._visited[subdir].last_visited = now_iso

        logger.debug(
            f"[VECTOR][subdir_hints] on_file_access: {rel} "
            f"(visited {len(self._visited)} dirs total)"
        )

    def get_hints(self, *, max_hints: int = 3) -> list[str]:
        """
        Return actionable hint strings about unexplored subdirectories.

        Logic:
        1. Collect all subdirs in the project (lazily, up to max_depth).
        2. Find subdirs not yet in self._visited.
        3. Filter to those with >= 2 direct files (reduce noise).
        4. Sort by file_count descending (most files = most likely relevant).
        5. Return the top max_hints as human-readable strings.

        Example outputs:
        - "You haven't explored src/auth/ yet (12 files). It may be relevant."
        - "Consider checking tests/ (8 files) for existing patterns."
        """
        all_subdirs = self._get_all_subdirs()
        visited_set = set(self._visited.keys())
        unexplored = all_subdirs - visited_set

        # Attach file counts and filter low-signal dirs
        candidates: list[tuple[int, str]] = []
        for subdir in unexplored:
            fc = self._count_files(subdir)
            if fc >= 2:
                candidates.append((fc, subdir))

        # Sort by file count descending, then alphabetically for stability
        candidates.sort(key=lambda x: (-x[0], x[1]))
        top = candidates[:max_hints]

        hints: list[str] = []
        for fc, subdir in top:
            # Normalise path separator to forward slash for readability
            display = subdir.replace("\\", "/")
            if not display.endswith("/"):
                display += "/"
            hints.append(
                f"You haven't explored {display} yet ({fc} files). It may be relevant."
            )

        logger.debug(
            f"[VECTOR][subdir_hints] get_hints: {len(unexplored)} unexplored dirs, "
            f"returning {len(hints)} hints"
        )
        return hints

    def get_visited_summary(self) -> dict:
        """Return a summary dict of all visited directories."""
        return {
            subdir: {
                "visit_count":  stats.visit_count,
                "last_visited": stats.last_visited,
                "file_count":   stats.file_count,
            }
            for subdir, stats in sorted(self._visited.items())
        }

    def reset(self) -> None:
        """Reset tracker state for a new session (project_dir stays the same)."""
        self._visited.clear()
        self._all_subdirs = None
        logger.debug("[VECTOR][subdir_hints] reset")

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_all_subdirs(self) -> set[str]:
        """
        Scan project_dir up to max_depth levels.
        Returns a set of relative subdir path strings.
        Ignores dirs in _IGNORE_DIRS and *.egg-info folders.
        """
        if self._all_subdirs is not None:
            return self._all_subdirs

        result: set[str] = set()
        try:
            for item in self.project_dir.rglob("*"):
                if not item.is_dir():
                    continue
                try:
                    parts = item.relative_to(self.project_dir).parts
                except ValueError:
                    continue
                # Depth check
                if len(parts) > self.max_depth:
                    continue
                # Ignore check — any component matches an ignored name
                if any(
                    p in _IGNORE_DIRS or p.endswith(".egg-info") or p.startswith(".")
                    for p in parts
                ):
                    continue
                result.add(str(Path(*parts)))
        except Exception as exc:
            logger.warning(f"[VECTOR][subdir_hints] _get_all_subdirs error: {exc}")

        self._all_subdirs = result
        logger.debug(
            f"[VECTOR][subdir_hints] scanned project — "
            f"{len(result)} subdirs found (max_depth={self.max_depth})"
        )
        return result

    def _count_files(self, subdir: str) -> int:
        """Count direct (non-recursive) files in *subdir*."""
        try:
            d = self.project_dir / subdir
            return sum(1 for f in d.iterdir() if f.is_file())
        except Exception:
            return 0


# ── Per-project singleton ─────────────────────────────────────────────────────

_trackers: dict[str, SubdirectoryHintTracker] = {}


def get_hint_tracker(project_dir: str = ".") -> SubdirectoryHintTracker:
    """Return a per-project singleton SubdirectoryHintTracker."""
    key = str(Path(project_dir).resolve())
    if key not in _trackers:
        _trackers[key] = SubdirectoryHintTracker(project_dir)
        logger.debug(f"[VECTOR][subdir_hints] created tracker for {key!r}")
    return _trackers[key]


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    # Determine the vectorcode python directory (where this file lives, two levels up)
    vectorcode_python_dir = str(Path(__file__).parent.parent.parent)

    # 1. Create tracker
    tracker = SubdirectoryHintTracker(
        project_dir=vectorcode_python_dir,
        max_depth=3,
    )
    logger.info(f"[VECTOR][subdir_hints] tracker project_dir={tracker.project_dir}")

    # 2. Simulate 3 file accesses to engine/agent_loop.py
    fake_file = str(tracker.project_dir / "vectorcode" / "engine" / "agent_loop.py")
    for _ in range(3):
        tracker.on_file_access(fake_file)

    # 3. Verify "engine" (or the full relative path) is recorded in visited
    summary = tracker.get_visited_summary()
    logger.info(f"[VECTOR][subdir_hints] visited summary: {list(summary.keys())}")

    # "vectorcode/engine" or "vectorcode\\engine" should be in summary
    # (depending on OS path separator)
    engine_keys = [k for k in summary if "engine" in k]
    assert len(engine_keys) >= 1, (
        f"Expected 'engine' in visited summary, got: {list(summary.keys())}"
    )
    stats = summary[engine_keys[-1]]  # the deepest level — engine itself
    assert stats["visit_count"] == 3, (
        f"Expected visit_count=3, got {stats['visit_count']}"
    )
    logger.info("[VECTOR][subdir_hints] visited summary OK — 'engine' recorded with visit_count=3")

    # 4. get_hints() returns a list (may be empty if all dirs visited, which is fine)
    hints = tracker.get_hints()
    assert isinstance(hints, list), f"get_hints must return list, got {type(hints)}"
    logger.info(f"[VECTOR][subdir_hints] get_hints returned {len(hints)} hint(s):")
    for h in hints:
        logger.info(f"  {h}")

    # 5. Singleton via get_hint_tracker
    t1 = get_hint_tracker(vectorcode_python_dir)
    t2 = get_hint_tracker(vectorcode_python_dir)
    assert t1 is t2, "get_hint_tracker must return singleton per project_dir"
    logger.info("[VECTOR][subdir_hints] singleton OK")

    # 6. reset() clears state
    tracker.reset()
    assert tracker._visited == {}, "reset() should clear _visited"
    assert tracker._all_subdirs is None, "reset() should clear _all_subdirs cache"
    logger.info("[VECTOR][subdir_hints] reset() OK")

    print("utils/subdirectory_hints.py OK")
