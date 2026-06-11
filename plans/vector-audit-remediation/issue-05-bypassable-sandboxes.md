# Issue 05 — Bypassable code sandboxes

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `vc_tools/repl.py`, `vc_tools/code_interpreter.py` — pattern blocklists trivially evaded
- **Status:** ⬜ TODO

## Issue (as reported)
REPL / code interpreter "sandboxes" rely on pattern blocklists that are trivially
evaded (getattr tricks, dunder access, import aliasing, etc.).

## Analysis (to complete during analysis pass)
- Root cause: blocklist sandboxing (not a real boundary)
- Affected files: `vectorcode/src/vc_tools/repl.py`, `.../code_interpreter.py` (confirm live dir vs Issue 22)
- Fix approach: _pending_ (gate behind PermissionGateway; real isolation via `core/sandbox` / subprocess+rlimits/container; or disable untrusted-code execution by default)
- Tests: _pending_
- Acceptance: _pending_
