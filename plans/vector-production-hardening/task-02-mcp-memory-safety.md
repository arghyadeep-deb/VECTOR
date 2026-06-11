# Task 02 - MCP memory safety

- **Depends on:** none
- **Who:** me
- **Effort:** 2-4 hours
- **Design:** `AUDIT_REPORT_core.md`

## Objective

Harden MCP memory tools so an MCP caller cannot wipe memory accidentally or read
and write arbitrary files through import/export paths.

## Files

- `core/mcp_server.py` - harden `memory_clear`, `memory_export`, `memory_import`
- `tests/` - add targeted MCP memory safety tests

## Implementation

Restrict import/export paths to an approved memory export directory under the
runtime data root. Reject absolute paths outside that directory and any
traversal such as `..`. Require an explicit confirmation phrase or equivalent
structured parameter before `memory_clear` can delete rows.

Keep the user-facing MCP response JSON stable where possible, but return clear
errors for rejected paths and missing confirmation.

## Tests

- Path traversal import/export attempts are rejected.
- Absolute paths outside the allowed export directory are rejected.
- Normal export/import inside the allowed directory still works.
- `memory_clear` without explicit confirmation does not delete memory.
- `memory_clear` with confirmation deletes only the intended table.

## Demo

```powershell
python -m pytest -q tests/backend/test_mcp_memory_safety.py
```

## Acceptance

- [ ] MCP memory import/export cannot access paths outside the approved directory.
- [ ] MCP memory clear requires explicit destructive-action confirmation.
- [ ] New tests cover rejected traversal, rejected absolute paths, and allowed paths.
- [ ] Existing smoke test still passes.
