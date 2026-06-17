-- VECTOR memory mesh — 6 tables (SQLite dialect: Turso + Cloudflare D1).
-- Matches core/memory/episodic.py exactly so last-write-wins sync works.
--
-- Turso:  turso db shell vector < deploy/sqlite_schema.sql
-- D1:     wrangler d1 execute vector-brain --remote --file=deploy/sqlite_schema.sql

CREATE TABLE IF NOT EXISTS episodic_memory (
    id TEXT PRIMARY KEY,
    event_type TEXT,
    content TEXT,
    tags TEXT,
    context_snapshot TEXT,
    timestamp TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS semantic_memory (
    key TEXT PRIMARY KEY,
    value TEXT,
    category TEXT,
    confidence REAL DEFAULT 0.5,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS policy_memory (
    action_type TEXT,
    situation_hash TEXT,
    avg_reward REAL,
    sample_count INTEGER DEFAULT 0,
    last_updated TEXT,
    PRIMARY KEY (action_type, situation_hash)
);

CREATE TABLE IF NOT EXISTS reasoning_chains (
    chain_id TEXT PRIMARY KEY,
    situation TEXT,
    goal_ids TEXT,
    steps TEXT,
    action_taken TEXT,
    outcome TEXT,
    reward REAL DEFAULT 0.0,
    is_training_data INTEGER DEFAULT 0,
    timestamp TEXT
);

CREATE TABLE IF NOT EXISTS skill_memory (
    skill_name TEXT PRIMARY KEY,
    confidence REAL DEFAULT 0.5,
    last_practiced TEXT,
    evidence TEXT,
    related_skills TEXT
);

CREATE TABLE IF NOT EXISTS agent_history (
    agent_id TEXT,
    agent_name TEXT,
    district TEXT,
    generation INTEGER,
    final_hp INTEGER,
    ghost_memory TEXT,
    died_at TEXT,
    PRIMARY KEY (agent_id, generation)
);
