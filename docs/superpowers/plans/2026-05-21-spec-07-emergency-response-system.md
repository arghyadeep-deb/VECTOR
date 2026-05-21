# SPEC-07 Emergency Response System Implementation Plan

> **REQUIRED SUB-SKILL:** executing-plans

**Goal:** Complete the VECTOR Emergency Response System — detect, classify, runbook, escalate, log, orchestrate, and wire into the main loop.

**Architecture:** Pipeline: detector (async queues per domain) → classifier (compound-aware severity) → runbook (structured step execution) → escalation (tiered Pushover) → log (hash-chain SQLite). Orchestrated by EmergencyResponseSystem.

**Tech Stack:** Python 3.13, asyncio, Pydantic V2, loguru, SQLite, Pushover API (httpx)

---

### Task 1: Complete `districts/emergency/detector.py`

**Files:**
- Modify: `districts/emergency/detector.py`

- [ ] Write complete detector.py with asyncio.Queue per domain, subscribe_signal, per-rule debounce windows, compound batching, context field, dedup_key format.

### Task 2: Complete `districts/emergency/classifier.py`

**Files:**
- Modify: `districts/emergency/classifier.py`

- [ ] Write complete classifier.py with SEVERITY_MODIFIERS, compound detection, user state, confidence, escalation_path, recurrence thresholds.

### Task 3: Complete `districts/emergency/runbook.py`

**Files:**
- Modify: `districts/emergency/runbook.py`

- [ ] Write complete runbook.py with RunbookAction/ActionResult dataclasses, step execution, timeout, rollback, safety levels, enhanced GPU/OOM runbooks.

### Task 4: Complete `districts/emergency/escalation.py`

**Files:**
- Modify: `districts/emergency/escalation.py`

- [ ] Write complete escalation.py with EscalationState, CRITICAL timing (0s→30s→120s), acceleration, pause/resume, no Twilio, Pushover priority=2.

### Task 5: Complete `districts/emergency/log.py`

**Files:**
- Modify: `districts/emergency/log.py`

- [ ] Write complete log.py with WAL mode pragma, get_by_domain, avg_response_time_seconds, avg_resolution_time_seconds, false_alarms in summary.

### Task 6: Create `districts/emergency/__init__.py`

**Files:**
- Modify: `districts/emergency/__init__.py`

- [ ] Export all public classes.

### Task 7: Create `districts/emergency/main.py` orchestrator

**Files:**
- Create: `districts/emergency/main.py`

- [ ] Write EmergencyResponseSystem class with start/stop/emit_signal/get_health/get_state.

### Task 8: Add EmergencyConfig to `core/config.py`

**Files:**
- Modify: `core/config.py`

- [ ] Add EmergencyConfig class and wire into CONFIG dict and VectorSettings.

### Task 9: Wire into `core/loop/autonomous_loop.py`

**Files:**
- Modify: `core/loop/autonomous_loop.py`

- [ ] Add emergency system startup in run_forever() as background task.

### Task 10: Wire signal sources

**Files:**
- Modify: `core/sensing/sound_classifier.py`
- Modify: `districts/ops/sre_monitor.py`
- Modify: `districts/health/emergency_detector.py`

- [ ] Add emit_signal calls to all three source files.

### Task 11: Create tests

**Files:**
- Create: `tests/emergency/__init__.py`
- Create: `tests/emergency/test_detector.py`
- Create: `tests/emergency/test_classifier.py`
- Create: `tests/emergency/test_log.py`
- Create: `tests/emergency/test_runbook.py`
- Create: `tests/emergency/test_escalation.py`
- Create: `tests/emergency/test_integration.py`

- [ ] Write all test files.

### Task 12: Smoke test and verify

- [ ] Run smoke tests, fix any issues.
