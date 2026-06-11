# Issue 01 — Path traversal in MCP memory_export/import

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `mcp_server.py:1052` — memory_export/import accepts arbitrary filesystem paths
- **Status:** ✅ RESOLVED (production-hardening Task 02, commit 252231e8a) — re-verify against current code

## Issue (as reported)
memory_export / memory_import accept arbitrary filesystem paths → read/write
anywhere via traversal or absolute paths.

## Resolution (already done)
`core/mcp_server.py` now has `_resolve_memory_path()` confining import/export to
`data/memory_exports/` (rejects `..` and absolute-outside paths). Covered by
`tests/backend/test_mcp_memory_safety.py`.

## Verify
- [ ] Confirm `_resolve_memory_path` still guards both tools at current line numbers
- [ ] `pytest tests/backend/test_mcp_memory_safety.py` green
