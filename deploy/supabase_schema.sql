-- VECTOR memory mesh — 6 tables (Postgres dialect: Supabase).
-- Paste into Supabase → SQL Editor → Run.
-- The sync uses the SERVICE-ROLE key (Bearer), which bypasses RLS, so no RLS
-- policies are required. Do NOT expose these tables with the anon key.

CREATE TABLE IF NOT EXISTS episodic_memory (
    id text PRIMARY KEY,
    event_type text,
    content text,
    tags text,
    context_snapshot text,
    timestamp text,
    source text
);

CREATE TABLE IF NOT EXISTS semantic_memory (
    key text PRIMARY KEY,
    value text,
    category text,
    confidence double precision DEFAULT 0.5,
    updated_at text
);

CREATE TABLE IF NOT EXISTS policy_memory (
    action_type text,
    situation_hash text,
    avg_reward double precision,
    sample_count integer DEFAULT 0,
    last_updated text,
    veto_count integer DEFAULT 0,
    PRIMARY KEY (action_type, situation_hash)
);

CREATE TABLE IF NOT EXISTS reasoning_chains (
    chain_id text PRIMARY KEY,
    situation text,
    goal_ids text,
    steps text,
    action_taken text,
    outcome text,
    reward double precision DEFAULT 0.0,
    is_training_data integer DEFAULT 0,
    timestamp text
);

CREATE TABLE IF NOT EXISTS skill_memory (
    skill_name text PRIMARY KEY,
    confidence double precision DEFAULT 0.5,
    last_practiced text,
    evidence text,
    related_skills text
);

CREATE TABLE IF NOT EXISTS agent_history (
    agent_id text,
    agent_name text,
    district text,
    generation integer,
    final_hp integer,
    ghost_memory text,
    died_at text,
    PRIMARY KEY (agent_id, generation)
);
