"""Disk cleanup plugin — free space by removing cache and temp files."""

from loguru import logger
import os
import shutil
from pathlib import Path


CACHE_DIRS = [
    Path.home() / ".cache" / "vector",
    Path.home() / ".vector" / "cache",
]


def get_size(path: Path) -> int:
    total = 0
    if path.is_file(): return path.stat().st_size
    for f in path.rglob("*"):
        if f.is_file(): total += f.stat().st_size
    return total


def clean(confirm: bool = True) -> dict:
    freed = 0
    for d in CACHE_DIRS:
        if d.exists():
            size = get_size(d)
            if confirm:
                ans = input(f"Delete {d} ({size // 1048576} MB)? [y/N]: ")
                if ans.lower() != "y": continue
            shutil.rmtree(d, ignore_errors=True)
            freed += size
            logger.info(f"Cleaned {d}: {size // 1024} KB freed")
    return {"freed_bytes": freed, "freed_mb": freed // 1048576}
