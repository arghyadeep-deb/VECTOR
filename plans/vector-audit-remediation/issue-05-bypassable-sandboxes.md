# Issue 05 — Bypassable code sandboxes

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `vc_tools/repl.py`, `vc_tools/code_interpreter.py` — pattern blocklists trivially evaded
- **Status:** ✅ RESOLVED (2026-06-12)

## Issue (as reported)
REPL / code interpreter "sandboxes" rely on pattern blocklists that are trivially
evaded (getattr tricks, dunder access, import aliasing, etc.).

## Resolution
- `vectorcode/src/vc_tools/repl.py` and `vectorcode/src/vc_tools/code_interpreter.py` now refuse execution by default.
- Execution requires explicit `VECTOR_ENABLE_UNTRUSTED_CODE=1`, intended only for isolated lab environments.
- This removes the bypassable blocklist sandbox from normal runtime.
- Regression: `tests/backend/test_audit_followups.py`.
