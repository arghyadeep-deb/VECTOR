# Plan: VECTOR security, provenance, and acceptance

## Objective

Close the evidence loop without allowing VECTOR to self-authorize or
self-modify its safety boundaries.

## Files and artifacts

- `vectorcode/src/skills/red-teaming/godmode/scripts/godmode_race.py`
- `vectorcode/src/skills/red-teaming/godmode/scripts/load_godmode.py`
- `vectorcode/src/skills/red-teaming/godmode/auto_jailbreak.py`
- `vectorcode/src/agents/workflow_engine.py`
- `.github/workflows/*`
- `THIRD_PARTY_NOTICES.md`
- component-specific `NOTICE.md` files
- SBOM/provenance output under `docs/` or `artifacts/`
- `docs/design/gap-register.md`
- `docs/OPEN_ISSUES.md`
- `frontend/VECTOR.html` and API acceptance routes

## Steps

1. Add tests proving Godmode and compatibility shell paths are not exposed to
   autonomous discovery or unapproved dispatch.
2. Complete vendored-component dispositions and notices without deleting code
   that still has real callers.
3. Verify CI and branch-protection evidence; do not claim remote configuration
   from local hooks alone.
4. Run read-only shadow audit and compare its findings with the matrix.
5. Start the API/loop under controlled isolated data roots.
6. Verify health/readiness, command execution, Gateway approvals, memory,
   restart/recovery, heartbeat freshness, and HUD/API parity.
7. Run the owner voice/camera checks and one real day of use.
8. Record SLO evidence: availability, false-success rate, unauthorized actions,
   latency, recovery time, and memory growth.

## Verification

```powershell
python -m pytest -q tests/test_safety_gate_fault_injection.py tests/test_bug_hunter_path_confinement.py
python -m pytest -q tests -m "not requires_ollama" --timeout=120
python -m compileall -q core districts vectorcode scripts run_vector.py
python run_vector.py doctor
python run_vector.py readiness-check
```

The full shard command is run only after the focused suites are green. Existing
claims-state and Windows privilege failures must be resolved or explicitly
classified before the final verdict.

## Final gate

The repository is complete only when every configured capability is LIVE,
NEEDS_CONFIG, FAIL_CLOSED, RETIRED, or DEFERRED with evidence. Accepted gaps
remain visible with owners and revisit dates.
