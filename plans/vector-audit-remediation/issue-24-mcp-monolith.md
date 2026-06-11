# Issue 24 — mcp_server.py 3,920-line monolith

- **Severity:** MEDIUM-HIGH · **Category:** Architecture / Maintainability
- **Source (audit):** `mcp_server.py` — 80+ copy-pasted error handlers
- **Status:** ⬜ TODO

## Issue (as reported)
`core/mcp_server.py` is a ~3,920-line monolith with 80+ duplicated error
handlers — hard to maintain and review.

## Analysis (to complete during analysis pass)
- Affected files: `core/mcp_server.py`
- Fix approach: _pending_ (extract `_add_*_tools` groups into submodules under
  `core/mcp_tools/`; shared error-handling decorator to replace copy-paste).
  Large refactor — sequence AFTER the security/stability fixes land, to avoid
  churn during the higher-priority work.
- Tests / Acceptance: _pending_ (tool registry unchanged; existing MCP tests green)
