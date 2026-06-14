# Issue 02 — Unauthenticated memory_clear

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `mcp_server.py:1039` — deletes entire episodic memory with no auth
- **Status:** ✅ RESOLVED / RE-VERIFIED

## Issue (as reported)
memory_clear wipes all episodic memory with no confirmation/authorization.

## Resolution (already done)
`memory_clear(confirm)` now requires `confirm="CONFIRM_CLEAR_MEMORY"`; without it
returns an error and deletes nothing. Covered by
`tests/backend/test_mcp_memory_safety.py`.

## Verify
- [x] Confirm confirmation gate present at current line
- [x] Clear-without-confirm test still green via `python -m pytest -q tests/backend/test_mcp_memory_safety.py`
