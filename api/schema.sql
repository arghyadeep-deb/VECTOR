-- VECTOR Worker D1 schema — remote command queue.
-- Apply with:
--   wrangler d1 execute vector-brain --file=schema.sql           (local)
--   wrangler d1 execute vector-brain --remote --file=schema.sql  (production)

CREATE TABLE IF NOT EXISTS command_queue (
    id           TEXT PRIMARY KEY,
    type         TEXT NOT NULL,
    params       TEXT,                 -- JSON
    status       TEXT DEFAULT 'queued',-- queued | delivered
    created_at   TEXT,
    delivered_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_command_queue_status
    ON command_queue(status, created_at);
