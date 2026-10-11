# Plan: VECTOR runtime reliability

## Objective

Make provider, loop, scheduler, MCP, and startup degradation observable and
recoverable without creating a second runtime architecture.

## Files to inspect and change only when a failing test requires it

- `core/inference/provider_client.py`
- `core/inference/provider_health.py`
- `core/inference/route_policy.py`
- `core/api/app.py`
- `core/loop/autonomous_loop.py`
- `core/loop/loop_state.py`
- `core/runtime/doctor.py`
- `core/runtime/readiness_check.py`
- `core/mcp_server.py`
- `core/scheduler/tools.py`
- the existing scheduler implementation selected by the runtime
- affected provider, loop, scheduler, MCP, and API tests

## Steps

1. Add tests for provider route states: healthy, cooldown, auth-disabled,
   unknown-model-disabled, and fallback exhaustion.
2. Add tests for stale heartbeat detection, duplicate-loop prevention, clean
   shutdown, and restart recovery.
3. Add tests that scheduler MCP tools receive a real scheduler or return an
   explicit unavailable result, never a silent no-op.
4. Add MCP transport tests for local-only defaults and explicit external auth
   behavior.
5. Implement only the missing wiring and recovery behavior using the existing
   `provider_health`, `CircuitBreaker`, heartbeat, and app lifespan structures.
6. Verify with:

```powershell
python -m pytest -q tests/test_provider_health_circuit_breaker.py tests/test_provider_selection.py tests/test_provider_dns_failfast.py
python -m pytest -q tests/test_regression_status_loop_running.py tests/test_regression_loop_guard_dead_pid.py tests/test_loop_guard_reset.py
python -m pytest -q tests -k "scheduler or mcp or readiness or lifespan" --timeout=120
python run_vector.py doctor
```

## Gate

One failed optional provider/service must degrade that capability and preserve
the rest of the local assistant. A stale or dead loop must not appear healthy.
