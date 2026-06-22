# headroom-main - VECTOR Absorption Review

**Verdict:** IMPLEMENT narrow context-compression and retrieval patterns. Do not wrap VECTOR wholesale with the Headroom proxy.

**Priority:** HIGH-MEDIUM

**Effort:** 1-2 sessions for a VECTOR-native context-budget layer; more if adding proxy compatibility

**License:** Apache-2.0

**Repo size inspected:** About 3215 files, excluding git/build/cache directories.

## What It Is

Headroom is a context optimization layer for AI agents. It compresses tool outputs, logs, RAG chunks, files, and conversation history before they reach an LLM. It supports:

- Python and TypeScript library modes
- OpenAI-compatible proxy mode
- agent wrapping for Claude/Codex/Cursor/Aider/Copilot
- MCP tools for compression/retrieval/stats
- reversible compression with cached originals
- code-aware and JSON-aware compressors
- output token reduction / verbosity steering
- shared cross-agent memory

## VECTOR Overlap

VECTOR already has:

- local SQLite memory and FTS
- research-engine context limiting
- provider clients and model-routing surfaces
- MCP/tool surfaces
- long-running agent/memory loops

But VECTOR still has a real risk area: large research, repo analysis, logs, and tool outputs can flood prompts. Headroom is directly relevant to reducing cost and context failure.

## Real Value For VECTOR

Useful clean-room ideas:

- central context-budget manager before provider calls
- compression policy by content type: logs, JSON, code, markdown, research results
- reversible "summary plus retrieval handle" format
- cached originals keyed by content hash
- output verbosity/effort shaping for routine turns
- token-savings telemetry per task/provider
- MCP-style `compress`, `retrieve`, and `stats` tools

## Risks

- proxy wrapping can bypass VECTOR's own PermissionGateway/provider controls if installed carelessly
- extra compression can hide critical security details if retrieval is not reliable
- ML compression dependencies may be heavy
- Headroom's agent wrappers should not be allowed to mutate Codex/Claude config automatically inside VECTOR

## Recommendation For Sonnet

Implement a VECTOR-native context-budget layer, not a dependency-first proxy migration.

Suggested sequence:

1. Add a lightweight `ContextBudgetManager` around VECTOR provider calls.
2. Start with deterministic compression: truncation with head/tail preservation, JSON key pruning, log folding, duplicate removal, and source hashes.
3. Store originals in SQLite with content hashes and retrieval handles.
4. Add telemetry: input tokens before/after, compression ratio, retrieval count, failure reason.
5. Only after tests pass, evaluate optional Headroom sidecar/proxy mode.

## Acceptance Criteria

- PermissionGateway and provider auth paths are unchanged.
- Compression is disabled or conservative by default for safety-critical actions.
- Every compressed artifact has a retrieval handle and source hash.
- Research/tool-output prompts stay under configured token budgets.
- Missing compression backend never blocks VECTOR.

