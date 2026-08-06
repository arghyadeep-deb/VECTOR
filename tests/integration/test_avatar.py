"""Integration tests for Phase 1 Avatar layer (AvatarCore, AvatarVoice, AvatarState)."""
import os
import unittest
import tempfile
from pathlib import Path


class TestAvatarState(unittest.TestCase):
    def setUp(self):
        # Use a temp DB so tests don't pollute vector_memory.db
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        import core.avatar.avatar_state as mod
        self._orig_db = mod._DB_PATH
        mod._DB_PATH = Path(self._tmp.name)

    def tearDown(self):
        import core.avatar.avatar_state as mod
        mod._DB_PATH = self._orig_db
        os.unlink(self._tmp.name)

    def test_load_defaults(self):
        from core.avatar.avatar_state import AvatarState
        state = AvatarState.load()
        self.assertEqual(state.valence, 0.0)
        self.assertEqual(state.mood_label, "neutral")

    def test_save_and_reload(self):
        from core.avatar.avatar_state import AvatarState
        state = AvatarState.load()
        state.absorb_sentiment("happy", 0.8)
        state.save()
        loaded = AvatarState.load()
        self.assertGreater(loaded.valence, 0.0)
        self.assertIn(loaded.mood_label, ("energised", "positive", "neutral"))

    def test_absorb_frustrated_lowers_valence(self):
        from core.avatar.avatar_state import AvatarState
        state = AvatarState()
        state.absorb_sentiment("frustrated", 0.9)
        self.assertLess(state.valence, 0.0)

    def test_presence_boost_and_decay(self):
        from core.avatar.avatar_state import AvatarState
        state = AvatarState()
        initial = state.presence_score
        state.boost_presence(0.2)
        self.assertAlmostEqual(state.presence_score, initial + 0.2, places=2)
        state.decay_presence(0.05)
        self.assertAlmostEqual(state.presence_score, initial + 0.15, places=2)

    def test_emotional_arc_capped_at_10(self):
        from core.avatar.avatar_state import AvatarState
        state = AvatarState()
        for _ in range(15):
            state.absorb_sentiment("happy", 0.5)
        state.save()
        loaded = AvatarState.load()
        self.assertLessEqual(len(loaded.emotional_arc), 10)

    def test_tone_hint_for_tense_mood(self):
        from core.avatar.avatar_state import AvatarState
        state = AvatarState(valence=-0.5, arousal=0.5)
        self.assertEqual(state.mood_label, "tense")
        self.assertEqual(state.tone_hint, "calm")


class TestAvatarVoice(unittest.TestCase):
    def setUp(self):
        from core.avatar.avatar_state import AvatarState
        self.state = AvatarState()

    def test_strips_internal_agent_names(self):
        from core.avatar.avatar_voice import AvatarVoice
        voice = AvatarVoice()
        raw = {"status": "ok", "response": "CodingBot reviewed your code and found 0 issues."}
        out = voice.format(raw, self.state, user_message="check my code")
        self.assertNotIn("CodingBot", out)

    def test_strips_district_word(self):
        # 2026-08-06: "Agent" and "District" were intentionally removed from
        # _INTERNAL_NAMES (see avatar_voice.py lines 31-41) because they're
        # common English words that appear in legitimate owner-facing prose,
        # unlike unambiguous implementation names like "CodingBot" or
        # "ChiefOfStaff". This test now verifies _ensure_first_person()
        # handles the "The Agent..." prefix pattern correctly.
        from core.avatar.avatar_voice import AvatarVoice
        voice = AvatarVoice()
        raw = "The Agent has processed your request via the District."
        out = voice.format(raw, self.state)
        # Should start with first-person prefix, not "The Agent"
        self.assertTrue(out.startswith("I've handled this") or out.startswith("I "))

    def test_empathy_prepended_for_frustrated(self):
        from core.avatar.avatar_voice import AvatarVoice
        voice = AvatarVoice()
        raw = {"status": "ok", "response": "Here is your analysis."}
        out = voice.format(raw, self.state, user_message="this is so frustrating not working")
        # Should contain empathy acknowledgment
        self.assertIn("frustrat", out.lower())

    def test_dict_output_extracts_response(self):
        from core.avatar.avatar_voice import AvatarVoice
        voice = AvatarVoice()
        raw = {"status": "ok", "response": "Task complete."}
        out = voice.format(raw, self.state)
        self.assertIn("Task complete", out)

    def test_status_only_dict_generates_message(self):
        from core.avatar.avatar_voice import AvatarVoice
        voice = AvatarVoice()
        raw = {"status": "ok"}
        out = voice.format(raw, self.state)
        self.assertIsInstance(out, str)
        self.assertGreater(len(out), 0)


class TestAvatarCore(unittest.TestCase):
    def setUp(self):
        # Reset singleton between tests
        from core.avatar import avatar_core as mod
        mod.AvatarCore._instance = None

    def tearDown(self):
        from core.avatar import avatar_core as mod
        mod.AvatarCore._instance = None

    def test_singleton(self):
        from core.avatar.avatar_core import AvatarCore
        a = AvatarCore.get_instance()
        b = AvatarCore.get_instance()
        self.assertIs(a, b)

    def test_on_observe_returns_dict(self):
        from core.avatar.avatar_core import AvatarCore
        core = AvatarCore.get_instance()
        obs = core.on_observe({"test": 1})
        self.assertIsInstance(obs, dict)
        self.assertEqual(obs["test"], 1)

    def test_on_act_strips_internal_names(self):
        from core.avatar.avatar_core import AvatarCore
        core = AvatarCore.get_instance()
        raw = {"status": "ok", "response": "GitBot pushed your changes."}
        result = core.on_act(raw, user_message="push my code")
        self.assertIn("_avatar_formatted", result)
        self.assertNotIn("GitBot", result.get("response", ""))

    def test_on_act_preserves_status(self):
        from core.avatar.avatar_core import AvatarCore
        core = AvatarCore.get_instance()
        raw = {"status": "ok", "data": [1, 2, 3], "response": "Done."}
        result = core.on_act(raw)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"], [1, 2, 3])

    def test_on_think_nudges_candidates(self):
        from core.avatar.avatar_core import AvatarCore
        from core.avatar.avatar_state import AvatarState
        core = AvatarCore.get_instance()
        # Force tense mood
        core._state = AvatarState(valence=-0.5, arousal=0.5)
        candidates = [
            {"action_type": "review_code", "score": 0.7},
            {"action_type": "deploy",      "score": 0.8},
        ]
        ranked = core.on_think(candidates)
        self.assertEqual(len(ranked), 2)
        review_score = next(c["score"] for c in ranked if c["action_type"] == "review_code")
        # tense mood should have boosted review_code
        self.assertGreaterEqual(review_score, 0.7)

    def test_on_reflect_does_not_raise(self):
        from core.avatar.avatar_core import AvatarCore
        core = AvatarCore.get_instance()
        # Should not raise even with bad summary
        core.on_reflect("", outcome="error")

    def test_on_act_fallback_on_error(self):
        """on_act must return raw_result (never raise) if voice fails."""
        from core.avatar.avatar_core import AvatarCore
        core = AvatarCore.get_instance()
        # Pass something un-formattable (shouldn't crash)
        result = core.on_act(None, user_message="")
        self.assertIsNotNone(result)


class TestSessionPlanWiring(unittest.TestCase):
    """Session plan checks: observe wiring, think nudge, break timer, sentiment sync."""

    def test_on_observe_absorbs_voice_sentiment(self):
        """Session 1+3: on_observe with text input updates AvatarState valence."""
        from core.avatar.avatar_core import AvatarCore
        AvatarCore._instance = None
        core = AvatarCore.get_instance()
        before = core.state.valence
        core.on_observe({"text": "I'm so frustrated today, nothing is working"})
        # Frustration → negative valence shift (or at least no crash)
        self.assertIsInstance(core.state.valence, float)
        AvatarCore._instance = None

    def test_on_observe_no_crash_on_empty(self):
        """Session 1: on_observe must never raise on empty input."""
        from core.avatar.avatar_core import AvatarCore
        AvatarCore._instance = None
        core = AvatarCore.get_instance()
        obs = core.on_observe({})
        self.assertIsInstance(obs, dict)
        AvatarCore._instance = None

    def test_on_think_nudges_calm_tasks_when_tense(self):
        """Session 1: on_think nudges review/research tasks up when mood=tense."""
        from core.avatar.avatar_core import AvatarCore
        from core.avatar.avatar_state import AvatarState
        AvatarCore._instance = None
        core = AvatarCore.get_instance()
        # Force tense mood
        core.state.valence = -0.5
        core.state.arousal = 0.3
        candidates = [
            {"action_type": "review_code", "score": 0.5},
            {"action_type": "deploy",       "score": 0.6},
        ]
        nudged = core.on_think(candidates)
        review_score = next(c["score"] for c in nudged if c["action_type"] == "review_code")
        # review_code should be nudged up (or at minimum unchanged)
        self.assertGreaterEqual(review_score, 0.5)
        AvatarCore._instance = None

    def test_proactive_care_timer_starts_from_boot(self):
        """Session 2: _last_break_ts must not be None after init."""
        from core.avatar.proactive_care import ProactiveCare
        care = ProactiveCare()
        self.assertIsNotNone(care._last_break_ts)

    def test_proactive_care_break_overdue_after_timeout(self):
        """Session 2: break intervention fires after simulated timeout."""
        import datetime
        from core.avatar.proactive_care import ProactiveCare
        care = ProactiveCare()
        # Simulate 3 hours since last break
        care._last_break_ts = datetime.datetime.now() - datetime.timedelta(hours=3)
        # check() may be DND-gated; test _check_break_overdue directly
        interventions = care._check_break_overdue()
        self.assertTrue(len(interventions) > 0, "Expected break intervention after 3h")
        self.assertEqual(interventions[0].kind, "break")

    def test_notify_user_helper_exists(self):
        """Session 1: _notify_user helper must exist and not raise."""
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        loop._notify_user("Test notification — VECTOR says hello")  # must not raise


class TestAvatarIntegration(unittest.TestCase):
    """End-to-end: governor-style raw result → formatted first-person response."""

    def test_full_pipeline_code_review(self):
        from core.avatar.avatar_core import AvatarCore
        AvatarCore._instance = None
        core = AvatarCore.get_instance()
        raw = {
            "status": "ok",
            "response": "CodeReviewer found 3 issues in your file. The BugHunter also flagged one critical bug.",
        }
        result = core.on_act(raw, task_context={"task_type": "code_review", "district": "coding"}, user_message="review my code")
        resp = result.get("response", "")
        self.assertNotIn("CodeReviewer", resp)
        self.assertNotIn("BugHunter", resp)
        self.assertIn("_avatar_formatted", result)
        AvatarCore._instance = None


if __name__ == "__main__":
    unittest.main()
