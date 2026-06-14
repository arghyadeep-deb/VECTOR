# Issue 18 — Unbounded in-memory lists

- **Severity:** HIGH · **Category:** Concurrency
- **Source (audit):** `point_system._logs`, `loop_guard._recent_calls` — OOM after days/weeks
- **Status:** ✅ RESOLVED / RE-VERIFIED

## Issue (as reported)
In-memory event lists grow without bound under 24/7 operation → eventual OOM.

## Resolution (already done)
- `core/city/point_system.py` `_logs` → `deque(maxlen=5000)`
- `core/loop/loop_guard.py` `_recent_calls` → `deque(maxlen=PHANTOM_THRESHOLD+2)`
- `core/memory/episodic.py` replay buffer → `deque(maxlen=10000)`
- District runtime histories now trim in place:
  `CallScreener._call_history`, `VoiceResponder._response_history`,
  `Uploader._upload_history`, `Uploader._scheduled_uploads`,
  `MarketScanner.scan_history`, and per-competitor
  `CompetitorSpy.movement_history`.
Covered by `tests/backend/test_memory_concurrency_safety.py`.

## Verify
- [x] All core buffers still bounded; phantom detection still works
- [x] District runtime histories are bounded by `tests/backend/test_audit_followups.py`
