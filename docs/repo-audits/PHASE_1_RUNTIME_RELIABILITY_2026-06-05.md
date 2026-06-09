# VECTOR Phase 1 Runtime Reliability - 2026-06-05

## Scope

Phase 1 builds the local reliability foundation before deeper JARVIS-style autonomy:

- offline dependency doctor
- readiness endpoint
- doctor endpoint
- CLI doctor mode
- smoke verification

Cloud deployment, phone nodes, Home Assistant/smart features, and sidecar runtime launch validation remain outside this phase.

## Implemented

- Added `core.runtime.doctor.run_dependency_doctor()`.
- Added structured check/result models:
  - `DependencyCheck`
  - `DoctorReport`
- Added offline-safe checks for:
  - Python version
  - required Python modules
  - optional Python modules
  - writable data root
  - writable test temp directory
  - launcher and frontend files
  - API router directory
  - districts directory
  - required mounted API routes
  - key/security environment variables
  - optional sidecar path configuration
- Added API endpoints:
  - `/health/readiness`
  - `/health/doctor`
- Added launcher mode:
  - `python run_vector.py doctor`
- Ensured `doctor` mode does not start sidecars or background services.

## Verification

Passed:

- `python -m pytest -q tests/backend/test_runtime_doctor.py`
- `python -m pytest -q tests/backend/test_runtime_doctor.py tests/backend/test_read_only_status_endpoints.py`
- `python run_vector.py smoke`
- `python run_vector.py doctor`

Doctor result in this environment:

- `required_failed`: `0`
- `status`: `degraded`
- Degraded only because optional items are not configured/installed:
  - SQLCipher Python binding
  - `VECTOR_API_KEY`
  - `VECTOR_JWT_SECRET`
  - `HUMANLAYER_API_KEY`
  - ComfyUI path
  - LibreChat path
  - UI-TARS path

## Phase 1 Reality

The local core is readiness-checkable now. This is not a full production soak, but VECTOR now has a fast command and API endpoint that can say whether the local runtime foundation is fit to start.

## Next Phase

Phase 2 should build the unified world model:

- one runtime context snapshot for voice, screen, camera, memory, tasks, agents, health, system, and open panels
- one API endpoint for that snapshot
- agents and frontend panels should read from the same live state object
