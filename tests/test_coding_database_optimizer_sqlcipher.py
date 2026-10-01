"""Regression: districts/coding/database_optimizer.py's analyze_schema() and
benchmark_queries() opened the main DB with a plain sqlite3.connect() instead
of core.memory.episodic.get_db_connection() (CLAUDE.md rule 7) -- with
SQLCipher active this fails outright (can't read an encrypted file as plain
SQLite), so the whole agent was non-functional. Fixed to use the shared
singleton connection (never closed here -- closing it would take down the
rest of VECTOR's memory access, same caution documented in
districts/data_analytics/data_engineer.py and districts/content/
blog_publisher.py for the identical shared connection).

Fixing the connection exposed a second, previously-unreachable bug: the
sqlcipher3 driver returns PRAGMA integers (page_size/page_count) as str,
not int, breaking the db_size_mb arithmetic -- the old code never got far
enough to hit this since the connection itself always failed first.
"""
from core.memory.episodic import get_db_connection
from districts.coding.database_optimizer import DatabaseOptimizer


def setup_module(module):
    # Under pytest, VECTOR_TEST_DATA_DIR points configured_db_path() at a
    # fresh, empty temp dir -- nothing has created vector_memory.db yet in
    # this isolated environment. get_db_connection() creates + initializes
    # the schema on first call (same as real production's first run);
    # calling it here first makes DatabaseOptimizer's own .exists() guard
    # pass, so the tests below actually exercise the fixed code path
    # instead of short-circuiting on "db not found".
    get_db_connection()


def test_analyze_schema_reads_real_encrypted_db():
    opt = DatabaseOptimizer()
    result = opt.analyze_schema()
    assert "error" not in result, result
    assert "tables" in result
    assert result["table_count"] > 0
    assert isinstance(result["db_size_mb"], float)
    assert "episodic_memory" in result["tables"]


def test_benchmark_queries_runs_against_real_encrypted_db():
    opt = DatabaseOptimizer()
    result = opt.benchmark_queries()
    assert "error" not in result, result
    assert "recent_events" in result
    assert "count_events" in result


def test_connection_is_never_closed_by_this_agent():
    """The connection is the shared episodic-memory singleton -- this agent
    must never close it, or it breaks every other caller for the rest of
    the process. Calling both methods twice in a row must not raise
    (would, if the first call closed the shared connection)."""
    opt = DatabaseOptimizer()
    opt.analyze_schema()
    opt.benchmark_queries()
    second = opt.analyze_schema()
    assert "error" not in second, second


if __name__ == "__main__":
    test_analyze_schema_reads_real_encrypted_db()
    test_benchmark_queries_runs_against_real_encrypted_db()
    test_connection_is_never_closed_by_this_agent()
    print("OK test_coding_database_optimizer_sqlcipher.py")
