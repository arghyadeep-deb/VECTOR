# Issue 25 — sys.path.insert hacks

- **Severity:** MEDIUM · **Category:** Architecture
- **Source (audit):** 3+ instances — breaks virtualenv isolation
- **Status:** ✅ RESOLVED

## Resolution (2026-06-14)
Count dropped 235 → 95 via `vectorcode/src/bootstrap.py:ensure_paths()` and a
sweep of districts/core to the side-effect import. Remaining 95 categorized by
direct `sys.path.insert(` call-site inspection — **none is a repo-root hack
left to fix**:
- **Genuine repo-root inserts → converted:** `core/brain/goal_system.py`,
  `districts/communications/person_model.py` now use `ensure_paths()`.
- **Legitimate external/absorbed-lib path inserts** (NOT repo root, ensure_paths
  can't cover): `ollama_safe.py` (AirLLM), `obsidian_sync.py` (LightRAG),
  `social_sim_agent.py` (MiroFish), `backtest_agent.py` (Vibe),
  `vectorintel_agent.py` (SDK), plus the whole `districts/investment/
  vector_finagent|vector_backtest` and `shadowbroker_server` absorbed subprojects
  (~40) that bootstrap their own internal package roots.
- **False positives** (string literals, not executed): `python_reviewer.py`,
  `security_reviewer.py`, `test_writer.py`, `reality_checker.py` — these *generate
  or detect* the `sys.path.insert` pattern as part of code review.

## Issue (as reported)
`sys.path.insert(0, ...)` hacks (3+ instances) break virtualenv isolation and
cause the import fragility behind Issue 09.

## Analysis (to complete during analysis pass)
- Fixed obvious top-level import hacks in `vectorcode/src/command_registry.py`
  and `vectorcode/src/event_bus_hooks.py` by centralizing path setup in
  `vectorcode` package bootstrap.
- Remaining scope: repo still contains script/runtime path edits that need
  per-callsite review. Some may be acceptable CLI entrypoint bootstraps; others
  should become package-relative imports or console entrypoints.
- Tests / Acceptance so far:
  `test_vectorcode_core_imports_work_outside_repo_cwd` in
  `tests/backend/test_audit_followups.py`.
