# mistral-vibe-main Audit

**Repo:** mistral-vibe — Python coding agent (Mistral AI's open-source Claude Code equivalent, Apache 2.0)
**Audited:** 2026-06-02
**Verified:** `ask_user_question in mcp: NO` — VECTOR lacks this tool

---

## 1. Repo Reality

Python autonomous coding agent with:
- `ask_user_question` tool — structured multi-option questions with typed responses mid-task
- Tree-sitter bash AST safety guard — deterministic static analysis of bash commands before execution
- Named permission profiles: `plan` / `accept-edits` / `auto-approve` mapped to trust tiers
- Tool orchestration loop (Edit, Shell, Browser, Search)
- Provider-agnostic LLM routing

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Verified output | Status |
|---------|------------------|-----------------|--------|
| Coding agent loop | `core/code_conductor/orchestrator.py` | ✅ | ✅ |
| Provider-agnostic LLM | `core/inference/provider_client.py` | ProviderClient OK | ✅ |
| Permission gateway | `core/loop/permission_gateway.py` | GREEN/YELLOW/RED | ✅ |
| `ask_user_question` tool | ❌ Not in `core/mcp_server.py` | grep: NO | ❌ |
| Tree-sitter bash AST guard | ❌ LLM injection scanner only | No static analysis | ❌ |
| Named permission profiles | ❌ No preset trust-level profiles | N/A | ❌ |

---

## 3. Frontend: N/A (CLI tool)

---

## 4. Verdict

**PATCH VECTOR** — 3 targeted gaps to port (~150 LOC total):
1. Add `ask_user_question(options: list[str])` MCP tool to `core/mcp_server.py`
2. Add tree-sitter bash AST check to `permission_gateway.py` before shell execution
3. Add named permission profiles mapping to GREEN/YELLOW/RED tiers

**Delete-readiness:** DELETE-AFTER porting 3 components.

---

## 5. Gaps

| ID | Issue | File:line | Severity |
|----|-------|-----------|----------|
| G1 | `ask_user_question` tool missing from MCP — agents can't ask structured mid-task questions | `core/mcp_server.py` | MED |
| G2 | No tree-sitter bash AST safety guard — only LLM-based injection scanning | `core/loop/permission_gateway.py` | MED |
| G3 | No named permission profiles (plan/accept-edits/auto-approve) | `core/loop/permission_gateway.py` | LOW |
