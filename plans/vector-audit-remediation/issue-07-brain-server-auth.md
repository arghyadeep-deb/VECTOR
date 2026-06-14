# Issue 07 — Auth bypass on brain server

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `districts/` cloud API has no authentication
- **Status:** ✅ RESOLVED (2026-06-12)

## Issue (as reported)
A cloud-facing brain/API server exposes endpoints with no authentication.

## Status notes
- ✅ `cloud/comms_service/service.py` `/send` — bearer auth + prod fail-closed.
- ✅ `cloud/brain_server/main.py` — non-public endpoints require bearer auth and fail closed in production when `VECTOR_API_KEY` is missing.
- ✅ `cloud/brain_server/vector_config.py` no longer defaults CORS to `*`.

## Verification
- `tests/backend/test_comms_service_auth.py`
- `tests/backend/test_audit_followups.py`
- `tests/integration/test_phase_e1_fly_deploy.py`
