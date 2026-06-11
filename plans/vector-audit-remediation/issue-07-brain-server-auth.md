# Issue 07 — Auth bypass on brain server

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `districts/` cloud API has no authentication
- **Status:** 🟨 PARTIAL / 🔍 needs-verify

## Issue (as reported)
A cloud-facing brain/API server exposes endpoints with no authentication.

## Status notes
- ✅ `cloud/comms_service/service.py` `/send` — bearer auth + prod fail-closed
  added in production-hardening Task 04. Re-verify.
- 🔍 `cloud/brain_server/main.py` — the audit's "brain server" likely refers
  here; verify whether its endpoints are authenticated. Currently NOT confirmed.

## Analysis (to complete during analysis pass)
- Affected files: `cloud/brain_server/main.py` (+ any other district cloud API)
- Fix approach: _pending_ (apply the same bearer/fail-closed pattern as comms; reuse `core/api/auth.py` style)
- Tests / Acceptance: _pending_
