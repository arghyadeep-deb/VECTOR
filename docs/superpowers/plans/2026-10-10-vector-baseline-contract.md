# Plan: VECTOR baseline contract

## Objective

Create one canonical inventory and one capability status vocabulary before
changing broad behavior.

## Files

### Modify

- `config/agent_manifest.yaml` — correct stale header/count claims only after
  loading the manifest.
- `core/city/declarative_manifest.py` — expose the loaded canonical counts in a
  structured report if the existing loader lacks them.
- `core/runtime/readiness_check.py` — add capability/inventory evidence without
  changing required dependency semantics.
- `core/runtime/doctor.py` — distinguish required failures from optional
  unavailable services.
- `scripts/audit_all_wiring.py` — fix known lazy-export/runtime-asset false
  negatives.
- `scripts/full_integration_audit.py` — use `MistralTTSClient.speak` and the
  actual MCP research registration.
- `docs/design/gap-register.md` — link the canonical matrix and proof artifacts.

### Create

- `docs/design/capability-closure-matrix.md`
- `tests/test_capability_closure_contract.py`
- `tests/test_manifest_inventory_contract.py`

## Steps

1. Add failing tests for 274 configured agents, 41 districts, zero empty
   districts, and the status vocabulary.
2. Run the tests and capture the current documentation/scanner mismatches.
3. Add the smallest inventory/reporting changes.
4. Regenerate the matrix from source evidence; do not hand-edit counts.
5. Run:

```powershell
python -m pytest -q tests/test_capability_closure_contract.py tests/test_manifest_inventory_contract.py
python scripts/audit_all_wiring.py
python scripts/full_integration_audit.py
python run_vector.py readiness-check
```

## Gate

The matrix is the source of truth for later phases. No capability work starts
until every current entry is classified or explicitly marked `FIX_QUEUE`.
