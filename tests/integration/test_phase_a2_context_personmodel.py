"""Integration tests — Session A2: PersonModel deep context in session_hydration_prompt."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

_TEST_PID = "_a2_test_alice_ctx"
_TEST_PID2 = "_a2_test_bob_ctx"


def _setup_test_persons():
    """Add test persons to the default PersonModel DB; return PersonModel."""
    from core.brain.person_model import PersonModel
    pm = PersonModel()
    pm.add_person(_TEST_PID, "Alice", relationship_type="colleague")
    pm.update_preference(_TEST_PID, "formality", "high")
    pm.update_preference(_TEST_PID, "technicality", "high")
    pm.update_trust(_TEST_PID, 0.35)  # set to 0.85
    pm.record_interaction(_TEST_PID, "Discussed VECTOR architecture", "positive", "voice")
    pm.add_person(_TEST_PID2, "Bob", relationship_type="friend")
    pm.update_preference(_TEST_PID2, "formality", "low")
    return pm


def _cleanup_test_persons():
    from core.brain.person_model import PersonModel
    pm = PersonModel()
    for pid in (_TEST_PID, _TEST_PID2):
        try:
            pm._conn.execute("DELETE FROM persons WHERE id=?", (pid,))
            pm._conn.execute("DELETE FROM person_preferences WHERE person_id=?", (pid,))
            pm._conn.execute("DELETE FROM person_interactions WHERE person_id=?", (pid,))
            pm._conn.execute("DELETE FROM person_beliefs WHERE person_id=?", (pid,))
        except Exception:
            pass
    pm._conn.commit()
    pm.close()


class TestSessionHydrationPersonModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _setup_test_persons().close()

    @classmethod
    def tearDownClass(cls):
        _cleanup_test_persons()

    def _get_engine(self):
        from core.loop.context_engine import ContextEngine
        return ContextEngine()

    def test_prompt_without_person_id_no_about_block(self):
        """Without person_id, no 'About <name>:' block in hydration prompt."""
        engine = self._get_engine()
        prompt = engine.session_hydration_prompt()
        self.assertNotIn(f"About Alice", prompt)
        self.assertNotIn(f"About {_TEST_PID}", prompt)

    def test_prompt_with_person_id_contains_about_block(self):
        """With person_id=alice, prompt contains 'About Alice:' block."""
        engine = self._get_engine()
        prompt = engine.session_hydration_prompt({"person_id": _TEST_PID})
        self.assertIn("About Alice", prompt)

    def test_about_block_contains_trust(self):
        """About block must include trust score."""
        engine = self._get_engine()
        prompt = engine.session_hydration_prompt({"person_id": _TEST_PID})
        self.assertIn("trust=", prompt)

    def test_about_block_contains_style(self):
        """About block must include communication style (formality)."""
        engine = self._get_engine()
        prompt = engine.session_hydration_prompt({"person_id": _TEST_PID})
        self.assertIn("formality=high", prompt)

    def test_about_block_contains_expected_stance(self):
        """About block must include expected_stance prediction."""
        engine = self._get_engine()
        prompt = engine.session_hydration_prompt({"person_id": _TEST_PID})
        self.assertIn("expected_stance=", prompt)

    def test_about_block_contains_recent_topics(self):
        """About block must include recent_topics list."""
        engine = self._get_engine()
        prompt = engine.session_hydration_prompt({"person_id": _TEST_PID})
        self.assertIn("recent_topics=", prompt)

    def test_person_id_key_not_in_raw_output(self):
        """'person_id: <value>' must NOT appear as a raw line (it's a reserved key)."""
        engine = self._get_engine()
        prompt = engine.session_hydration_prompt({"person_id": _TEST_PID, "task": "review"})
        self.assertNotIn(f"person_id: {_TEST_PID}", prompt)

    def test_other_extra_context_keys_still_present(self):
        """Non-reserved extra_context keys are still emitted normally."""
        engine = self._get_engine()
        prompt = engine.session_hydration_prompt({"person_id": _TEST_PID, "task": "code_review"})
        self.assertIn("task: code_review", prompt)

    def test_unknown_person_id_does_not_crash(self):
        """Passing a non-existent person_id must not raise or crash."""
        engine = self._get_engine()
        prompt = engine.session_hydration_prompt({"person_id": "zzz_nobody_xyz"})
        self.assertIsInstance(prompt, str)
        self.assertIn("[END SESSION CONTEXT]", prompt)

    def test_prompt_longer_with_person_id(self):
        """Prompt with person_id for a known person is longer than without."""
        engine = self._get_engine()
        prompt_plain = engine.session_hydration_prompt()
        prompt_person = engine.session_hydration_prompt({"person_id": _TEST_PID})
        self.assertGreater(len(prompt_person), len(prompt_plain))


if __name__ == "__main__":
    unittest.main()
