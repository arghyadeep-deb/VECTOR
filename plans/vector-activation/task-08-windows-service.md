# Task 08 — Install Windows service (always-on)

- **Depends on:** Task 06 (prove voice manually before going always-on)
- **Who:** OWNER (admin shell)
- **Effort:** ~10 min

## Objective

VECTOR runs as a supervised Windows service: auto-start on boot, auto-restart
on crash, CTRL+C drain on stop. The loop (and its 18 coroutines, 2AM reflect,
nightly self-check) becomes genuinely autonomous.

## Implementation

Admin PowerShell:

```
powershell -ExecutionPolicy Bypass -File scripts/install_service.ps1
```

(NSSM-based; `AppStopMethodConsole=1` already configured for graceful drain.)

## Tests

- `Get-Service VECTOR*` → Running
- Kill the python process → NSSM restarts it within seconds
- `Stop-Service` → log shows graceful asyncio drain, not a hard kill

## Demo

Reboot the machine; VECTOR is running without you touching anything.

## Acceptance

- [ ] Service survives reboot
- [ ] Crash → auto-restart observed
- [ ] Stop → graceful drain in logs
- [ ] Log rotation working (no unbounded file growth)
