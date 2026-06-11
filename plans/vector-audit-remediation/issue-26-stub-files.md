# Issue 26 — Stub / not-implemented files

- **Severity:** mixed (core ones HIGH, peripheral LOW) · **Category:** Completeness
- **Source (audit):** stub-files table
- **Status:** ⬜ TODO (per-item triage below)

## Issue (as reported)
Several modules are scaffolds / no-ops that silently return empty or fixed
values instead of doing real work.

| Item | File | Reported state | Priority | Notes / status |
|------|------|----------------|----------|----------------|
| 26a | `core/loop/planner.py` | 83 lines, all scaffold | HIGH | core loop planner — verify if anything depends on it at runtime |
| 26b | `core/memory/semantic.py` | `search()` always returns `[]` | **HIGH** | core memory — semantic recall is dead; MCP `memory_semantic_search` + `_get_sem` rely on it. Highest-value fix. |
| 26c | `core/memory/reasoning_memory.py` | stores but never retrieves | **HIGH** | core memory — RULE 8 reasoning recall broken; verify retrieval path |
| 26d | `vc_skills/manager.py` | `pass` | LOW | skill manager no-op |
| 26e | `vc_skills/overlay.py` | `pass` | LOW | skill overlay no-op |
| 26f | `vc_agents/digest_evaluator.py` | hardcoded `return 1.0` | MED | quality scoring is fake → everything scores "perfect" |
| 26g | `channels/imessage_daemon.py` | always returns `False` | LOW | iMessage channel non-functional (macOS-only anyway) |
| 26h | `districts/finagent/` (17 methods) | 17 `NotImplementedError` | MED | financial agent stubs — confirm whether this is the absorbed `districts/investment/vector_finagent` and whether anything routes to it |

## Analysis (to complete during analysis pass)
- For each: determine (1) is it on a live code path? (2) is the stub intentional
  (Year-2 / optional capability) or a silent-failure bug?
- **Fix priority order:** 26b semantic.search → 26c reasoning retrieval →
  26a planner → 26f digest evaluator → finagent/skills/channels (peripheral or
  platform-gated; may stay stubbed with an explicit "not implemented" signal
  instead of fake values).
- Key principle: a stub that returns a *plausible fake* (empty list, `1.0`,
  `False`) is worse than one that clearly signals "unavailable" — prefer the
  latter where real impl is out of scope.
- Tests / Acceptance: _pending_ per item.
