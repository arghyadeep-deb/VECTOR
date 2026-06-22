-- VECTOR Worker D1 schema — remote command queue.
-- Apply with:
--   wrangler d1 execute vector-brain --file=schema.sql           (local)
--   wrangler d1 execute vector-brain --remote --file=schema.sql  (production)

CREATE TABLE IF NOT EXISTS command_queue (
    id           TEXT PRIMARY KEY,
    type         TEXT NOT NULL,
    params       TEXT,                 -- JSON
    status       TEXT DEFAULT 'queued',-- queued | delivered | running | done | failed | deferred
    target_node  TEXT DEFAULT 'legion-heavy-node',
    result       TEXT,                 -- JSON
    error        TEXT,
    created_at   TEXT,
    delivered_at TEXT,
    claimed_at   TEXT,
    completed_at TEXT,
    updated_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_command_queue_status
    ON command_queue(status, created_at);

CREATE INDEX IF NOT EXISTS idx_command_queue_target_status
    ON command_queue(target_node, status, created_at);

-- Existing D1 databases created before these columns need an additive migration
-- with the same new columns. Keep this base schema idempotent for fresh local DBs.
