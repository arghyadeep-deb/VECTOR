# Phase 11 - Local LLM Mission Planner

## Summary
VECTOR now has a local-model advisory planning path for missions. The planner asks a local LLM for candidate steps, parses the response defensively, classifies every suggested action through the permission gateway, and falls back to the rule-based decomposer when the model is unavailable or returns unusable output.

## Backend
- Added `MissionPlanAdvisor` in `core.runtime.missions`.
- Added mission planning flag `llm_plan`.
- Added `POST /missions/advise` for advisory decomposition without creating a mission.
- Kept execution unchanged: model-suggested steps are only candidates and still pass through the mission runner and permission gateway.

## Frontend
- Added `LLM PLAN` to Mission Control.
- Registered `/missions/advise` in Mission Control and Platform endpoint coverage.

## Safety Notes
- The local LLM cannot grant approval.
- Non-GREEN actions, unknown actions, and low-confidence suggestions are marked `requires_review`.
- If Ollama or any fallback model is unavailable, VECTOR returns the conservative rule-based plan.

## Verification
- `tests/backend/test_missions.py`
- `tests/backend/test_autonomous_executor.py`
- `tests/frontend/test_feature_registry.py`
- JS syntax checks for Mission Control files
- `python run_vector.py smoke`
- `python run_vector.py doctor`
