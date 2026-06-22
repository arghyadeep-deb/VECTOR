# helix-db-main - VECTOR Absorption Review

**Verdict:** OPTIONAL external memory mirror only. Do not replace VECTOR's SQLite hot-path memory.

**Priority:** LOW-MEDIUM

**Effort:** 1-2 sessions for an experimental disabled-by-default adapter

**License:** Apache-2.0 for the main repo; Python SDK metadata indicates MIT.

**Repo size inspected:** About 121 files / 4.9 MB.

## What It Is

HelixDB is a Rust graph-vector database positioned for AI memory and knowledge graphs. The checkout includes:

- Rust workspace pieces
- CLI
- metrics
- SDKs including Python/TypeScript/Go/Rust directions
- docs/examples for dynamic queries over HTTP

The local checkout appears to be mainly CLI/SDK/support code, not something VECTOR should embed as a database engine.

## VECTOR Overlap

VECTOR already has a local memory/storage decision:

- SQLite + FTS5 + WAL is the local hot path
- Supabase/cloud sync is async and optional
- memory must survive offline, sleep/wake, and low-latency observe loops

This is documented in `docs/adr/0006-sqlite-not-postgres-for-local-runtime.md`. HelixDB should not override that architecture.

## Real Value For VECTOR

Useful clean-room / optional ideas:

- graph-vector mirror for long-term knowledge graphs
- research-library relationship graph
- entity/relation exploration for "company brain" style memory
- external adapter for memory export/sync experiments

## Risks

- replacing SQLite would break the local-first runtime assumption
- external DB dependency adds deployment and recovery complexity
- Helix unavailable must never stop VECTOR from thinking/responding
- query/memory contracts need to be stable before adding another storage layer

## Recommendation For Sonnet

Do not modify the memory hot path.

Only consider a disabled-by-default external adapter after existing memory contracts are stable:

1. Keep SQLite as source of truth for local runtime memory.
2. Add an export/mirror interface, not a replacement.
3. Send selected entities/relations/chunks to HelixDB asynchronously.
4. Treat Helix results as optional enrichment.
5. Ensure VECTOR works exactly the same when Helix is absent.

## Acceptance Criteria

- Existing memory tests continue passing.
- VECTOR starts and functions with no HelixDB installed.
- No observe-loop or permission-gateway path depends on Helix.
- Adapter is disabled by default.
- Failed sync logs a warning but does not fail user work.

