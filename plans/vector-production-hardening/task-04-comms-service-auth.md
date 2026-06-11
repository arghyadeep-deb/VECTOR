# Task 04 - Comms service auth

- **Depends on:** 01
- **Who:** me
- **Effort:** 2-3 hours
- **Design:** `AUDIT_REPORT.md`

## Objective

Protect the comms service so network callers cannot trigger outbound messages
without an approved bearer token.

## Files

- `cloud/comms_service/service.py` - add auth middleware/dependency
- `tests/` - add comms service auth tests

## Implementation

Require `Authorization: Bearer <VECTOR_API_KEY>` for `POST /send` and any other
state-changing comms endpoints. In production, fail startup or reject all
requests when `VECTOR_API_KEY` is empty. Keep `/health` or equivalent status
routes public only if they expose no sensitive data.

## Tests

- `POST /send` without auth returns 401.
- `POST /send` with the wrong token returns 401.
- `POST /send` with the correct token reaches the handler.
- Empty key in production fails closed.

## Demo

```powershell
python -m pytest -q tests/backend/test_comms_service_auth.py
```

## Acceptance

- [ ] Unauthenticated `/send` cannot send messages.
- [ ] Wrong bearer token cannot send messages.
- [ ] Correct bearer token works.
- [ ] Production mode with missing key fails closed.
