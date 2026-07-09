"""Integration tests — Session A6: SynthesisBridge.get_recent_patterns() → daily briefing.

Rewritten 2026-07-08: the original version seeded marker rows with source="a6_test" and
asserted they APPEARED in get_recent_patterns(). Those rows leaked into the owner's real
nightly reflections (the "A6_TEST_XDOM_PATTERN" placeholder-journal bug). The contract is
now the opposite: test-sourced rows must be EXCLUDED from briefings, and all seeded rows
are cleaned up in tearDownClass.
"""
from __future__ import annotations

import inspect
import unittest


_MARKER = "A6_TEST_XDOM_PATTERN"
_TEST_SOURCE = "a6_test"      # contains "test" → must be filtered out of briefings
_PROBE_SOURCE = "a6_probe"    # production-like source → must be included


def _seed(count: int, source: str) -> list[str]:
    """Inject synthetic cross_domain_synthesis rows into episodic memory."""
    from core.memory.episodic import EpisodicMemory
    em = EpisodicMemory()
    seeded = []
    for i in range(count):
        content = f"{_MARKER}_{source}_{i}: Pattern {i} — district X correlates with district Y"
        em.store(event_type="cross_domain_synthesis", content=content, tags=["test", "a6"], source=source)
        seeded.append(content)
    return seeded


def _cleanup_seeded_rows() -> None:
    """Delete every row this module ever seeded (marker-matched), main + FTS tables."""
    from core.memory.episodic import EpisodicMemory
    em = EpisodicMemory()
    for table in ("episodic_memory", "episodic_memory_fts"):
        try:
            em.conn.execute(f"DELETE FROM {table} WHERE content LIKE ?", (f"%{_MARKER}%",))
        except Exception:
            pass
    try:
        em.conn.commit()
    except Exception:
        pass


class TestGetRecentPatterns(unittest.TestCase):
    """SynthesisBridge.get_recent_patterns() API contract + test-row exclusion."""

    @classmethod
    def setUpClass(cls):
        _cleanup_seeded_rows()  # remove residue from any previous run
        cls._test_rows = _seed(count=3, source=_TEST_SOURCE)
        cls._probe_rows = _seed(count=2, source=_PROBE_SOURCE)

    @classmethod
    def tearDownClass(cls):
        _cleanup_seeded_rows()

    def _make_bridge(self):
        from core.brain.synthesis_bridge import SynthesisBridge
        return SynthesisBridge()

    def test_method_exists(self):
        sb = self._make_bridge()
        self.assertTrue(hasattr(sb, "get_recent_patterns"))

    def test_returns_list(self):
        sb = self._make_bridge()
        result = sb.get_recent_patterns(days=1)
        self.assertIsInstance(result, list)

    def test_test_sourced_rows_excluded(self):
        """REGRESSION (2026-07-08): rows with a test source must never reach briefings."""
        sb = self._make_bridge()
        patterns = sb.get_recent_patterns(days=1)
        leaked = [p for p in patterns if _TEST_SOURCE in p]
        self.assertEqual(len(leaked), 0, f"test-sourced rows leaked into briefing: {leaked}")

    def test_production_like_rows_returned(self):
        sb = self._make_bridge()
        patterns = sb.get_recent_patterns(days=1)
        found = [p for p in patterns if _PROBE_SOURCE in p]
        self.assertGreaterEqual(len(found), 2, f"Expected 2 probe patterns, got {len(found)} in {len(patterns)} total")

    def test_zero_days_returns_empty_or_few(self):
        """days=0 means cutoff is right now — very unlikely to return anything stored earlier."""
        sb = self._make_bridge()
        result = sb.get_recent_patterns(days=0)
        self.assertIsInstance(result, list)

    def test_large_days_still_returns_list(self):
        sb = self._make_bridge()
        result = sb.get_recent_patterns(days=365)
        self.assertIsInstance(result, list)
        found = [p for p in result if _PROBE_SOURCE in p]
        self.assertGreaterEqual(len(found), 2)

    def test_graceful_empty_when_no_patterns(self):
        """days=0 or fresh DB — must never raise, returns empty list."""
        sb = self._make_bridge()
        try:
            result = sb.get_recent_patterns(days=0)
        except Exception as e:
            self.fail(f"get_recent_patterns raised unexpectedly: {e}")
        self.assertIsInstance(result, list)


class TestDailyReviewerPatternWiring(unittest.TestCase):
    """daily_reviewer.review() source includes cross-domain pattern wiring."""

    def test_review_sources_synthesis_bridge(self):
        from districts.reflection.daily_reviewer import DailyReviewer
        src = inspect.getsource(DailyReviewer.review)
        self.assertIn("SynthesisBridge", src, "review() must import SynthesisBridge")

    def test_review_calls_get_recent_patterns(self):
        from districts.reflection.daily_reviewer import DailyReviewer
        src = inspect.getsource(DailyReviewer.review)
        self.assertIn("get_recent_patterns", src)

    def test_review_has_cross_domain_section_label(self):
        from districts.reflection.daily_reviewer import DailyReviewer
        src = inspect.getsource(DailyReviewer.review)
        self.assertIn("Cross-domain patterns", src)

    def test_patterns_section_injected_into_obsidian_content(self):
        """The _patterns_section variable must be in the write_note content arg."""
        from districts.reflection.daily_reviewer import DailyReviewer
        src = inspect.getsource(DailyReviewer.review)
        self.assertIn("_patterns_section", src)

    def test_fetch_today_excludes_test_sources(self):
        """REGRESSION (2026-07-08): the daily event fetch must filter test rows."""
        from districts.reflection.daily_reviewer import DailyReviewer
        src = inspect.getsource(DailyReviewer._fetch_today)
        self.assertIn("NOT LIKE '%test%'", src)


if __name__ == "__main__":
    unittest.main()
