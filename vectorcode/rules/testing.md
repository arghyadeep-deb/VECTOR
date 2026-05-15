<!-- VECTOR-INGESTED ASSET
  Source: .claude/rules/testing.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:56+00:00
-->

---
paths:
  - "tests/**/*.py"
  - "**/*_test.py"
  - "**/test_*.py"
---

# Testing Rules

## Location
All tests in `tests/` mirroring the module structure:
```
core/memory.py  →  tests/test_core_memory.py
districts/d7/   →  tests/test_d7_memory_curator.py
```

## Every Test File
```python
# Real execution, no mocks of VECTOR internals
# Mocking external APIs (Supabase, cloud APIs) is acceptable
# Never mock: permission_gateway, session_hydration, HP system

def test_something():
    result = real_function()
    assert result is not None, "result must be non-null"
```

## Test Categories
- `test_core_*` — core systems (config, memory, gateway)
- `test_district_*` — per-district tests
- `test_integration_*` — cross-district flows
- `test_regression_*` — tests written for specific fixed bugs

## Shipped Gate
Before any district is marked done:
`pytest tests/test_district_<n>_*.py -v` must pass completely.

## No Mocking These
- `permission_gateway.py` — test the real gate
- `session_hydration_prompt()` — must test cold-start behavior
- `hp_system.py` — HP changes must be real, not stubbed
- SQLite `episodic_memory` — use a test DB, not mocks
