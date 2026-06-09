# VECTOR Backend Handoff - 2026-06-05

## Scope

Backend/core stabilization only. Frontend/dashboard work, cloud deployment, phone nodes, and Home Assistant/smart features are intentionally excluded.

## Fixed In This Pass

- Read-only panel endpoints now read state directly instead of dispatching governor actions:
  - `/skills/map`
  - `/relationships/contacts`
  - `/calls/contacts`
- Production honesty fixes:
  - `/investment/portfolio` no longer returns synthetic zero portfolio data when `StockAnalyst` is unavailable.
  - `/location/current` no longer returns hard-coded owner coordinates when IP geolocation fails.
  - `/sb/health` now returns `503` when the ShadowBroker sidecar is unreachable.
- Sentiment analyzer no longer calls Ollama during default keyword-mode analysis.
- Sentiment keyword analysis now returns `neutral` when no keyword/urgency signal exists.
- Fincept absorption path is verified against the absorbed
  `districts/investment/vector_finagent` tree instead of a missing sibling path.
- ComfyUI adapter now exposes operational sidecar helpers for system stats,
  node metadata, model lists, history, jobs, interrupt, memory free, and image
  upload. Missing local upload files return an explicit error instead of a fake
  success.
- Voice profile reference retrieval now returns bytes correctly from
  `FileStorage(LocalDriver(...))`.
- Key rotation/revocation now require the current `VECTOR_API_KEY` bearer token
  when a key is configured, matching the route contract instead of trusting
  localhost alone.
- PC automation endpoints are explicitly permission-gated before governor
  dispatch:
  - `/control/pc/screenshot`
  - `/control/pc/type`
  - `/control/pc/click`
  - `/control/pc/launch-app`
- PC automation action types are classified as `YELLOW` in the permission
  policy.
- Added backend regressions:
  - `tests/backend/test_read_only_status_endpoints.py`
  - `tests/backend/test_production_honesty.py`
  - `tests/backend/test_audit_followups.py`
  - `tests/backend/test_control_gateway.py`

## Verification Run

Passed:

- `python run_vector.py smoke`
- `python -m pytest -q tests/backend/test_control_gateway.py tests/backend/test_audit_followups.py tests/backend/test_production_honesty.py tests/backend/test_read_only_status_endpoints.py tests/test_voice_cloning.py`
- `python -m pytest -q tests/unit/test_permission_gateway.py tests/unit/test_permission_gateway_extra.py tests/backend/test_control_gateway.py`
- `python -m pytest --collect-only -q tests`
- `python -m pytest -q tests/unit tests/backend tests/core`
- `python -m pytest -q tests/districts/health tests/districts/security tests/emergency`
- `python -m pytest -q tests/event_bus`
- `python -m pytest -q tests/resilience`
- `python -m pytest -q tests/persona`
- `python -m pytest -q tests/personality`
- `python -m pytest -q tests/voice tests/training tests/research_engine`
- `python -m pytest -q tests/districts/predictive_analytics tests/districts/coding`
- `python -m pytest -q tests/integration/test_no_stubs.py tests/integration/test_spec15_hardening.py`
- Phase A integration group: `test_phase_a1` through `test_phase_a8`
- Selected non-cloud/non-Home-Assistant integration specs:
  - science
  - personality
  - SIEM
  - health
  - emergency
  - research
  - predictive
  - resilience
  - year2 gaps/cognition
  - trigger/cross-district/full-pipeline/avatar
- Selected investment tests:
  - `districts/investment/vector_backtest/tests/test_mcp_regression.py`
  - `districts/investment/vector_backtest/tests/test_mcp_server_smoke.py`
  - `districts/investment/vector_backtest/tests/test_fundamental_filter_example.py`
  - `districts/investment/vector_finagent/strategies/test_strategies.py`
- Selected ShadowBroker tests:
  - `test_network_utils.py`
  - `test_third_party_fetchers_opt_in.py`
  - `test_2c_exception_visibility.py`

Endpoint matrix:

- `/status` 200
- `/voice/status` 200
- `/investment/hedge/status` 200
- `/investment/market-status` 200
- `/investment/portfolio` 200 in this environment
- `/brain/epistemic/summary` 200
- `/brain/epistemic/staleness` 200
- `/health/status` 200
- `/skills/map` 200
- `/relationships/contacts` 200
- `/calls/contacts` 200
- `/patterns/habits` 200
- `/projects/list` 200
- `/projects/deadline` 200
- `/ops/slo-check` 200
- `/analytics/pipeline-health` 200
- `/governance/autopilot/status` 200
- `/sb/health` 503 when ShadowBroker sidecar is not running; this is expected and now semantically correct.

## Known Exclusions / Remaining Review Targets

- Frontend/dashboard tests still expect the old `dashboard/src/App.tsx` path and fail because this repo uses `frontend/`. This is excluded by request.
- Cloud/Fly/Cloudflare gateway tests are excluded by request.
- Home Assistant tests are excluded by request.
- A full single-command `python -m pytest -q tests` previously timed out; chunked backend/core verification above passed.
- SQLCipher is not installed in this environment, so memory logs warn that plain SQLite is being used.
- `VECTOR_JWT_SECRET` uses a persistent local fallback unless explicitly set.
- ShadowBroker sidecar is not running here; main API correctly reports `/sb/health` as 503.
- Physical voice hardware/audio, real exchange/trading execution, and long-running background runtime were not validated in this pass.

## External Review Prompt

Claude was unavailable, so the immediate backend items above were handled locally.
For a later second-opinion review, focus on:

- Any remaining backend route that returns fake success for unavailable dependencies.
- Any action endpoint that should require explicit permission gateway coverage beyond the PC automation endpoints fixed here.
- Any investment/vector_finagent or intelligence/shadowbroker compatibility layer that exposes incomplete behavior as production.
- Long-running server lifecycle/background jobs beyond startup smoke.
- Security defaults: secrets, encryption, localhost-only assumptions, approval policy boundaries.
