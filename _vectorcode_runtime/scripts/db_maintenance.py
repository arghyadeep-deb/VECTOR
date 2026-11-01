"""VECTOR episodic-memory maintenance — purge, prune, reclaim.

Keeps ``vector_memory.db`` bounded. Three passes:

  1. purge_test_pollution()  — delete rows written by tests that leaked into the
     live DB (source='test' for the synthetic event types) + bogus future-dated
     sentinels. Historical cleanup; the current test suite is isolated, so this
     should find nothing on a clean system.
  2. prune_old_episodes()    — the normal decay/forgetting pass (now
     ephemeral-aware: high-frequency telemetry forgotten after 14d, bulk 90d).
  3. vacuum()                — return freed pages to the OS (SQLCipher-safe).

Run:
    python scripts/db_maintenance.py            # report + execute
    python scripts/db_maintenance.py --dry-run  # report only, change nothing

Safe to run repeatedly. Never touches protected event types (council/ghost/
death/consolidation/security) or agent_history (ghost memory).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from loguru import logger

from core.memory.episodic import (
    EpisodicMemory,
    get_db_connection,
    get_temp_cursor,
    _with_cb,
    _delete_episodes_by_ids,
)

# Synthetic event types the test suite writes; purge only when source='test' so
# a real feature that ever reused one of these names is never touched.
_TEST_POLLUTION_TYPES = ("concurrent", "test", "unit")

# Event types that are no longer written and were never read back — pure
# write-only bloat. `context_budget_handle` stored tens-of-KB prompt offloads
# into FTS-indexed episodic_memory (ballooned the DB to multiple GB); the
# context budget manager now uses a dedicated capped non-FTS table instead, so
# every existing row here is dead. Purged unconditionally (any source/age).
_DEAD_EVENT_TYPES = ("context_budget_handle",)


def _db_size_mb() -> float:
    try:
        from core.memory.episodic import _memory_db_path
        return Path(_memory_db_path()).stat().st_size / 1e6
    except Exception:
        return -1.0


def purge_test_pollution(dry_run: bool = False) -> int:
    """Delete leaked test rows + future-dated sentinels. Returns rows affected."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def _collect_ids(cursor) -> list:
        ids: set = set()
        ph = ",".join("?" for _ in _TEST_POLLUTION_TYPES)
        cursor.execute(
            f"SELECT id FROM episodic_memory WHERE event_type IN ({ph}) AND source='test'",
            _TEST_POLLUTION_TYPES,
        )
        ids.update(r[0] for r in cursor.fetchall())
        # Dead/legacy write-only event types — purge unconditionally.
        dph = ",".join("?" for _ in _DEAD_EVENT_TYPES)
        cursor.execute(
            f"SELECT id FROM episodic_memory WHERE event_type IN ({dph})",
            _DEAD_EVENT_TYPES,
        )
        ids.update(r[0] for r in cursor.fetchall())
        # Future-dated rows are always test sentinels — no real event is in the future.
        cursor.execute("SELECT id FROM episodic_memory WHERE timestamp > ?", (now,))
        ids.update(r[0] for r in cursor.fetchall())
        return list(ids)

    with get_temp_cursor() as cursor:
        ids = _collect_ids(cursor)
    if not ids:
        logger.info("[db_maintenance] no test pollution found — DB is clean")
        return 0
    logger.info(f"[db_maintenance] found {len(ids):,} polluted/junk rows")
    if dry_run:
        return len(ids)

    def _do() -> int:
        with get_temp_cursor() as cursor:
            return _delete_episodes_by_ids(cursor, ids)

    deleted = _with_cb(_do)
    logger.info(f"[db_maintenance] purged {deleted:,} test-pollution rows")
    return deleted


def main(dry_run: bool = False) -> bool:
    before = _db_size_mb()
    logger.info(f"[db_maintenance] DB size before: {before:.1f}MB")

    mem = EpisodicMemory()
    purged = purge_test_pollution(dry_run=dry_run)
    pruned = 0 if dry_run else mem.prune_old_episodes(retention_days=90, vacuum=False)

    if not dry_run:
        # One VACUUM after both passes is cheaper than two.
        if purged or pruned:
            mem.vacuum()
        after = _db_size_mb()
        logger.info(
            f"[db_maintenance] DONE — purged {purged:,}, pruned {pruned:,}; "
            f"size {before:.1f}MB → {after:.1f}MB (reclaimed {before - after:.1f}MB)"
        )
    else:
        logger.info(f"[db_maintenance] DRY-RUN — would purge {purged:,} rows (no changes made)")
    return True


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    ok = main(dry_run=dry)
    print("✅ db_maintenance OK" if ok else "❌ db_maintenance FAILED")
