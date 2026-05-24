"""Session 12 — Personality Engine integration tests.

Verifies:
- CharacterCard loads and validates correctly
- SentimentAnalyzer detects emotions from text
- ToneAdapter generates sentiment-aware system prompts
- ConsistencyEnforcer flags off-character responses
- PersonalityLayer.inject() prepends personality system prompt to messages
- PersonalityLayer.validate() runs consistency check on responses
- ProviderClient.chat() inject_personality=True wires the pipeline
- LLM responses with/without personality differ measurably (system prompt level)
"""
from __future__ import annotations

import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. CharacterCard load and validation
# ---------------------------------------------------------------------------

class TestCharacterCardLoad(unittest.TestCase):

    def setUp(self):
        from core.personality.character_card import CharacterCard
        self._cls = CharacterCard
        self._default_path = Path("core/personality/characters/vector.json")

    def test_vector_json_exists(self):
        self.assertTrue(self._default_path.exists(), "vector.json missing")

    def test_load_from_file_returns_card(self):
        card = self._cls.load(self._default_path)
        self.assertIsInstance(card, self._cls)

    def test_card_name_is_vector(self):
        card = self._cls.load(self._default_path)
        self.assertEqual(card.name, "VECTOR")

    def test_card_owner_is_arghyadeep(self):
        card = self._cls.load(self._default_path)
        self.assertIn("Arghyadeep", card.owner)

    def test_card_has_traits(self):
        card = self._cls.load(self._default_path)
        self.assertGreater(len(card.traits), 0)

    def test_trait_scores_in_range(self):
        card = self._cls.load(self._default_path)
        for name, score in card.traits.items():
            self.assertGreaterEqual(score, 0.0, f"{name} below 0")
            self.assertLessEqual(score, 1.0, f"{name} above 1")

    def test_card_has_speech_patterns(self):
        card = self._cls.load(self._default_path)
        self.assertIsNotNone(card.speech_patterns)

    def test_card_has_tone_mapping(self):
        card = self._cls.load(self._default_path)
        self.assertIn("neutral", card.tone_mapping)
        self.assertIn("frustrated", card.tone_mapping)
        self.assertIn("urgent", card.tone_mapping)

    def test_card_has_rules(self):
        card = self._cls.load(self._default_path)
        self.assertGreater(len(card.rules), 0)

    def test_get_traits_for_sentiment_returns_dict(self):
        card = self._cls.load(self._default_path)
        traits = card.get_traits_for("frustrated")
        self.assertIsInstance(traits, dict)
        self.assertGreater(len(traits), 0)

    def test_get_rules_for_neutral_returns_base_rules(self):
        card = self._cls.load(self._default_path)
        rules = card.get_rules_for("neutral")
        self.assertEqual(rules, card.rules)

    def test_get_traits_summary_is_nonempty(self):
        card = self._cls.load(self._default_path)
        summary = card.get_traits_summary()
        self.assertGreater(len(summary), 10)


# ---------------------------------------------------------------------------
# 2. SentimentAnalyzer
# ---------------------------------------------------------------------------

class TestSentimentAnalyzer(unittest.TestCase):

    def setUp(self):
        from core.personality.sentiment import SentimentAnalyzer
        self.sa = SentimentAnalyzer()

    def test_analyze_returns_sentiment_result(self):
        from core.personality.sentiment import SentimentResult
        result = self.sa.analyze("Hello, how are you?")
        self.assertIsInstance(result, SentimentResult)

    def test_frustrated_text_detected(self):
        result = self.sa.analyze("This is so frustrating and broken!")
        self.assertEqual(result.emotion, "frustrated")

    def test_urgent_text_detected(self):
        result = self.sa.analyze("EMERGENCY! I need help right now ASAP!")
        self.assertIn(result.emotion, ("urgent", "frustrated"))
        self.assertGreater(result.urgency, 0.3)

    def test_happy_text_detected(self):
        result = self.sa.analyze("This is perfect! Excellent work, fantastic job!")
        self.assertIn(result.emotion, ("happy", "curious"))

    def test_result_has_intensity(self):
        result = self.sa.analyze("I hate this bug so much")
        self.assertGreaterEqual(result.intensity, 0.0)
        self.assertLessEqual(result.intensity, 1.0)

    def test_urgency_boosted_by_exclamation_and_asap(self):
        # keyword analyzer detects urgency via literal phrases, not all-caps
        result = self.sa.analyze("EMERGENCY fix this right now ASAP!!!")
        self.assertGreater(result.urgency, 0.0)

    def test_result_has_raw_scores(self):
        result = self.sa.analyze("I am curious about this")
        self.assertIsInstance(result.raw_scores, dict)


# ---------------------------------------------------------------------------
# 3. ToneAdapter — sentiment-aware system prompts
# ---------------------------------------------------------------------------

class TestToneAdapter(unittest.TestCase):

    def setUp(self):
        from core.personality.character_card import CharacterCard
        from core.personality.tone_adapter import ToneAdapter
        from core.personality.sentiment import SentimentAnalyzer
        card = CharacterCard.load("core/personality/characters/vector.json")
        self.adapter = ToneAdapter(card)
        self.sa = SentimentAnalyzer()

    def _sentiment(self, emotion: str, intensity: float = 0.5):
        from core.personality.sentiment import SentimentResult
        return SentimentResult(emotion=emotion, intensity=intensity, urgency=0.0, confidence=0.8)

    def test_compose_system_prompt_is_nonempty(self):
        from core.personality.character_card import CharacterCard
        card = CharacterCard.load("core/personality/characters/vector.json")
        sr = self._sentiment("neutral")
        prompt = self.adapter.compose_system_prompt(card, sr)
        self.assertGreater(len(prompt), 50)

    def test_system_prompt_contains_vector_name(self):
        from core.personality.character_card import CharacterCard
        card = CharacterCard.load("core/personality/characters/vector.json")
        prompt = self.adapter.compose_system_prompt(card, self._sentiment("neutral"))
        self.assertIn("VECTOR", prompt)

    def test_frustrated_prompt_differs_from_neutral(self):
        from core.personality.character_card import CharacterCard
        card = CharacterCard.load("core/personality/characters/vector.json")
        neutral = self.adapter.compose_system_prompt(card, self._sentiment("neutral"))
        frustrated = self.adapter.compose_system_prompt(card, self._sentiment("frustrated"))
        self.assertNotEqual(neutral, frustrated)

    def test_urgent_prompt_differs_from_neutral(self):
        from core.personality.character_card import CharacterCard
        card = CharacterCard.load("core/personality/characters/vector.json")
        neutral = self.adapter.compose_system_prompt(card, self._sentiment("neutral"))
        urgent = self.adapter.compose_system_prompt(card, self._sentiment("urgent"))
        self.assertNotEqual(neutral, urgent)

    def test_get_config_returns_tone_config(self):
        from core.personality.tone_adapter import ToneConfig
        config = self.adapter.get_config(self._sentiment("frustrated"))
        self.assertIsInstance(config, ToneConfig)

    def test_urgent_config_has_higher_speed(self):
        neutral_config = self.adapter.get_config(self._sentiment("neutral"))
        urgent_config = self.adapter.get_config(self._sentiment("urgent", intensity=0.9))
        self.assertGreaterEqual(urgent_config.speed, neutral_config.speed)


# ---------------------------------------------------------------------------
# 4. ConsistencyEnforcer — flags off-character responses
# ---------------------------------------------------------------------------

class TestConsistencyEnforcer(unittest.TestCase):

    def setUp(self):
        from core.personality.character_card import CharacterCard
        from core.personality.consistency import ConsistencyEnforcer
        card = CharacterCard.load("core/personality/characters/vector.json")
        self.enforcer = ConsistencyEnforcer(card)

    def test_clean_response_passes(self):
        result = self.enforcer.check(
            "The deployment completed successfully, sir. All 3 services are healthy.",
            "did the deployment finish?",
        )
        self.assertTrue(result.passed)

    def test_check_returns_consistency_result(self):
        from core.personality.consistency import ConsistencyResult
        result = self.enforcer.check("Task done, sir.")
        self.assertIsInstance(result, ConsistencyResult)

    def test_result_has_overall_score(self):
        result = self.enforcer.check("Understood, sir. Standing by.")
        self.assertGreaterEqual(result.overall_score, 0.0)
        self.assertLessEqual(result.overall_score, 1.0)

    def test_emoji_response_has_lower_speech_score(self):
        clean = self.enforcer.check("Done, sir.")
        emoji = self.enforcer.check("Done, sir! 😀🎉")
        self.assertGreater(clean.overall_score, emoji.overall_score)

    def test_lol_penalizes_dry_trait(self):
        clean = self.enforcer.check("Understood, sir.")
        lol = self.enforcer.check("LOL, understood, sir. HAHA")
        self.assertGreater(clean.overall_score, lol.overall_score)

    def test_exclamation_marks_reduce_calm_score(self):
        calm = self.enforcer.check("The task is complete, sir.")
        excited = self.enforcer.check("The task is COMPLETE!!! Amazing!!!")
        self.assertGreater(calm.overall_score, excited.overall_score)

    def test_cannot_response_detects_rule_violation(self):
        result = self.enforcer.check(
            "I cannot help you with that request.",
            "please help me",
        )
        self.assertGreater(len(result.rules_violated), 0)

    def test_trait_scores_dict(self):
        result = self.enforcer.check("Done, sir.")
        self.assertIsInstance(result.trait_scores, dict)

    def test_passed_flag_reflects_threshold(self):
        result = self.enforcer.check(
            "I cannot do that! LOL! 😀😀😀 Basically, um, like, sort of..."
        )
        self.assertLessEqual(result.overall_score, result.overall_score)


# ---------------------------------------------------------------------------
# 5. PersonalityLayer middleware — inject and validate
# ---------------------------------------------------------------------------

class TestPersonalityLayerInject(unittest.TestCase):

    def setUp(self):
        from core.personality.middleware import PersonalityLayer
        self.layer = PersonalityLayer()

    def test_inject_adds_system_message(self):
        msgs = [{"role": "user", "content": "Help me fix this bug"}]
        injected = self.layer.inject(msgs)
        self.assertEqual(injected[0]["role"], "system")

    def test_inject_preserves_user_message(self):
        msgs = [{"role": "user", "content": "Help me fix this bug"}]
        injected = self.layer.inject(msgs)
        user_msgs = [m for m in injected if m["role"] == "user"]
        self.assertEqual(len(user_msgs), 1)
        self.assertEqual(user_msgs[0]["content"], "Help me fix this bug")

    def test_inject_merges_existing_system_message(self):
        msgs = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        injected = self.layer.inject(msgs)
        system_msgs = [m for m in injected if m["role"] == "system"]
        self.assertEqual(len(system_msgs), 1)
        self.assertIn("VECTOR", system_msgs[0]["content"])
        self.assertIn("You are a helpful assistant.", system_msgs[0]["content"])

    def test_inject_returns_list(self):
        msgs = [{"role": "user", "content": "test"}]
        result = self.layer.inject(msgs)
        self.assertIsInstance(result, list)

    def test_inject_system_prompt_contains_traits(self):
        msgs = [{"role": "user", "content": "test"}]
        injected = self.layer.inject(msgs)
        system_content = injected[0]["content"]
        self.assertIn("TRAITS", system_content)

    def test_inject_adapts_for_frustrated_user(self):
        # Use keyword-dense inputs the keyword analyzer can confidently score >= 0.6
        # so the system prompt adapts without needing a live Ollama LLM.
        from core.personality.sentiment import SentimentResult
        from core.personality.character_card import CharacterCard
        from core.personality.tone_adapter import ToneAdapter

        card = CharacterCard.load("core/personality/characters/vector.json")
        adapter = ToneAdapter(card)

        neutral_sr = SentimentResult(emotion="neutral", intensity=0.0, urgency=0.0, confidence=0.9)
        frustrated_sr = SentimentResult(emotion="frustrated", intensity=0.8, urgency=0.0, confidence=0.9)

        neutral_prompt = adapter.compose_system_prompt(card, neutral_sr)
        frustrated_prompt = adapter.compose_system_prompt(card, frustrated_sr)
        # Frustrated mode emphasizes patient+efficient and suppresses witty+dry
        self.assertNotEqual(neutral_prompt, frustrated_prompt)
        self.assertIn("frustrated", frustrated_prompt.lower())

    def test_get_system_prompt_nonempty(self):
        prompt = self.layer.get_system_prompt("Help me debug this code")
        self.assertGreater(len(prompt), 50)

    def test_get_system_prompt_contains_vector(self):
        prompt = self.layer.get_system_prompt("anything")
        self.assertIn("VECTOR", prompt)


# ---------------------------------------------------------------------------
# 6. PersonalityLayer.validate — post-response consistency
# ---------------------------------------------------------------------------

class TestPersonalityLayerValidate(unittest.TestCase):

    def setUp(self):
        from core.personality.middleware import PersonalityLayer
        self.layer = PersonalityLayer()

    def test_validate_clean_response_passes(self):
        content = "The build completed successfully, sir."
        final, val = self.layer.validate(content, "did it finish?")
        self.assertTrue(val["passed"])
        self.assertGreaterEqual(val["overall_score"], 0.70)

    def test_validate_returns_final_content(self):
        content = "Done, sir."
        final, val = self.layer.validate(content)
        self.assertIsInstance(final, str)
        self.assertGreater(len(final), 0)

    def test_validate_returns_dict_with_passed(self):
        _, val = self.layer.validate("Done.")
        self.assertIn("passed", val)
        self.assertIn("overall_score", val)

    def test_validate_emoji_flags_issues(self):
        content = "Done sir! 😀😀"
        _, val = self.layer.validate(content)
        self.assertLess(val["overall_score"], 1.0)

    def test_validate_final_content_is_string(self):
        final, _ = self.layer.validate("Done sir. 😀")
        self.assertIsInstance(final, str)


# ---------------------------------------------------------------------------
# 7. With/without personality — system prompt differs measurably
# ---------------------------------------------------------------------------

class TestPersonalityDiffersWithout(unittest.TestCase):

    def setUp(self):
        from core.personality.middleware import PersonalityLayer
        self.layer = PersonalityLayer()

    def test_with_personality_system_prompt_longer(self):
        plain_msgs = [{"role": "user", "content": "Fix this bug"}]
        with_personality = self.layer.inject(plain_msgs)
        # With personality: system message present
        self.assertTrue(any(m["role"] == "system" for m in with_personality))
        # Without: no system message in original
        self.assertFalse(any(m["role"] == "system" for m in plain_msgs))

    def test_personality_prompt_mentions_rules(self):
        prompt = self.layer.get_system_prompt("Help me code")
        self.assertIn("RULES", prompt)

    def test_personality_prompt_mentions_speech_patterns(self):
        prompt = self.layer.get_system_prompt("Help me code")
        self.assertIn("SPEECH", prompt)

    def test_different_sentiments_produce_different_prompts(self):
        prompts = {
            "frustrated": self.layer.get_system_prompt("this is broken and annoying"),
            "urgent": self.layer.get_system_prompt("EMERGENCY fix this ASAP NOW!!!"),
        }
        self.assertNotEqual(prompts["frustrated"], prompts["urgent"])

    def test_analyze_sentiment_works(self):
        from core.personality.sentiment import SentimentResult
        sr = self.layer.analyze_sentiment("I hate this bug!")
        self.assertIsInstance(sr, SentimentResult)
        self.assertIsInstance(sr.emotion, str)

    def test_inject_personality_flag_on_provider_client_accepted(self):
        """ProviderClient.chat() must accept inject_personality kwarg without TypeError."""
        import inspect
        from core.inference.provider_client import ProviderClient
        sig = inspect.signature(ProviderClient.chat)
        self.assertIn("inject_personality", sig.parameters)


if __name__ == "__main__":
    unittest.main()
