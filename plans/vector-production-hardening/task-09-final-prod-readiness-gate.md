# Task 09 - Final prod readiness gate

- **Depends on:** 01, 02, 03, 04, 05, 06, 07, 08
- **Who:** me
- **Effort:** 1-2 hours
- **Design:** `README.md`, `HANDOFF_TODO.md`, `AUDIT_REPORT.md`, `AUDIT_REPORT_core.md`

## Objective

Run the final production-readiness gate after all hardening tasks are complete
and record the result so VECTOR has one clear go/no-go signal.

## Files

- `plans/vector-production-hardening/INDEX.md` - mark tasks done as they pass
- `HANDOFF_TODO.md` or a new audit note - summarize final result if needed

## Implementation

Run the required checks in a clean shell with production environment values
configured. Do not mark this task done until strict doctor, smoke, and focused
frontend/backend tests all pass.

## Tests

- `python run_vector.py smoke`
- `python run_vector.py doctor`
- `VECTOR_ENV=production python run_vector.py doctor`
- `python -m pytest -q tests/backend/test_runtime_doctor.py tests/frontend/test_frontend_bundle.py tests/backend/test_hud_entrypoint.py`
- New targeted tests from tasks 02-07

## Demo

```powershell
python run_vector.py smoke
python run_vector.py doctor
$env:VECTOR_ENV='production'; python run_vector.py doctor
python -m pytest -q tests/backend/test_runtime_doctor.py tests/frontend/test_frontend_bundle.py tests/backend/test_hud_entrypoint.py
```

## Acceptance

- [ ] Smoke test passes.
- [ ] Default doctor has `required_failed: 0`.
- [ ] Strict production doctor has `required_failed: 0`.
- [ ] Focused frontend/backend pytest suite passes.
- [ ] Targeted hardening tests from tasks 02-07 pass.
- [ ] INDEX status accurately reflects completed tasks.
