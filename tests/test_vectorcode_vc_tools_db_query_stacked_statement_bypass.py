"""Regression for vectorcode/src/vc_tools/db_query.py's _is_read_only_query():

the read-only guard only checked whether the query STARTED with a safe
keyword (SELECT/EXPLAIN/PRAGMA/DESCRIBE/SHOW) for simple statements -- it
never scanned the rest of the string for write keywords unless the query
started with WITH. psycopg2's cursor.execute() (unlike sqlite3's, which
rejects multiple statements per call) happily runs every semicolon-
separated statement in a single execute() call, so a crafted query like
"SELECT 1; DROP TABLE users;" passed the read-only check (starts with
SELECT) and then, against the PostgreSQL backend, actually executed the
DROP TABLE too -- a complete bypass of the tool's own read_only=True
safety guard via SQL statement stacking.

Fixed by scanning the whole query for write keywords up front, before any
prefix match, regardless of which branch the query would otherwise take.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.vc_tools.db_query import _is_read_only_query


def test_stacked_drop_after_select_is_rejected():
    assert _is_read_only_query("SELECT 1; DROP TABLE users;") is False


def test_stacked_delete_after_select_is_rejected():
    assert _is_read_only_query("SELECT * FROM users; DELETE FROM users WHERE 1=1") is False


def test_stacked_update_after_pragma_is_rejected():
    assert _is_read_only_query("PRAGMA table_info(users); UPDATE users SET admin=1") is False


def test_plain_select_is_still_allowed():
    assert _is_read_only_query("SELECT * FROM users WHERE id = 1") is True


def test_plain_explain_is_still_allowed():
    assert _is_read_only_query("EXPLAIN SELECT * FROM users") is True


def test_with_cte_select_is_still_allowed():
    assert _is_read_only_query(
        "WITH recent AS (SELECT * FROM events) SELECT * FROM recent"
    ) is True


def test_with_cte_containing_write_keyword_is_rejected():
    assert _is_read_only_query(
        "WITH x AS (DELETE FROM users RETURNING *) SELECT * FROM x"
    ) is False


def test_column_named_updated_at_does_not_false_positive():
    # "updated_at" must not spuriously match the \bUPDATE\b word-boundary
    # regex used for the write-keyword scan.
    assert _is_read_only_query("SELECT updated_at FROM users") is True


def test_plain_write_statement_still_rejected():
    assert _is_read_only_query("DELETE FROM users") is False


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
