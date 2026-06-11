# Task 01 - Production env + secrets

- **Depends on:** none
- **Who:** OWNER
- **Effort:** 30-60 minutes
- **Design:** `README.md`, `.env.example`, `HANDOFF_TODO.md`

## Objective

Configure the production-only secrets required for strict startup readiness so
VECTOR can run with `VECTOR_ENV=production` without falling back to development
auth behavior.

## Files

- `.env` or deployment secret store - set real production values locally only
- `.env.production` or platform secrets - set deployment values outside git

## Implementation

Generate and store strong values for:

- `VECTOR_API_KEY` - at least 32 random characters
- `VECTOR_JWT_SECRET` - at least 48 random characters
- `HUMANLAYER_API_KEY` - real HumanLayer key for RED-tier approvals

Do not commit real secrets. Rotate any values that were previously exposed in
git history before publishing or deploying.

## Tests

- Run `VECTOR_ENV=production python run_vector.py doctor`.
- Confirm the three `env:*` checks are `ok`.

## Demo

```powershell
$env:VECTOR_ENV='production'; python run_vector.py doctor
```

## Acceptance

- [ ] `env:VECTOR_API_KEY` is `ok` in strict production doctor.
- [ ] `env:VECTOR_JWT_SECRET` is `ok` in strict production doctor.
- [ ] `env:HUMANLAYER_API_KEY` is `ok` in strict production doctor.
- [ ] No real secret value is committed to git.
