# Task 07 - Memory/concurrency safety

- **Depends on:** none
- **Who:** me
- **Effort:** 1 day
- **Design:** `AUDIT_REPORT_core.md`

## Objective

Reduce long-running runtime risk from unbounded in-memory collections and unsafe
concurrent SQLite access patterns.

## Files

- `core/memory/episodic.py` and related memory modules - serialize writes or use safer connections
- `core/city/point_system.py` - cap HP/event logs
- `core/loop/loop_guard.py` - cap recent-call history
- `tests/` - add concurrency and bounded-buffer tests

## Implementation

Use a clear serialization strategy for SQLite writes, such as a lock around
shared connections or per-thread connections with write coordination. Replace
unbounded lists with `deque(maxlen=...)` or equivalent bounded structures.

Avoid broad memory rewrites; target the specific audited risks first.

## Tests

- Concurrent memory writes do not raise `database is locked` in the targeted test.
- Point-system logs are capped.
- Loop-guard recent calls are capped.
- Existing memory tests still pass.

## Demo

```powershell
python -m pytest -q tests/backend/test_memory_concurrency_safety.py
```

## Acceptance

- [ ] Targeted concurrent write test passes repeatedly.
- [ ] Long-running point logs cannot grow without bound.
- [ ] Loop-guard call history cannot grow without bound.
- [ ] Smoke test still passes.
