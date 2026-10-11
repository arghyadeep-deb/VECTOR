# Plan: VECTOR trust, persistence, and outcomes

## Objective

Prevent test/smoke writes to live state and remove false completion claims at
the Gateway, API, and autonomous-loop boundaries.

## Files

### Modify

- `vectorcode/src/claims/_types.py` — add runtime default-path resolution while
  retaining explicit path injection.
- `vectorcode/src/claims/_persistence.py` — accept `None` and resolve the path
  at repository construction time.
- `vectorcode/src/swarm.py` — keep claim service construction compatible with
  runtime isolation and test injection.
- `run_vector.py` — set both DB and data roots for smoke before construction.
- `tests/conftest.py` — assert claims storage follows the isolated data root.
- `core/loop/permission_gateway.py` — correct handler-specific outcomes.
- `core/runtime/executor.py` — extend shared interpretation only where a
  concrete caller needs it; preserve compatible agent success statuses.
- `core/api/routers/commands.py` — consume shared outcome helpers.
- `core/loop/autonomous_loop.py` — use verified outcome for reward/events and
  notifications.
- `tests/test_audit_phase3_mcp_expansion_a.py` — guard unavailable Windows
  symlink privilege.

### Create

- `tests/test_claims_runtime_isolation.py`
- `tests/test_gateway_handler_outcomes.py`
- `tests/test_autonomous_outcome_accounting.py`
- `docs/design/trust-outcome-evidence-2026-10-10.md`

## TDD sequence

1. Add a test proving default claims construction uses `VECTOR_TEST_DATA_DIR`.
2. Run the swarm regression and the new test; observe the stale
   `%USERPROFILE%\\.vector\\claims.db` failure.
3. Add tests proving an unconfigured vault, failed attendance scrape, failed
   search, and local-only calendar reminder are not reported as full execution.
4. Run them red.
5. Implement the smallest path/outcome changes.
6. Add the Windows symlink skip around creation only, then run the test.

## Verification

```powershell
python -m pytest -q tests/test_claims_runtime_isolation.py tests/test_absorption.py::TestSwarmTopologies::test_agent_state_tracks_task
python -m pytest -q tests/test_gateway_handler_outcomes.py tests/test_outcome_assessment.py tests/test_command_failure_reporting.py tests/test_autonomous_outcome_accounting.py
python -m pytest -q tests/test_audit_phase3_mcp_expansion_a.py::test_file_symlink_escape_denied
python -m compileall -q core districts vectorcode scripts run_vector.py
```

## Gate

No smoke or test path may resolve to live memory or claims state. No approved
handler result may claim `executed` when it did not produce the promised effect.
