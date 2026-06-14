# Issue 01 — Path traversal in MCP memory_export/import

- **Severity:** CRITICAL · **Category:** Security
- **Source (audit):** `mcp_server.py:1052` — memory_export/import accepts arbitrary filesystem paths
- **Status:** ✅ RESOLVED / RE-VERIFIED

## Issue (as reported)
memory_export / memory_import accept arbitrary filesystem paths → read/write
anywhere via traversal or absolute paths.

## Resolution (already done)
`core/mcp_tools/memory_safety.py` now owns `resolve_memory_path()`, re-exported
from `core/mcp_server.py` for compatibility. `memory_export` and
`memory_import` both call the resolver, confining import/export to
`data/memory_exports/` and rejecting traversal or absolute-outside paths.
Covered by `tests/backend/test_mcp_memory_safety.py`.

## Verify
- [x] Confirm `_resolve_memory_path` still guards both tools at current line numbers
- [x] `python -m pytest -q tests/backend/test_mcp_memory_safety.py` green
