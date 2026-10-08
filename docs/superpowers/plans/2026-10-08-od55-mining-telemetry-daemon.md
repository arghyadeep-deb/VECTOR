# OD-55 Mining Telemetry Daemon Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register `MiningTelemetryCollector` with the live gateway daemon so it periodically records mining telemetry without being able to crash the daemon.

**Architecture:** Add a focused `GatewayRunner` registration method that builds the canonical telemetry store, starts the collector's existing periodic `run()` coroutine, and retains the task in the gateway's existing `_background_tasks` lifecycle set. Invoke that method during successful gateway startup; keep initialization and store cleanup failure-safe.

**Tech Stack:** Python 3.12+, asyncio, pytest, existing VectorCode gateway/mining/telemetry modules.

---

### Task 1: Add a failing gateway registration regression

**Files:**
- Modify: `tests/test_vectorcode_engine_mining_audit.py`

- [ ] Add an async test that calls the real `GatewayRunner` mining registration path with controlled config/store/collector dependencies.
- [ ] Assert the daemon retains the created task and that the collector coroutine executes at least once.
- [ ] Run only the new test and confirm it fails because the gateway registration method does not exist.

### Task 2: Register the collector with the live gateway

**Files:**
- Modify: `vectorcode/src/gateway/run.py`

- [ ] Add a narrow, failure-contained registration method using canonical telemetry configuration, `TelemetryStore`, `SIDECAR_PATH`, and `MiningTelemetryCollector`.
- [ ] Add the collector task to `_background_tasks` and close its store when the task completes.
- [ ] Invoke registration after the gateway reaches its running state.
- [ ] Run the focused regression and confirm it passes.

### Task 3: Verify the scoped change

**Files:**
- Verify: `vectorcode/src/gateway/run.py`
- Verify: `tests/test_vectorcode_engine_mining_audit.py`

- [ ] Use a path-limited stash of the production change, leaving the new test present, to confirm the test fails pre-fix; restore the production change immediately. If git cannot update its index, report the exact permission failure.
- [ ] Run `python -m py_compile` for both touched Python files.
- [ ] Run the new regression, the complete existing collector test module, and the focused gateway daemon/scheduler test module.
- [ ] Inspect `git diff` and `git status`; leave all changes unstaged and do not commit.
