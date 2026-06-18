"""
VECTOR DB Backup — backs up all SQLite databases to a timestamped archive.

Usage:
    python scripts/backup_dbs.py                   # backup to ../VECTOR-backups/
    python scripts/backup_dbs.py --dest /path/to/  # custom destination
    python scripts/backup_dbs.py --verify           # verify backups after copy
    python scripts/backup_dbs.py --prune-days 30   # delete backups older than 30 days

Called by the autonomous loop's 2AM reflect tick (wired in core/loop/autonomous_loop.py)
and by the NSSM pre-stop hook.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from loguru import logger

REPO_ROOT = Path(__file__).parent.parent


def _find_db_files(root: Path) -> list[Path]:
    """Find all .db files that are likely SQLite (not encrypted blobs)."""
    dbs = []
    for db in sorted(root.rglob("*.db")):
        # Skip test fixtures, venv, node_modules, __pycache__
        parts = set(db.parts)
        if parts & {".venv", "venv", "node_modules", "__pycache__", ".git"}:
            continue
        if "test_fixtures" in str(db) or "tmp" in str(db).lower():
            continue
        dbs.append(db)
    return dbs


def _is_sqlite(path: Path) -> bool:
    """Quick magic-byte check — SQLite header starts with 'SQLite format 3'."""
    try:
        with path.open("rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def backup_db(src: Path, dest_dir: Path, verify: bool = False) -> bool:
    """
    Backup a single SQLite DB using the online backup API (safe under writes).
    Returns True on success.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    try:
        # Use sqlite3 online backup — safe while the DB is being written to
        src_conn = sqlite3.connect(str(src))
        dst_conn = sqlite3.connect(str(dest))
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()

        if verify:
            # Quick integrity check on the backup copy
            chk = sqlite3.connect(str(dest))
            result = chk.execute("PRAGMA integrity_check").fetchone()
            chk.close()
            if result[0] != "ok":
                logger.error("[VECTOR][backup] integrity_check FAILED for {}: {}", dest, result[0])
                return False

        return True
    except Exception as e:
        logger.error("[VECTOR][backup] failed to backup {}: {}", src, e)
        return False


def prune_old_backups(backup_root: Path, keep_days: int) -> int:
    """Delete backup snapshots older than keep_days. Returns count deleted."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    deleted = 0
    for snapshot_dir in sorted(backup_root.iterdir()):
        if not snapshot_dir.is_dir():
            continue
        # Directory names are ISO timestamps: 2026-06-18T02-00-00
        try:
            ts = datetime.fromisoformat(snapshot_dir.name.replace("T", " ").replace("-", ":", 2))
        except ValueError:
            continue
        if ts.replace(tzinfo=timezone.utc) < cutoff:
            shutil.rmtree(snapshot_dir, ignore_errors=True)
            deleted += 1
            logger.info("[VECTOR][backup] pruned old snapshot: {}", snapshot_dir.name)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="VECTOR DB backup utility")
    parser.add_argument("--dest", default=str(REPO_ROOT.parent / "VECTOR-backups"),
                        help="Root backup directory (default: ../VECTOR-backups/)")
    parser.add_argument("--verify", action="store_true",
                        help="Run PRAGMA integrity_check on each backup")
    parser.add_argument("--prune-days", type=int, default=0,
                        help="Delete snapshots older than N days (0 = no pruning)")
    args = parser.parse_args()

    backup_root = Path(args.dest)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    snapshot_dir = backup_root / ts

    logger.info("[VECTOR][backup] starting snapshot → {}", snapshot_dir)
    t0 = time.monotonic()

    dbs = [p for p in _find_db_files(REPO_ROOT) if _is_sqlite(p)]
    logger.info("[VECTOR][backup] found {} SQLite databases", len(dbs))

    ok = failed = 0
    for db in dbs:
        # Preserve relative path structure inside snapshot
        rel = db.relative_to(REPO_ROOT)
        dest_subdir = snapshot_dir / rel.parent
        if backup_db(db, dest_subdir, verify=args.verify):
            ok += 1
        else:
            failed += 1

    elapsed = time.monotonic() - t0
    logger.info(
        "[VECTOR][backup] done in {:.1f}s — {} backed up, {} failed",
        elapsed, ok, failed,
    )

    if args.prune_days > 0:
        pruned = prune_old_backups(backup_root, args.prune_days)
        logger.info("[VECTOR][backup] pruned {} old snapshots (>{} days)", pruned, args.prune_days)

    if failed:
        logger.warning("[VECTOR][backup] {} databases failed to back up", failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
