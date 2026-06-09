# VECTOR Phase 2 Unified World Model - 2026-06-05

## Scope

Phase 2 creates a single local world snapshot so the backend, HUD, and future agents can reason from one shared view of VECTOR's current state.

Excluded as before:

- cloud deployment
- phone nodes
- Home Assistant/smart-home features
- sidecar runtime certification

## Implemented

- Added `core.runtime.world_model.build_world_snapshot()`.
- Added structured `WorldSnapshot` sections:
  - `runtime`
  - `readiness`
  - `agents`
  - `memory`
  - `safety`
  - `sensing`
  - `voice`
  - `tasks`
  - `frontend`
- Added main API route:
  - `/world/snapshot`
- The endpoint accepts optional frontend panel context:
  - `/world/snapshot?panels=features,pccontrol`
- Mounted the world router in `core.api.app`.
- Wired the HUD backend adapter to poll `/world/snapshot`.
- Stored the snapshot in `VECTOR_DATA.WORLD`.
- Used the world snapshot to refresh:
  - uptime
  - visible agent sample
  - memory feed
  - approval queue
  - sensing readouts
  - top-right world status glyph
- Added `/world/snapshot` to frontend feature registry/core readouts.

## Verification

Passed:

- `python -m pytest -q tests/backend/test_world_snapshot.py tests/backend/test_runtime_doctor.py`
- `python -m pytest -q tests/frontend/test_feature_registry.py`
- `node --check frontend/js/backend.js`
- `node --check frontend/js/widgets.js`
- Playwright HUD smoke:
  - loaded `frontend/VECTOR.html`
  - opened `corepanel` and `features`
  - confirmed `/world/snapshot` exists in `VectorFeatureRegistry`
- `python run_vector.py smoke`
- `python run_vector.py doctor`

## Reality

VECTOR now has a real shared state layer. This is the start of the JARVIS-style "awareness" path, but it is still a snapshot, not a full continuous perception model.

## Next Phase

Phase 3 should implement the autonomous execution loop:

- plan
- classify risk
- request approval when needed
- execute
- verify result
- recover or report failure

The world model should become the context input for that execution loop.
