# Phase 10 - Mission Recovery Policy

Date: 2026-06-05

## What Changed

- Added `MissionRecoveryPolicy` to persisted missions.
- Missions now track retry count, retry budget, rollback status, rollback reason, and timestamps.
- Added `MissionRunner.retry()`.
- Added `MissionRunner.request_rollback()`.
- Added `/missions/{mission_id}/retry`.
- Added `/missions/{mission_id}/rollback`.
- Mission Control now exposes RETRY and ROLLBACK controls for the selected mission.

## Safety Contract

- Retry only runs missions that are currently `blocked` or `failed`.
- Retry is bounded by `max_retries`.
- Retry restarts from the first blocked/failed step rather than replaying known-completed steps.
- Rollback does not pretend to undo arbitrary real-world actions.
- Rollback creates a manual review artifact with compensating-action candidates.

## Verification

- `python -m pytest -q tests/backend/test_missions.py tests/backend/test_autonomous_executor.py tests/frontend/test_feature_registry.py`
- `node --check frontend/js/widgets.js`
- `node --check frontend/js/demo.js`
- `node --check frontend/js/terminal.js`
- `python run_vector.py smoke`
- `python run_vector.py doctor`

## Current Reality

VECTOR now has an explicit recovery policy instead of silent failure. This is still intentionally conservative: rollback is a reviewed plan, not automatic reversal. The next big phase is LLM-backed planning using the local model stack, with safety classification before any proposed step becomes executable.
