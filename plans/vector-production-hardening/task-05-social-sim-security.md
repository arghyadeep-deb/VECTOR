# Task 05 - Social sim security

- **Depends on:** none
- **Who:** me
- **Effort:** 2-3 hours
- **Design:** `AUDIT_REPORT.md`

## Objective

Remove unsafe Flask defaults from the social simulation service so it cannot
ship with a known session secret, debug mode, or wildcard CORS.

## Files

- `districts/intelligence/vector_social_sim/app/config.py`
- `districts/intelligence/vector_social_sim/app/__init__.py`
- `tests/` - add social sim config/security tests

## Implementation

Require `SECRET_KEY` when running in production-like modes, default `DEBUG` to
false, and make CORS origins configurable rather than `*`. Development may keep
an explicit opt-in path, but unsafe behavior must be visible and intentional.

## Tests

- Missing `SECRET_KEY` fails production config validation.
- Debug defaults to false.
- CORS does not default to wildcard in production.
- Explicit dev config can still run locally.

## Demo

```powershell
python -m pytest -q tests/backend/test_social_sim_security.py
```

## Acceptance

- [ ] No hardcoded Flask secret is used as a production fallback.
- [ ] Flask debug mode is not enabled by default.
- [ ] Production CORS origins are explicit.
- [ ] Tests cover production and development behavior.
