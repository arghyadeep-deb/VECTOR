# OD-50 Gateway Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the standalone VectorCode gateway from exposing session-execution endpoints beyond loopback without strong Bearer-token authentication.

**Architecture:** Resolve `VECTOR_GATEWAY_KEY` through VECTOR's keyring-aware secret manager. Reuse the existing network exposure classifier and secret-quality validator for a fail-closed startup guard, and enforce authentication centrally in FastAPI middleware while leaving `/health` public. Keep wildcard CORS for compatibility but disable credentialed cross-origin requests.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, httpx/TestClient, pytest

---

### Task 1: Add failing regression coverage

**Files:**
- Create: `tests/test_gateway_server_auth_guard.py`

- [ ] Add a real-module test proving an exposed gateway without a key refuses startup before uvicorn serves.
- [ ] Add a loopback test proving no-key startup reaches the uvicorn serve boundary.
- [ ] Add TestClient requests proving missing/invalid Bearer tokens receive 401 and the configured token reaches `/status`.
- [ ] Add assertions proving `/health` remains public and CORS does not allow credentials with a wildcard origin.
- [ ] Run `python -m pytest tests/test_gateway_server_auth_guard.py -v` and confirm the security assertions fail against the current implementation.

### Task 2: Implement the minimal guard and authentication middleware

**Files:**
- Modify: `vectorcode/src/gateway/server.py`

- [ ] Resolve `VECTOR_GATEWAY_KEY` in `GatewayServer.__init__` with `core.security.secrets_manager.get_secret`.
- [ ] Import and reuse `is_network_accessible`; import and reuse `has_usable_secret(min_length=8)`.
- [ ] Before constructing/serving uvicorn, raise `RuntimeError` for an exposed host with a missing or unusable key.
- [ ] Log a warning when loopback starts without a configured key.
- [ ] Add FastAPI HTTP middleware that exempts `/health`, otherwise checks `Authorization: Bearer <key>` with `hmac.compare_digest` whenever a key is configured.
- [ ] Change wildcard CORS to `allow_credentials=False`.
- [ ] Run the focused regression file and confirm it passes.

### Task 3: Verify scope and regressions

**Files:**
- Inspect: `vectorcode/src/gateway/server.py`
- Inspect: `tests/test_gateway_server_auth_guard.py`

- [ ] Run `python -m pytest tests/ -k "gateway" -v` and record exact counts.
- [ ] Run the legacy gateway tests from the repository root and record exact counts or collection limitations.
- [ ] Run `git diff --check`, inspect `git diff`, and confirm no unrelated files were modified.
- [ ] Leave every change uncommitted for owner review.
