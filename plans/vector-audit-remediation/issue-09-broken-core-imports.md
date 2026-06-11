# Issue 09 — 25+ broken `core.*` bare imports

- **Severity:** CRITICAL · **Category:** Stability
- **Source (audit):** `core.*` bare imports across `vc_system/`, `vc_agents/`, `channels/`
- **Status:** ⬜ TODO

## Issue (as reported)
25+ modules import `core.*` in a way that crashes depending on `sys.path` —
works only when the repo root happens to be importable.

## Analysis (to complete during analysis pass)
- Root cause: _pending_ (bare `core.` imports in absorbed vectorcode subtree; relies on sys.path luck — see Issue 25)
- Affected files: `vectorcode/src/vc_system/`, `vc_agents/`, `channels/` (enumerate exact files)
- Fix approach: _pending_ (make imports robust / guarded, or fix packaging so `core` is always resolvable)
- Tests: _pending_ (compileall + import smoke of each affected module)
- Acceptance: _pending_
