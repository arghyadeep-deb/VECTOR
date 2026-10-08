# MCP Expansion Audit Wiring Plan

## Goal

Route every tool registered by the 16 MCP expansion modules through the existing
`mcp_secure_call` audit and rate-limit chokepoint without changing the expansion
modules or their tool schemas.

## Steps

1. Capture FastMCP 3.2.4's real decorator behavior and an unwrapped 287-tool
   schema snapshot.
2. Add a transparent MCP proxy in `core/mcp_tools/expansion.py` that wraps sync
   and async handlers, preserves metadata/signatures, and returns the established
   JSON blocked response before underlying logic can run.
3. Pass one proxy per expansion module with its domain-specific district label.
4. Add regression coverage for complete registration/schema equivalence,
   cross-domain blocking and district attribution, and allowed execution against
   an isolated memory database.
5. Run the focused test red before the fix, then green after it; compile every
   touched Python file and run the requested MCP/security test selection.

## Non-goals

- No edits to `core/mcp_tools/expansion_modules/*.py`.
- No Permission Gateway tier or owner-approval policy changes.
- No change to `memory_clear`'s confirmation check.
