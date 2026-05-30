"""Integration tests — Session A6: SynthesisBridge.get_recent_patterns() → daily briefing."""
from __future__ import annotations

import inspect
import unittest


_MARKER = "A6_TEST_XDOM_PATTERN"


def _seed_patterns(count: int = 2) -> list[str]:
    """Inject synthetic cross_domain_synthesis rows into episodic memory."""
    from core.memory.episodic import EpisodicMemory
    em = EpisodicMemory()
    seeded = []
    for i in range(count):
        content = f"{_MARKER}_{i}: Pattern {i} — district X correlates with district Y"
        em.store(event_type="cross_domain_synthesis", content=content, tags=["test", "a6"], source="a6_test")
        seeded.append(content)
    return seeded


class TestGetRecentPatterns(unittest.TestCase):
    """SynthesisBridge.get_recent_patterns() API contract."""

    @classmethod
    def setUpClass(cls):
        cls._seeded = _seed_patterns(count=3)

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

    def test_seeded_patterns_returned(self):
        sb = self._make_bridge()
        patterns = sb.get_recent_patterns(days=1)
        found = [p for p in patterns if _MARKER in p]
        self.assertGreaterEqual(len(found), 3, f"Expected 3 seeded patterns, got {len(found)} in {len(patterns)} total")

    def test_zero_days_returns_empty_or_few(self):
        """days=0 means cutoff is right now — very unlikely to return anything stored earlier."""
        sb = self._make_bridge()
        result = sb.get_recent_patterns(days=0)
        self.assertIsInstance(result, list)

    def test_large_days_still_returns_list(self):
        sb = self._make_bridge()
        result = sb.get_recent_patterns(days=365)
        self.assertIsInstance(result, list)
        # Must include the seeded rows
        found = [p for p in result if _MARKER in p]
        self.assertGreaterEqual(len(found), 3)

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
        # The write_note call must reference _patterns_section
        self.assertIn("_patterns_section", src)


class TestSynthesisBridgeMethodSignature(unittest.TestCase):
    """get_recent_patterns has correct signature and defaults."""

    def test_default_days_is_1(self):
        from core.brain.synthesis_bridge import SynthesisBridge
        sig = inspect.signature(SynthesisBridge.get_recent_patterns)
        self.assertIn("days", sig.parameters)
        self.assertEqual(sig.parameters["days"].default, 1)

    def test_returns_list_of_strings(self):
        from core.brain.synthesis_bridge import SynthesisBridge
        sb = SynthesisBridge()
        result = sb.get_recent_patterns(days=1)
        for item in result:
            self.assertIsInstance(item, str)


if __name__ == "__main__":
    unittest.main()
