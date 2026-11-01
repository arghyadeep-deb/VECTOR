"""Clean test-pollution rows from the production episodic memory DB.

Background: 7 test files (discovered 2026-08-06) were writing into the
production SQLCipher database instead of isolated temp DBs. Over time this
accumulated ~28,111 rows with source='test' in the episodic_memory table.
The bleeding was stopped (isolation fixtures added to all 7 files), but
the old rows remain.

Usage:
    python scripts/clean_test_pollution.py              # dry run (count only)
    python scripts/clean_test_pollution.py --apply      # actually delete

The --apply flag is required to actually delete. Without it, this script
only counts and reports — safe to run anytime.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Actually delete the rows (default: dry run)")
    args = parser.parse_args()

    from core.memory.episodic import get_db_connection

    conn = get_db_connection()
    if conn is None:
        print("[FATAL] Could not open database connection")
        sys.exit(1)

    # Count test rows
    cursor = conn.execute(
        "SELECT COUNT(*) FROM episodic_memory WHERE source = 'test'"
    )
    count = cursor.fetchone()[0]

    # Count total rows for context
    cursor = conn.execute("SELECT COUNT(*) FROM episodic_memory")
    total = cursor.fetchone()[0]

    print(f"Production DB: {total:,} total rows")
    print(f"Test pollution: {count:,} rows with source='test'")

    if count == 0:
        print("Nothing to clean — already clean!")
        return

    pct = (count / total * 100) if total > 0 else 0
    print(f"Test rows are {pct:.1f}% of total")

    if not args.apply:
        print(f"\nDry run — {count:,} rows would be deleted.")
        print("Pass --apply to actually delete them.")
        return

    print(f"\nDeleting {count:,} test rows...")
    conn.execute("DELETE FROM episodic_memory WHERE source = 'test'")
    conn.commit()

    # Verify
    cursor = conn.execute(
        "SELECT COUNT(*) FROM episodic_memory WHERE source = 'test'"
    )
    remaining = cursor.fetchone()[0]
    cursor = conn.execute("SELECT COUNT(*) FROM episodic_memory")
    new_total = cursor.fetchone()[0]

    print(f"Done. Deleted {count - remaining:,} rows.")
    print(f"DB now has {new_total:,} total rows, {remaining} test rows remaining.")


if __name__ == "__main__":
    main()
