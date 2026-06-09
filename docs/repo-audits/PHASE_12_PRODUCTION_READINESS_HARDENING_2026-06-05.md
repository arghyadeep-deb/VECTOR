# Phase 12 - Production Readiness Hardening

## Summary
VECTOR now separates local readiness from strict production readiness. Local development can still run in degraded mode, but production mode fails loudly when security, approval, encryption, or configured sidecar requirements are missing.

## Backend
- `run_dependency_doctor()` now accepts `production=True`.
- `VECTOR_ENV=production` automatically enables strict doctor requirements.
- Production readiness requires:
  - `VECTOR_API_KEY`
  - `VECTOR_JWT_SECRET`
  - `HUMANLAYER_API_KEY`
  - SQLCipher-capable memory driver (`sqlcipher3-binary` or `pysqlcipher3`)
  - configured optional sidecar paths when optional checks are included
- Added `GET /health/production-readiness`.

## Frontend
- Added `/health/production-readiness` to backend feature, health, and platform coverage.

## Behavior
- `/health/readiness` remains a core local readiness check.
- `/health/doctor` remains the full local doctor.
- `/health/production-readiness` returns `503` until production blockers are fixed.

## Verification
- `tests/backend/test_runtime_doctor.py`
- `tests/frontend/test_feature_registry.py`
- JS syntax checks
- `python run_vector.py smoke`
- `python run_vector.py doctor`
