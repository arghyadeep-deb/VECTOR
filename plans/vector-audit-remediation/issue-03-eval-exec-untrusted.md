# Issue 03 — eval()/exec() on untrusted code

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `tools/skills_guard.py`, `vc_tools/templates/loader.py:92` — sandbox bypass
- **Status:** ✅ RESOLVED (2026-06-12)

## Issue (as reported)
eval()/exec() run on untrusted code paths; the guard/sandbox can be bypassed.

## Resolution
- `vectorcode/src/vc_tools/templates/loader.py` no longer uses Python `eval()`.
- Template expressions now run through a small AST allowlist evaluator.
- `skills_guard.py` contains detection strings for unsafe code, not a live eval/exec sink.
- Regression: `tests/backend/test_audit_followups.py`.
