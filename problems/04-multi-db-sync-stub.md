# Problem 04 - 4-DB Sync Is Still A Stub

## Symptom

`core/memory/multi_db_manager.py` is an auto-generated stub.

## Why It Matters

The architecture promises SQLite, Supabase, Turso, and Cloudflare D1 sync every
48 hours. Right now, the real memory backbone is local SQLite plus partial cloud
heartbeat plumbing.

## Implemented Solution

Not implemented yet. This is intentionally tracked because it is a major
truth-gap between docs and code.

## Remaining Work

- Define sync contract and conflict rules.
- Implement local SQLite export/import first.
- Add one cloud target at a time.
- Add tests for last-write-wins and offline recovery.

