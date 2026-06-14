# Issue 26 — Stub / not-implemented files

- **Severity:** mixed (core ones HIGH, peripheral LOW) · **Category:** Completeness
- **Source (audit):** stub-files table
- **Status:** ✅ RESOLVED / RE-VERIFIED

## Issue (as reported)
Several modules are scaffolds / no-ops that silently return empty or fixed
values instead of doing real work.

| Item | File | Reported state | Priority | Notes / status |
|------|------|----------------|----------|----------------|
| 26a | `core/loop/planner.py` | 83 lines, all scaffold | HIGH | triaged: not a pure stub; delegates to `GoalSystem.generate_immediate_actions()` and energy filters |
| 26b | `core/memory/semantic.py` | `search()` always returns `[]` | **HIGH** | ✅ added real persisted keyword `search()` over `semantic_memory` |
| 26c | `core/memory/reasoning_memory.py` | stores but never retrieves | **HIGH** | ✅ added structured `search_chains()` / `retrieve_similar()` and fixed `chain_id`/`timestamp` schema mismatch |
| 26d | `vc_skills/manager.py` | `pass` | LOW | ✅ real manager re-export; fallback now raises explicit unavailable error |
| 26e | `vc_skills/overlay.py` | `pass` | LOW | ✅ real overlay/write re-export; fallback now raises explicit unavailable error |
| 26f | `vc_agents/digest_evaluator.py` | hardcoded `return 1.0` | MED | ✅ deterministic 0-10 evaluator with actionable feedback |
| 26g | `channels/imessage_daemon.py` | always returns `False` | LOW | ✅ real daemon re-export; fallback actions raise explicit unavailable error |
| 26h | `districts/investment/` finagent surfaces | 17 `NotImplementedError` | MED | ✅ replaced runtime stubs with explicit implementations/errors; `rg "raise NotImplementedError|NotImplementedError\(" districts\investment -S` is clean |

## Analysis (to complete during analysis pass)
- Tests / Acceptance: `python -m pytest -q tests/backend/test_audit_followups.py`
  covers semantic search, reasoning recall, digest evaluator scoring, and the
  explicit shim behavior/compatibility touched in this pass.
- Re-verification: `rg "raise NotImplementedError|NotImplementedError\(" districts\investment -S`
  returns no matches.
