# Phase 8 - Background Mission Jobs

Date: 2026-06-05

## What Changed

- Added `MissionJob` and `MissionJobStore`.
- Missions now include `job_id` and `progress`.
- Mission execution saves progress after each step.
- Added `/missions/run-async` for queued background execution.
- Added `/missions/jobs` and `/missions/jobs/{job_id}` for polling.
- Mission Control now uses `/missions/run-async` for real runs and polls job status until terminal.

## Safety Contract

- Background jobs do not bypass mission runner, executor, or permission gateway.
- `/missions/run` remains as synchronous compatibility behavior.
- `/missions/run-async` returns immediately with a job id and mission snapshot.
- Mission progress/status are persisted as the run advances.

## Verification

- `python -m pytest -q tests/backend/test_missions.py tests/backend/test_autonomous_executor.py tests/frontend/test_feature_registry.py`
- `node --check frontend/js/widgets.js`
- `node --check frontend/js/demo.js`
- `node --check frontend/js/terminal.js`
- `python run_vector.py smoke`
- `python run_vector.py doctor`

## Current Reality

VECTOR now has request-independent mission execution with status polling. This is a big step toward production-shaped autonomy. Remaining work is artifact/timeline tracking, retry/rollback policy, LLM-backed planning, and production config/sidecar hardening.
