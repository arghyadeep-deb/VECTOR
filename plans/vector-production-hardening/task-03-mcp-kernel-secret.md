# Task 03 - MCP kernel secret

- **Depends on:** 01
- **Who:** me
- **Effort:** 1-2 hours
- **Design:** `AUDIT_REPORT_core.md`

## Objective

Make MCP stdio signing use a stable, configured secret in production so signed
requests do not break across restarts or processes.

## Files

- `core/mcp_server_stdio.py` - require stable secret in production
- `core/runtime/doctor.py` - add production check for `MCP_KERNEL_SECRET`
- `tests/backend/test_runtime_doctor.py` or new focused tests

## Implementation

Keep the development fallback if useful for local testing, but fail closed in
production when `MCP_KERNEL_SECRET` is missing or too weak. Add the secret to
the production doctor required checks with remediation text.

## Tests

- Production doctor fails when `MCP_KERNEL_SECRET` is missing.
- Production doctor accepts a strong configured `MCP_KERNEL_SECRET`.
- Development mode still imports `core/mcp_server_stdio.py`.

## Demo

```powershell
$env:VECTOR_ENV='production'; python run_vector.py doctor
```

## Acceptance

- [ ] Production mode has no random per-restart MCP signing secret.
- [ ] Strict doctor reports missing/weak `MCP_KERNEL_SECRET`.
- [ ] Tests prove dev fallback behavior remains intentional.
