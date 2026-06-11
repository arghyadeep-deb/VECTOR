# Issue 08 — Tokens in CLI args

- **Severity:** HIGH · **Category:** Security
- **Source (audit):** `slack_daemon.py:147` — token visible in process list
- **Status:** ⬜ TODO

## Issue (as reported)
A Slack token is passed as a command-line argument, making it visible to any
process via the process list (`ps`, `/proc`, Task Manager).

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/.../slack_daemon.py`
- Fix approach: _pending_ (pass via env var or stdin/file, never argv)
- Tests / Acceptance: _pending_
