# Issue 08 — Tokens in CLI args

- **Severity:** HIGH · **Category:** Security
- **Source (audit):** `slack_daemon.py:147` — token visible in process list
- **Status:** ✅ RESOLVED (2026-06-12)

## Issue (as reported)
A Slack token is passed as a command-line argument, making it visible to any
process via the process list (`ps`, `/proc`, Task Manager).

## Resolution
- `vectorcode/src/comms/slack_daemon.py` and `vectorcode/src/channels/slack_daemon.py` no longer pass Slack tokens in subprocess argv.
- Tokens are passed through `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in the child environment.
- Regression: `tests/backend/test_audit_followups.py`.
