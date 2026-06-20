"""24-48h soak verification — run this after letting `python run_vector.py loop`
run for a day. Confirms the Phase 5 autonomy proof holds in the wild, not
just in a test: real hand_run rows and cron job rows appearing with nobody
prompting them.

IMPORTANT: the real vector_memory.db already has hand_run rows from this
session's own Phase 1 development/testing (manual verification calls made
*before* Task 0.5c's test-DB isolation existed) — researcher/trader rows
from 2026-06-20 ~18:15-20:20 UTC are dev artifacts, not soak evidence. This
script defaults --since to right now, so re-running it without --since
always answers "what's happened since I last checked," not "ever."

Usage:
    python scripts/check_soak.py                  # mark baseline (run this NOW, when starting the soak)
    python scripts/check_soak.py --since "2026-06-21T00:00:00+00:00"   # check what's fired since a specific time
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from core.memory.episodic import get_temp_cursor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since", default=None,
        help="ISO timestamp — only show rows after this. Defaults to now (use this on day 1 to mark "
             "the soak's start; pass that exact printed timestamp back in on day 2).",
    )
    args = parser.parse_args()
    since = args.since or datetime.now(timezone.utc).isoformat()

    with get_temp_cursor() as cursor:
        cursor.execute(
            "SELECT event_type, source, timestamp FROM episodic_memory "
            "WHERE event_type = 'hand_run' AND timestamp > ? ORDER BY timestamp DESC LIMIT 50",
            (since,),
        )
        hand_rows = cursor.fetchall()

        cursor.execute(
            "SELECT event_type, source, timestamp FROM episodic_memory "
            "WHERE event_type IN ('hand_execution', 'reflection', 'daily_review') "
            "AND timestamp > ? ORDER BY timestamp DESC LIMIT 50",
            (since,),
        )
        other_rows = cursor.fetchall()

    if not args.since:
        print(f"\nBaseline marked at {since} — pass this back as --since tomorrow:")
        print(f'  python scripts/check_soak.py --since "{since}"')
        return 0

    print(f"\n--- hand_run rows since {since} (expect ~4 from vault_sync if soaked 24h, every-6h cadence) ---")
    if not hand_rows:
        print("  NONE — scheduler is not firing hands. Check `python run_vector.py loop` is actually running.")
    for event_type, source, ts in hand_rows:
        print(f"  {ts}  {source}")

    seen_sources = {r[1] for r in hand_rows}
    print(f"\nDistinct hands seen firing: {sorted(seen_sources) or 'none'}")

    print(f"\n--- other related rows since {since} (hand_execution / reflection / daily_review) ---")
    if not other_rows:
        print("  none yet")
    for event_type, source, ts in other_rows[:10]:
        print(f"  {ts}  {event_type}  {source}")

    print(f"\n--- verdict ---")
    if hand_rows:
        print(f"✅ {len(hand_rows)} hand_run row(s) found since baseline — resurrection holds in the wild.")
    else:
        print("❌ zero hand_run rows since baseline — soak has not produced evidence yet (or loop mode isn't running).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
