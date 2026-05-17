# Local runtime storage uses SQLite (with FTS5 and WAL mode), not PostgreSQL

All on-device memory tables (episodic_memory, semantic_memory, policy_memory, reasoning_chains, skill_memory, agent_history) use SQLite with FTS5 full-text search and WAL mode. Supabase (PostgreSQL) is used only for cloud sync — it is never in the hot path of the autonomous loop.

**Why**: SQLite runs without a server process, survives laptop sleep/wake, works offline, and has sub-millisecond reads for the loop's 0.5s observe tick. The FTS5 extension gives full-text search over episodic memory without needing Elasticsearch. Supabase is async-synced, never blocking.
