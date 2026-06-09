# Phase 5 - Mission Decomposition

Date: 2026-06-05

## What Changed

- Added `ObjectiveDecomposer` to translate plain objectives into candidate mission steps.
- Added `/missions/decompose`.
- Added `decompose: true` support to `/missions/plan` and `/missions/run`.
- Extended mission steps with `source`, `confidence`, and `requires_review`.
- Extended missions with `review_required` and `decomposition` metadata.
- Added `/missions/decompose` to the frontend platform panel surface.

## Safety Contract

- Explicit user-provided steps still take priority.
- Risky terms such as delete, wipe, transfer, trade, deploy, password, and key operations are not decomposed into executable actions.
- Risky or uncertain objectives become review-required `respond` steps.
- Decomposition is rule-based and conservative; it is not pretending to be full LLM planning yet.

## Verification

- `python -m pytest -q tests/backend/test_missions.py tests/backend/test_autonomous_executor.py tests/frontend/test_feature_registry.py`
- `node --check frontend/js/widgets.js`
- `python run_vector.py smoke`
- `python run_vector.py doctor`

## Current Reality

VECTOR can now accept a natural-language objective and produce safe candidate mission steps for simple tasks like weather checks, web research, timers, reminders, and response-style work. It still needs richer LLM-backed planning, owner review UI, persisted mission history, and rollback/retry policy before it reaches mature JARVIS-like autonomy.
