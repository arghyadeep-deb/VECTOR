# Task 08 - Sidecar production certification

- **Depends on:** 01
- **Who:** OWNER -> me
- **Effort:** 1-2 hours after sidecars are installed
- **Design:** `README.md`, `core/runtime/doctor.py`

## Objective

Configure and verify the production sidecars required by strict readiness:
ComfyUI, LibreChat, and UI-TARS.

## Files

- `.env` or deployment secret store - set local sidecar paths outside git
- `core/runtime/doctor.py` - only if health/path checks need adjustment
- `tests/backend/test_runtime_doctor.py` - only if doctor behavior changes

## Implementation

Set these values to real local directories:

- `VECTOR_COMFYUI_PATH`
- `VECTOR_LIBRECHAT_PATH`
- `VECTOR_UITARS_PATH`

Start or configure the sidecar services so doctor health checks can certify
them. Keep health URLs loopback/private unless a separate authenticated public
deployment is intentionally configured.

## Tests

- Run strict production doctor.
- Confirm all sidecar path checks are `ok`.
- Confirm required sidecar health checks are `ok`.

## Demo

```powershell
$env:VECTOR_ENV='production'; python run_vector.py doctor
```

## Acceptance

- [ ] `sidecar:comfyui_path` is `ok`.
- [ ] `sidecar:librechat_path` is `ok`.
- [ ] `sidecar:ui_tars_path` is `ok`.
- [ ] Required sidecar health checks pass or are explicitly certified.
