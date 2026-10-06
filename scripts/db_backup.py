"""
VECTOR DB Backup — daily rolling backup of all SQLite databases.

Finds every *.db file under the project root, copies each with an
online-backup API (safe while VECTOR is running), and removes backups
older than RETENTION_DAYS.

Usage:
    python scripts/db_backup.py             # backup all DBs
    python scripts/db_backup.py --dry-run   # show what would be backed up
    python scripts/db_backup.py --list      # list existing backups
    python scripts/db_backup.py --prune     # prune old backups only

Scheduled automatically by the autonomous loop at 2 AM via APScheduler.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from loguru import logger

RETENTION_DAYS: int = 7
_BASE_DIR      = Path(CONFIG.get("base_dir", Path(__file__).parent.parent))
BACKUP_DIR     = _BASE_DIR / "data" / "backups" / "sqlite"

# Directories to never back up (node_modules, venv, external data).
# "backups" is CRITICAL: without it, rglob re-copies every prior backup each run —
# an exponential recursion bomb that reached 74GB on 2026-06-19 (fixed 2026-07-11).
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "backups"}


def _find_db_files() -> list[Path]:
    result: list[Path] = []
    _backup_root = BACKUP_DIR.resolve()
    for path in _BASE_DIR.rglob("*.db"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        # Belt-and-suspenders: never back up anything already under the backup dir.
        if _backup_root in path.resolve().parents:
            continue
        result.append(path)
    result.sort()
    return result


def _backup_path(db: Path, stamp: str) -> Path:
    # Preserve the real directory structure under BACKUP_DIR/stamp/ instead
    # of flattening it into a single "__"-joined filename: flattening let
    # two distinct source paths collide onto the same backup file whenever
    # either path segment itself contained "__" (e.g. "a__b/c.db" and
    # "a/b__c.db" both flattened to "a__b__c.db").
    relative = db.relative_to(_BASE_DIR)
    return BACKUP_DIR / stamp / relative


def _sqlite_backup(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dst.parent), prefix=f".{dst.name}.", suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    src_conn = None
    dst_conn = None
    try:
        src_conn = sqlite3.connect(str(src))
        dst_conn = sqlite3.connect(str(tmp))
        src_conn.backup(dst_conn)
        dst_conn.close()
        dst_conn = None
        src_conn.close()
        src_conn = None
        with tmp.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp, dst)
    except sqlite3.DatabaseError:
        # Not a valid SQLite file (e.g., corrupt or locked differently) — raw copy
        if dst_conn is not None:
            dst_conn.close()
            dst_conn = None
        if src_conn is not None:
            src_conn.close()
            src_conn = None
        tmp.unlink(missing_ok=True)
        _atomic_copy(src, dst)
    finally:
        if dst_conn is not None:
            dst_conn.close()
        if src_conn is not None:
            src_conn.close()
        tmp.unlink(missing_ok=True)


def _atomic_copy(src: Path, dst: Path) -> None:
    """Copy *src* without exposing a partial destination on interruption."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dst.parent), prefix=f".{dst.name}.", suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(src, tmp)
        with tmp.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def run_backup(dry_run: bool = False) -> dict:
    stamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    dbs    = _find_db_files()
    backed = []
    failed = []

    logger.info("[VECTOR][db_backup] starting backup of {} databases → {}", len(dbs), BACKUP_DIR / stamp)

    for db in dbs:
        dst = _backup_path(db, stamp)
        if dry_run:
            logger.info("[VECTOR][db_backup] DRY-RUN  {}", db.relative_to(_BASE_DIR))
            backed.append(str(db.relative_to(_BASE_DIR)))
            continue
        try:
            _sqlite_backup(db, dst)
            backed.append(str(db.relative_to(_BASE_DIR)))
            logger.debug("[VECTOR][db_backup] ✓ {}", db.relative_to(_BASE_DIR))
        except Exception as e:
            failed.append(str(db.relative_to(_BASE_DIR)))
            logger.error("[VECTOR][db_backup] ✕ {} — {}", db.relative_to(_BASE_DIR), e)

    result = {"stamp": stamp, "backed": backed, "failed": failed, "dry_run": dry_run}

    if not dry_run:
        prune_old_backups()

    if failed:
        logger.warning("[VECTOR][db_backup] {} backed up, {} failed: {}", len(backed), len(failed), failed)
    else:
        logger.info("[VECTOR][db_backup] {} databases backed up successfully", len(backed))

    return result


def prune_old_backups() -> int:
    if not BACKUP_DIR.exists():
        return 0
    cutoff  = datetime.now() - timedelta(days=RETENTION_DAYS)
    removed = 0
    for stamp_dir in BACKUP_DIR.iterdir():
        if not stamp_dir.is_dir():
            continue
        try:
            dt = datetime.strptime(stamp_dir.name, "%Y%m%d_%H%M%S")
        except ValueError:
            continue
        if dt < cutoff:
            shutil.rmtree(stamp_dir, ignore_errors=True)
            removed += 1
            logger.info("[VECTOR][db_backup] pruned old backup {}", stamp_dir.name)
    return removed


def list_backups() -> list[dict]:
    if not BACKUP_DIR.exists():
        return []
    entries = []
    for stamp_dir in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if not stamp_dir.is_dir():
            continue
        files = list(stamp_dir.glob("*.db"))
        total = sum(f.stat().st_size for f in files)
        entries.append({
            "stamp": stamp_dir.name,
            "files": len(files),
            "size_mb": round(total / 1_048_576, 2),
        })
    return entries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VECTOR SQLite backup tool")
    parser.add_argument("--dry-run", action="store_true", help="show what would be backed up")
    parser.add_argument("--list",    action="store_true", help="list existing backups")
    parser.add_argument("--prune",   action="store_true", help="prune old backups only")
    args = parser.parse_args()

    if args.list:
        backups = list_backups()
        if not backups:
            print("No backups found.")
        for b in backups:
            print(f"  {b['stamp']}  {b['files']} files  {b['size_mb']} MB")
        sys.exit(0)

    if args.prune:
        n = prune_old_backups()
        print(f"OK db_backup.py -- pruned {n} old backup(s)")
        sys.exit(0)

    result = run_backup(dry_run=args.dry_run)
    status = "DRY-RUN" if args.dry_run else ("DONE" if not result["failed"] else "PARTIAL")
    print(f"OK db_backup.py {status} -- {len(result['backed'])} backed up, {len(result['failed'])} failed")
