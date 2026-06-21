"""Regression tests for core/queue/retry_queue.py — found 2026-06-21 during
the post-Phase-5 codebase audit, live in the wild: RetryQueue._conn() opened
the shared, possibly-SQLCipher-encrypted main DB with plain sqlite3.connect(),
raising "file is not a database" on every scheduler_loop tick (silently
swallowed, so Gap 4's retry-replay feature was dead with no crash to notice).
Same bug class as the 5 already-fixed modules (avatar_state.py etc.) per
phase_status.md's "SQLCipher access discipline" note — a 6th instance.
"""
import os
import tempfile
import unittest
from pathlib import Path


class TestRetryQueuePrivateConnection(unittest.TestCase):
    """Mirrors core/avatar/avatar_state.py's own test style: overriding the
    db_path to something other than the main configured DB exercises the
    private plain-sqlite3 branch, which always worked — this just proves it
    still works after the fix."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        import core.queue.retry_queue as mod
        self._mod = mod
        self._orig_instance = mod.RetryQueue._instance
        mod.RetryQueue._instance = None
        self._rq = mod.RetryQueue(db_path=Path(self._tmp.name))

    def tearDown(self):
        self._mod.RetryQueue._instance = self._orig_instance
        os.unlink(self._tmp.name)

    def test_push_and_pop_due_roundtrip(self):
        row_id = self._rq.push("test_action", {"x": 1}, proposed_by="test")
        self.assertIsInstance(row_id, int)
        # next_retry_at for attempt=0 is 1s in the future — not due yet.
        self.assertEqual(self._rq.pop_due(), [])

    def test_size_and_dlq_size_start_at_zero(self):
        self.assertEqual(self._rq.size(), 0)
        self.assertEqual(self._rq.dlq_size(), 0)

    def test_requeue_or_dlq_moves_to_dead_letter_after_max_attempts(self):
        from core.queue.retry_queue import RetryItem, _MAX_ATTEMPTS
        item = RetryItem(
            id=1, action_type="boom", params={}, proposed_by="test",
            attempt=_MAX_ATTEMPTS - 1, next_retry_at=0.0,
        )
        self._rq.requeue_or_dlq(item, "final failure")
        self.assertEqual(self._rq.dlq_size(), 1)
        self.assertEqual(self._rq.size(), 0)


class TestRetryQueueSharedConnectionBranch(unittest.TestCase):
    """The actual regression: when db_path equals the main configured DB
    (the real, default, no-override case — exactly what scheduler_loop hits
    in production), _conn() must route through episodic's SQLCipher-aware
    singleton, never raw sqlite3.connect(). Mocked rather than requiring a
    real SQLCipher-encrypted file in CI — matches the project's established
    test style for this exact bug class."""

    def test_conn_uses_shared_singleton_when_path_matches_main_db(self):
        """Real sqlite3.Connection stand-in (not a bare MagicMock) — proves
        both that get_db_connection() is the one called (not sqlite3.connect
        directly) AND that row_factory assignment doesn't crash, which is
        exactly the second bug this fix uncovered: sqlite3.Row can't wrap an
        sqlcipher3.dbapi2.Cursor, so row_factory must be derived from the
        connection's own driver module, not hardcoded."""
        import sqlite3 as _sqlite3
        import core.queue.retry_queue as mod
        from unittest.mock import patch

        rq = mod.RetryQueue.__new__(mod.RetryQueue)
        rq._db = str(mod.configured_db_path())  # no override — the real-world case

        fake_conn = _sqlite3.connect(":memory:")
        try:
            with patch("core.memory.episodic.get_db_connection", return_value=fake_conn) as get_conn, \
                 patch("sqlite3.connect") as raw_connect:
                conn, private = rq._conn()
                get_conn.assert_called_once()
                raw_connect.assert_not_called()
                self.assertIs(conn, fake_conn)
                self.assertFalse(private)
                self.assertIs(conn.row_factory, _sqlite3.Row)
        finally:
            fake_conn.close()

    def test_conn_uses_private_plain_sqlite_when_path_overridden(self):
        import core.queue.retry_queue as mod
        from unittest.mock import patch

        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        try:
            rq = mod.RetryQueue.__new__(mod.RetryQueue)
            rq._db = tmp.name  # differs from configured_db_path()

            with patch("core.memory.episodic.get_db_connection") as get_conn:
                conn, private = rq._conn()
                get_conn.assert_not_called()
                self.assertTrue(private)
                conn.close()
        finally:
            os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
