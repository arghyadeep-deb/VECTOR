# OD-12 and OD-46 Phone Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a disabled chaos monkey inert through every public execution entry point and make the network-reachable phone node reject mutating requests unless a usable API key is configured.

**Architecture:** Add entry-point guards directly to `ChaosMonkey`, using `None` for disabled single-result calls and an empty list for the disabled batch call. Keep the standalone Termux server self-contained with a small key-quality helper, central fail-closed POST authentication, and a startup warning while preserving the public read-only `/status` route.

**Tech Stack:** Python 3.12, stdlib HTTP server, loguru-compatible fallback logging, pytest

---

### Task 1: Add failing regression coverage

**Files:**
- Modify: `tests/resilience/test_chaos_monkey.py`
- Modify: `tests/backend/test_phone_node_hardening.py`

- [ ] Add a real injector counter proving all four chaos entry points execute nothing when disabled.
- [ ] Assert disabled single-experiment methods return `None`, the batch method returns `[]`, and the scheduled method returns `None`.
- [ ] Replace the old blank-key fail-open assertion with blank, short, and placeholder key rejection tests plus a usable-key success test.
- [ ] Add a server-start test proving an unusable key emits one loud warning while the read-only server can still start.
- [ ] Run both focused test files and confirm failures against the current implementation.

### Task 2: Implement the minimal gates

**Files:**
- Modify: `core/resilience/chaos_monkey.py`
- Modify: `phone_node/ambient_server.py`

- [ ] Add matching disabled guards and logs to the three ungated chaos entry points.
- [ ] Widen the two single-result annotations to `ChaosExperiment | None`; retain `list[ChaosExperiment]` and return `[]` for the disabled batch.
- [ ] Add a self-contained `_is_usable_key()` helper with an eight-character minimum and explicit placeholder deny-list.
- [ ] Make `_auth_ok()` reject every POST when the configured key is unusable.
- [ ] Emit a single startup warning from `_start_server()` when mutating endpoints are locked due to an unusable key.
- [ ] Run the focused regression files and confirm they pass.

### Task 3: Verify affected areas and scope

**Files:**
- Inspect: `core/resilience/chaos_monkey.py`
- Inspect: `phone_node/ambient_server.py`
- Inspect: `tests/resilience/test_chaos_monkey.py`
- Inspect: `tests/backend/test_phone_node_hardening.py`

- [ ] Run `python -m py_compile` on every changed Python file.
- [ ] Run the affected chaos/resilience/phone-node tests with a recorded `-k` expression and exact counts.
- [ ] Run `git diff --check`, inspect the final diff, and confirm OD-22 and `hands/runner.py` are untouched.
- [ ] Leave all changes uncommitted for owner review.
