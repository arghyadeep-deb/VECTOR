# Issue 09 — 25+ broken `core.*` bare imports

- **Severity:** CRITICAL · **Category:** Stability
- **Source (audit):** `core.*` bare imports across `vc_system/`, `vc_agents/`, `channels/`
- **Status:** ✅ RESOLVED

## Issue (as reported)
25+ modules import `core.*` in a way that crashes depending on `sys.path` —
works only when the repo root happens to be importable.

## Analysis (to complete during analysis pass)
- Root cause: absorbed VectorCode modules expected both the repo root and
  `vectorcode/src` to be importable.
- Fix: centralized path bootstrapping in `vectorcode/__init__.py` and
  `vectorcode/src/__init__.py`; removed ad-hoc top-level path edits from
  `command_registry.py` and `event_bus_hooks.py`.
- Tests: `test_vectorcode_core_imports_work_outside_repo_cwd` imports
  representative `vc_system`, `vc_agents`, event, registry, and `core.config`
  modules from outside the repo working directory.
- Acceptance: `python -m pytest -q tests/backend/test_audit_followups.py`
