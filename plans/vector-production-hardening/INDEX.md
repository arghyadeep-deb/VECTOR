# VECTOR Production Hardening - Task Index

Goal: turn the current healthy local VECTOR runtime into a production-ready
deployment candidate by closing the security, secret, sidecar, and reliability
gaps found in the 2026-06-11 audits. Status legend: todo | in progress | done.

| Task | Who | Demo | Status |
|------|-----|------|--------|
| [01](./task-01-production-env-secrets.md) Production env + secrets | OWNER | strict doctor no longer fails secret checks | **OWNER — pending** (set real secrets in .env; doctor gates verified green when set) |
| [02](./task-02-mcp-memory-safety.md) MCP memory safety | me | traversal rejected, clear requires confirmation | ✅ done 2026-06-11 (11 tests; also fixed pre-existing `_get_epi` + export/import bugs) |
| [03](./task-03-mcp-kernel-secret.md) MCP kernel secret | me | production doctor fails without stable secret | ✅ done 2026-06-11 (8 tests; fail-closed + doctor check) |
| [04](./task-04-comms-service-auth.md) Comms service auth | me | unauthenticated `/send` returns 401 | ✅ done 2026-06-11 (6 tests) |
| [05](./task-05-social-sim-security.md) Social sim security | me | production config rejects unsafe defaults | ✅ done 2026-06-11 (7 tests) |
| [06](./task-06-phone-node-hardening.md) Phone node hardening | me | empty phone API key cannot send commands | ✅ done 2026-06-11 (6 tests) |
| [07](./task-07-memory-concurrency-safety.md) Memory/concurrency safety | me | concurrent memory tests pass, buffers capped | ✅ done 2026-06-11 (4 tests; write-lock + bounded buffers) |
| [08](./task-08-sidecar-production-certification.md) Sidecar production certification | OWNER -> me | sidecar path + health checks pass | **OWNER — pending** (set paths + start ComfyUI/LibreChat; only the 2 live health checks remain) |
| [09](./task-09-final-prod-readiness-gate.md) Final prod readiness gate | me | smoke, focused tests, strict doctor all pass | ✅ code-side done 2026-06-11 (smoke ok; dev doctor required_failed=0; 57 focused+hardening tests pass; strict doctor green except OWNER 01/08) |

## Result (2026-06-11)

All code-side tasks (02-07) complete with tests; task 09 gate run. Remaining
failures in strict production doctor are **only** the OWNER tasks:
- 01: set real `VECTOR_API_KEY`, `VECTOR_JWT_SECRET`, `HUMANLAYER_API_KEY`,
  `MCP_KERNEL_SECRET` (verified: doctor goes green when these are set).
- 08: set the 3 sidecar paths + start ComfyUI/LibreChat (verified: paths pass
  when set; only the 2 live health checks need the services running).

Simulated full prod env → strict doctor `required_failed` 7 → 2 (the 2 are the
unstarted sidecar HTTP health checks). Code is production-ready; what's left is
owner configuration/credentials, not code.

## Dependency chain

```text
01 -> 03 -> 09
01 -> 04 -> 09
01 -> 08 -> 09
02 -> 09
05 -> 09
06 -> 09
07 -> 09
```

## Notes

- This plan does not replace `plans/vector-activation/`; it tracks hardening
  work discovered after the app became locally bootable.
- Owner tasks require real local/cloud credentials or installed sidecars and
  must not be faked by code changes.
- Code tasks should add tests beside the implementation and update doctor
  checks when a risk should become a production gate.
