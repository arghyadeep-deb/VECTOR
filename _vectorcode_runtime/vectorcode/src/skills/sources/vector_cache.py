"""VECTOR cache skill resolver.

Skills are treated as a local cache source. No network is performed by
default; callers may populate the cache directory out of band.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from vectorcode.src.skills.sources.github import GitHubResolver
from vectorcode.src.skills.sources.base import ResolvedSkill


class VectorCacheResolver(GitHubResolver):
    name = "vector-cache"

    def __init__(self, cache_root: Path | None = None) -> None:
        super().__init__(
            cache_root=cache_root or Path("~/.vector/skill-cache/vector-cache").expanduser(),
            repo_url="",
        )

    def sync(self) -> None:
        if self.cache_dir().exists():
            return
        self.cache_dir().mkdir(parents=True, exist_ok=True)

    def list_skills(self) -> List[ResolvedSkill]:
        return super().list_skills()


__all__ = ["VectorCacheResolver"]
