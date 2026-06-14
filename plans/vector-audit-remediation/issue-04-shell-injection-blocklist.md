# Issue 04 — Bypassable shell-injection sanitization

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `templates/loader.py:116` — blocklist misses `$()`, `>`, newlines
- **Status:** ✅ RESOLVED (2026-06-12)

## Issue (as reported)
Shell sanitization uses a blocklist that misses command substitution `$()`,
redirection `>`, and newline injection.

## Resolution
- `vectorcode/src/vc_tools/templates/loader.py` rejects shell metacharacters in substituted values, including `$()`, backticks, `>`, `;`, pipes, and newlines.
- Template commands still use `shell=False`.
- Direct shell interpreters such as `sh`, `bash`, `cmd`, PowerShell, and `pwsh` are rejected for template commands.
- Regression: `tests/backend/test_audit_followups.py`.
