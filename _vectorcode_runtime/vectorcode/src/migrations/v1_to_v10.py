# Ported from GitHub/VectorCode_vectorcode/repo/vector_state.py (schema migration)
"""Migration: session_db v1 → SCHEMA_VERSION 10.

Adds columns required for full VectorCode compatibility:
  sessions: parent_session_id, billing_provider, billing_mode,
            estimated_cost_usd, actual_cost_usd, cost_status,
            api_call_count, focus_topic
  messages: is_training_data
"""
import sqlite3
from pathlib import Path
from loguru import logger


def migrate_v1_to_v10(conn: sqlite3.Connection) -> None:
    """Apply all schema changes from v1 to v10 in-place."""
    cursor = conn.cursor()

    # Sessions table additions
    session_columns = {
        "parent_session_id": "TEXT",
        "billing_provider": "TEXT",
        "billing_mode": "TEXT",
        "estimated_cost_usd": "REAL DEFAULT 0.0",
        "actual_cost_usd": "REAL DEFAULT 0.0",
        "cost_status": "TEXT",
        "api_call_count": "INTEGER DEFAULT 0",
        "focus_topic": "TEXT",
    }

    existing_session_cols = {row[1] for row in cursor.execute("PRAGMA table_info(sessions)")}
    for col, col_type in session_columns.items():
        if col not in existing_session_cols:
            cursor.execute(f"ALTER TABLE sessions ADD COLUMN {col} {col_type}")
            logger.debug(f"Added sessions.{col}")

    # Messages table additions
    message_columns = {
        "is_training_data": "INTEGER DEFAULT 0",
    }
    existing_msg_cols = {row[1] for row in cursor.execute("PRAGMA table_info(messages)")}
    for col, col_type in message_columns.items():
        if col not in existing_msg_cols:
            cursor.execute(f"ALTER TABLE messages ADD COLUMN {col} {col_type}")
            logger.debug(f"Added messages.{col}")

    # Update schema version
    cursor.execute("DELETE FROM schema_version")
    cursor.execute("INSERT INTO schema_version (version) VALUES (10)")
    conn.commit()
    logger.info("Migrated session_db to SCHEMA_VERSION 10")


def migrate_up(db_path: Path) -> None:
    """Migrate the database at db_path to the latest schema version."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        current_version = row[0] if row else 0

        if current_version < 10:
            logger.info(f"Migrating session_db from v{current_version} to v10")
            migrate_v1_to_v10(conn)
        else:
            logger.debug(f"session_db already at v{current_version}, no migration needed")
    finally:
        conn.close()
