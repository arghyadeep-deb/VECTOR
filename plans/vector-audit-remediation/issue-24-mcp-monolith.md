# Issue 24 — mcp_server.py 3,920-line monolith

- **Severity:** MEDIUM-HIGH · **Category:** Architecture / Maintainability
- **Source (audit):** `mcp_server.py` — 80+ copy-pasted error handlers
- **Status:** ✅ RESOLVED (2026-06-14)

## Resolution
`_add_expansion_tools` (3,145 lines, ~300 tools) lifted verbatim into
`core/mcp_tools/expansion.py:add_expansion_tools(mcp)`. `core/mcp_server.py`
now imports and calls it; the shared `_reg` stub-registrar moved to
`core/mcp_tools/error_handling.py:register_stub_tool`. **mcp_server.py: 4,353 →
1,201 lines.** Safety net proved no behavioral change:
- registered tool inventory identical (353 tools, name-set SHA `3824d04807007a5b`)
  — frozen in `test_mcp_tool_inventory_unchanged_after_split`.
- end-to-end `call_tool` on moved tools (`agent_list`, `config_version`) works.
- `tests/ -k mcp` 45 passed; smoke 38/38; audit suite 60 passed; compileall clean.

## (historical) Why it was deferred first / safe plan followed

## Why deferred (2026-06-14)
The file is 4,353 lines, but it is NOT 80+ scattered handlers anymore. The
shape now:
- The tool groups are already separate functions: `_add_collections_tools`,
  `_add_voice_profile_tools`, `_add_browser_tools`, `_add_knowledge_tools`,
  `_add_claims_tools`, `_add_guidance_tools`, `_add_kanban_tools`,
  `_add_email_tools`, `_add_research_tools`, `_add_brain_vault_tools`,
  `_add_code_graph_tools` — and codex already extracted `core/mcp_tools/
  memory_safety.py` + `code_graph.py`.
- The actual monolith is **one ~3,147-line function**, `_add_expansion_tools()`
  (lines 745–3892), which registers 80+ live `@mcp.tool()` closures.

Splitting that one function means relocating 80+ tool registrations that VECTOR
agents call at runtime. A silent registration miss = a tool quietly disappears.
This is a high-risk, low-urgency, organizational-only change — wrong to rush in a
budget-constrained pass. It needs its own session with an MCP tool-inventory
regression test (assert the full registered-tool set is unchanged before/after).

## Safe plan for that session
1. Add a regression test that snapshots `mcp.list_tools()` names → freeze count.
2. Create `core/mcp_tools/expansion/` and move cohesive sub-clusters out of
   `_add_expansion_tools` one at a time (memory, scheduler, control, media, …),
   each as `register(mcp)`; re-run the snapshot test after every move.
3. `mcp_server.py` becomes a thin orchestrator calling each `register(mcp)`.
Acceptance: tool-name snapshot identical; smoke 38/38; audit suite green.

## Issue (as reported)
`core/mcp_server.py` is a ~3,920-line monolith with 80+ duplicated error
handlers — hard to maintain and review.

## Analysis (to complete during analysis pass)
- Affected files: `core/mcp_server.py`
- Fixed in this pass: extracted `_mcp_call_json()` as the shared error-handling
  primitive and converted the kanban tool group to use it.
- Follow-up hardening extracted `core/mcp_tools/memory_safety.py` and
  `core/mcp_tools/code_graph.py`, with `core/mcp_server.py` delegating to those
  modules instead of owning those implementations inline.
- Remaining: full closure still requires moving `_add_*_tools` groups into
  focused modules under a `core/mcp_tools/` package and converting the rest of
  the repeated handlers. This is intentionally not marked resolved yet.
- Tests / Acceptance so far:
  `test_mcp_call_json_helper_returns_json_error` plus existing MCP hardening
  tests.
