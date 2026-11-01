"""24-48h soak verification — run this after letting `python run_vector.py loop`
run for a day. Confirms the Phase 5 autonomy proof holds in the wild, not
just in a test: real hand_run rows AND real cron-job firings appearing with
nobody prompting them.

IMPORTANT: the real vector_memory.db already has hand_run rows from this
session's own Phase 1 development/testing (manual verification calls made
*before* Task 0.5c's test-DB isolation existed) — researcher/trader rows
from 2026-06-20 ~18:15-20:20 UTC are dev artifacts, not soak evidence. This
script defaults --since to right now, so re-running it without --since
always answers "what's happened since I last checked," not "ever."

Cron verification ground truth: most of the ~12 pre-existing cron jobs
(subconscious_loop, biometrics, daily_review, dspy, etc.) write nowhere
observable in episodic_memory on a HEALTHY run — several only write a row
on FAILURE (e.g. job_nightly_selfcheck's "selfcheck_failure"). Checking for
job-specific event_types would show "none yet" whether cron is dead or
just quiet-on-success. Instead this queries event_type="scheduler_job_run",
written by an APScheduler EVENT_JOB_EXECUTED/EVENT_JOB_ERROR listener
(core/loop/autonomous_loop.py::_record_job_run) — ground truth for "did the
scheduler actually fire this job," independent of what the job itself logs.

Usage:
    python scripts/check_soak.py                  # mark baseline (run this NOW, when starting the soak)
    python scripts/check_soak.py --since "2026-06-21T00:00:00+00:00"   # check what's fired since a specific time
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

# Windows console defaults to cp1252, which crashes on the ✅/❌/⚠️ verdict
# glyphs. Force UTF-8 so the check prints cleanly when run directly.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.memory.episodic import get_temp_cursor

EXPECTED_CRON_JOB_IDS = (
    "daily-eval-harness", "daily-audit-verify", "daily-biometrics-pull",
    "content-scheduler", "daily-review-journal", "daily-workflow-trigger",
    "weekly-benchmark-suite", "weekly-recipe-sync", "weekly-dspy-optimize",
    "weekly-growth-report", "weekly-venture-pipeline", "nightly-selfcheck",
    "subconscious-loop",
)
EXPECTED_HAND_JOB_IDS = (
    "hand-researcher", "hand-collector", "hand-predictor", "hand-trader",
    "hand-lead", "hand-content", "hand-vault_sync",
)


def verdict_exit_code(*, hands_ok: bool, cron_ok: bool) -> int:
    """Return failure unless both halves of the soak proof have evidence."""
    return 0 if hands_ok and cron_ok else 1


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
            "SELECT event_type, source, timestamp, content FROM episodic_memory "
            "WHERE event_type = 'hand_run' AND timestamp > ? ORDER BY timestamp DESC LIMIT 50",
            (since,),
        )
        hand_rows = cursor.fetchall()

        cursor.execute(
            "SELECT source, timestamp, content FROM episodic_memory "
            "WHERE event_type = 'scheduler_job_run' AND timestamp > ? ORDER BY timestamp DESC LIMIT 200",
            (since,),
        )
        job_run_rows = cursor.fetchall()

    if not args.since:
        print(f"\nBaseline marked at {since} — pass this back as --since tomorrow:")
        print(f'  python scripts/check_soak.py --since "{since}"')
        print(
            "\nNOTE: if this is the first time _record_job_run is live, restart "
            "`python run_vector.py loop` now so cron firings are captured from this "
            "baseline forward — anything before the listener existed is unrecorded."
        )
        return 0

    print(f"\n--- hand_run rows since {since} (expect ~4 from vault_sync if soaked 24h, every-6h cadence) ---")
    if not hand_rows:
        print("  NONE — scheduler is not firing hands. Check `python run_vector.py loop` is actually running.")
    for event_type, source, ts, content in hand_rows:
        print(f"  {ts}  {source}")
    seen_hands = {r[1] for r in hand_rows}

    print(f"\n--- scheduler_job_run rows since {since} (ground truth: did the scheduler fire each job?) ---")
    if not job_run_rows:
        print("  NONE — either the loop isn't running, or it was started before the "
              "job-run listener existed (restart it).")
    for source, ts, content in job_run_rows[:30]:
        print(f"  {ts}  {source}  {content}")
    seen_job_ids = {r[0] for r in job_run_rows}

    print(f"\n--- cron job coverage ---")
    fired_cron = [j for j in EXPECTED_CRON_JOB_IDS if j in seen_job_ids]
    missing_cron = [j for j in EXPECTED_CRON_JOB_IDS if j not in seen_job_ids]
    print(f"Fired:   {fired_cron or 'none'}")
    print(f"Missing: {missing_cron or 'none'}  (expected — most won't be due within 24-48h; "
          f"only flag this if a job's own cadence should have fired by now)")

    print(f"\n--- hand coverage (via scheduler_job_run, ground truth independent of hand_run rows) ---")
    fired_hands = [h for h in EXPECTED_HAND_JOB_IDS if h in seen_job_ids]
    missing_hands = [h for h in EXPECTED_HAND_JOB_IDS if h not in seen_job_ids]
    print(f"Fired:   {fired_hands or 'none'}")
    print(f"Missing: {missing_hands or 'none'}")

    print(f"\n--- verdict ---")
    hands_ok = bool(hand_rows) and bool(fired_hands)
    cron_ok = bool(fired_cron)
    if hands_ok and cron_ok:
        print(f"✅ resurrection holds in the wild: {len(hand_rows)} hand_run row(s), "
              f"{len(fired_cron)}/{len(EXPECTED_CRON_JOB_IDS)} cron job(s) fired, "
              f"{len(fired_hands)}/{len(EXPECTED_HAND_JOB_IDS)} hand job(s) fired.")
    elif hands_ok and not cron_ok:
        print("⚠️  hands are firing, but ZERO cron jobs have fired yet — either none were due "
              "in this window, or cron registration regressed. Check the window vs. each job's cadence.")
    elif cron_ok and not hands_ok:
        print("⚠️  cron jobs are firing, but ZERO hands have fired yet — check hand registration.")
    else:
        print("❌ neither hands nor cron jobs have fired — scheduler is not running "
              "(or the loop process isn't up).")

    return verdict_exit_code(hands_ok=hands_ok, cron_ok=cron_ok)


if __name__ == "__main__":
    raise SystemExit(main())
