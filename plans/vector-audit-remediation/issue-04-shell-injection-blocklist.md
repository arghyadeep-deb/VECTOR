# Issue 04 — Bypassable shell-injection sanitization

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `templates/loader.py:116` — blocklist misses `$()`, `>`, newlines
- **Status:** ⬜ TODO

## Issue (as reported)
Shell sanitization uses a blocklist that misses command substitution `$()`,
redirection `>`, and newline injection.

## Analysis (to complete during analysis pass)
- Root cause: blocklist-based filtering (inherently bypassable)
- Affected files: `vectorcode/src/.../templates/loader.py` (confirm live dir vs Issue 22)
- Fix approach: _pending_ (prefer no shell / `shlex` + arg vector + allowlist; reuse `core/security` shell guard if present)
- Tests: _pending_ (assert `$()`, backticks, `>`, `;`, newline payloads are rejected/neutralized)
- Acceptance: _pending_
