# Issue 18 — Unbounded in-memory lists

- **Severity:** HIGH · **Category:** Concurrency
- **Source (audit):** `point_system._logs`, `loop_guard._recent_calls` — OOM after days/weeks
- **Status:** ✅ RESOLVED (production-hardening Task 07, commit 252231e8a) — re-verify

## Issue (as reported)
In-memory event lists grow without bound under 24/7 operation → eventual OOM.

## Resolution (already done)
- `core/city/point_system.py` `_logs` → `deque(maxlen=5000)`
- `core/loop/loop_guard.py` `_recent_calls` → `deque(maxlen=PHANTOM_THRESHOLD+2)`
- `core/memory/episodic.py` replay buffer → `deque(maxlen=10000)`
Covered by `tests/backend/test_memory_concurrency_safety.py`.

## Verify
- [ ] All three still bounded; phantom detection still works
