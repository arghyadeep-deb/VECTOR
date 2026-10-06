# Miscellaneous Root Directories Security/Correctness Audit Plan

Date: 2026-10-06

## Scope

- `tools/ci_gate.py`
- Every tracked Python file directly under `tools/vector_dev_orchestrator/`, excluding live `.state/` data
- `hands/__init__.py`, `hands/registry.py`, `hands/result.py`, `hands/runner.py`
- Every tracked Python file under `data/` and `phone_node/`
- The three tracked Python files under `cloud/`
- The tracked Python file under `models/`

`scripts/` is explicitly out of scope because concurrent audit tasks own it.

## Method

1. Inventory and read every scoped file completely, plus callers, tests, history, and relevant configuration.
2. Trace public entry points and persistence/subprocess boundaries, actively checking the recurring audit bug classes supplied by the owner.
3. Reproduce each suspected defect before editing and distinguish narrow correctness/security bugs from product-policy questions.
4. For each genuine narrow bug, add a focused regression test that fails on the old behavior, apply the smallest safe fix, and rerun the proof test.
5. Record unwired/design gaps without inventing integration policy, especially the orphaned `hands/` package.
6. Run focused existing tests, the new regression suite, compile checks, and diff hygiene checks.
7. Re-read `docs/OPEN_ISSUES.md`, calculate the current highest item number, and append one dated audit entry without staging or committing it.

## Constraints

- Do not modify `scripts/` or `tools/vector_dev_orchestrator/.state/`.
- Preserve unrelated working-tree changes.
- Do not change public signatures without checking all callers.
- Do not wire `hands/` into runtime without an owner decision.
- Leave all changes uncommitted for parent review.
