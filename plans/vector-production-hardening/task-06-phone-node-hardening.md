# Task 06 - Phone node hardening

- **Depends on:** none
- **Who:** me
- **Effort:** 2-4 hours
- **Design:** `AUDIT_REPORT.md`, `docs/TERMUX_SETUP.md`

## Objective

Harden the ambient phone node configuration and auth behavior so it cannot send
commands upstream with an empty or malformed API key.

## Files

- `phone_node/ambient_server.py` - robust env parsing and auth checks
- `phone_node/setup.sh` - document required key behavior if needed
- `tests/` - add phone node hardening tests

## Implementation

Replace the custom `.env` parser with `python-dotenv` if available, or make the
parser correctly handle quotes, comments, and whitespace. Require a non-empty
`VECTOR_API_KEY` before sending upstream command/action requests. Return a clear
error when the key is missing.

## Tests

- Quoted `.env` values parse correctly.
- Missing `VECTOR_API_KEY` prevents upstream sends.
- Configured `VECTOR_API_KEY` is sent as a bearer token.

## Demo

```powershell
python -m pytest -q tests/backend/test_phone_node_hardening.py
```

## Acceptance

- [ ] Empty phone-node API key cannot send upstream commands.
- [ ] Quoted and commented env values parse correctly.
- [ ] Existing setup docs/scripts still show how to configure the key.
