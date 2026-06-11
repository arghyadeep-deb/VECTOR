# Issue 03 — eval()/exec() on untrusted code

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `tools/skills_guard.py`, `vc_tools/templates/loader.py:92` — sandbox bypass
- **Status:** ⬜ TODO

## Issue (as reported)
eval()/exec() run on untrusted code paths; the guard/sandbox can be bypassed.

## Analysis (to complete during analysis pass)
- Root cause: _pending_
- Affected files: `vectorcode/src/tools/skills_guard.py`, `vectorcode/src/vc_tools/templates/loader.py` (+ verify which dir is live — see Issue 22)
- Fix approach: _pending_ (remove eval/exec on untrusted input; AST-validate or replace with a safe interpreter; align with existing `core/security` patterns)
- Tests: _pending_
- Acceptance: _pending_
