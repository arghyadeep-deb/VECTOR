-- Add node targeting and result tracking to the Cloudflare command queue.
-- Apply once to D1 databases created from the earlier schema.

ALTER TABLE command_queue ADD COLUMN target_node TEXT DEFAULT 'legion-heavy-node';
ALTER TABLE command_queue ADD COLUMN result TEXT;
ALTER TABLE command_queue ADD COLUMN error TEXT;
ALTER TABLE command_queue ADD COLUMN claimed_at TEXT;
ALTER TABLE command_queue ADD COLUMN completed_at TEXT;
ALTER TABLE command_queue ADD COLUMN updated_at TEXT;

CREATE INDEX IF NOT EXISTS idx_command_queue_target_status
    ON command_queue(target_node, status, created_at);

