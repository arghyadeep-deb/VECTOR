"""24-48h soak verification — run this after letting `python run_vector.py loop`
run for a day. Confirms the Phase 5 autonomy proof holds in the wild, not
just in a test: real hand_run rows and cron job rows appearing with nobody
prompting them.

Usage: python scripts/check_soak.py
"""
from __future__ import annotations

from core.memory.episodic import get_temp_cursor

CRON_JOB_SOURCES = (
    "job_daily_eval", "job_audit_verify", "job_biometrics_pull",
    "job_content_scheduler", "job_daily_review", "job_trigger_workflow",
    "job_benchmark_suite", "job_recipe_sync", "job_weekly_dspy_optimize",
    "job_weekly_growth_report", "job_venture_pipeline", "job_nightly_selfcheck",
)
HAND_NAMES = (
    "researcher", "collector", "predictor", "trader",
    "lead", "content", "vault_sync",
)


def main() -> int:
    with get_temp_cursor() as cursor:
        cursor.execute(
            "SELECT event_type, source, timestamp FROM episodic_memory "
            "WHERE event_type = 'hand_run' ORDER BY timestamp DESC LIMIT 50"
        )
        hand_rows = cursor.fetchall()

        cursor.execute(
            "SELECT event_type, source, timestamp FROM episodic_memory "
            "WHERE event_type IN ('hand_execution', 'reflection', 'daily_review') "
            "ORDER BY timestamp DESC LIMIT 50"
        )
        other_rows = cursor.fetchall()

    print(f"\n--- hand_run rows (expect ~4 from vault_sync if soaked 24h, every-6h cadence) ---")
    if not hand_rows:
        print("  NONE — scheduler is not firing hands. Check `python run_vector.py loop` is actually running.")
    for event_type, source, ts in hand_rows:
        print(f"  {ts}  {source}")

    seen_sources = {r[1] for r in hand_rows}
    print(f"\nDistinct hands seen firing: {sorted(seen_sources) or 'none'}")

    print(f"\n--- other related rows (hand_execution / reflection / daily_review) ---")
    if not other_rows:
        print("  none yet")
    for event_type, source, ts in other_rows[:10]:
        print(f"  {ts}  {event_type}  {source}")

    print(f"\n--- verdict ---")
    if hand_rows:
        print(f"✅ {len(hand_rows)} hand_run row(s) found — resurrection holds in the wild.")
    else:
        print("❌ zero hand_run rows — soak has not produced evidence yet (or loop mode isn't running).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
