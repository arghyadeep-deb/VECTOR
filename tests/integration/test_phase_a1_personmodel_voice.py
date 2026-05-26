"""Integration tests — Session A1: PersonModel style → PersonalityLayer injection."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestPersonModelStyleInference(unittest.TestCase):
    """PersonModel.infer_communication_style() returns correct shape."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        from core.brain.person_model import PersonModel
        self.pm = PersonModel(db_path=self._tmp.name)
        self.pm.add_person("alice", "Alice", relationship_type="friend")

    def tearDown(self):
        self.pm.close()
        Path(self._tmp.name).unlink(missing_ok=True)

    def test_style_keys_present(self):
        style = self.pm.infer_communication_style("alice")
        for key in ("formality", "verbosity", "technicality", "directness"):
            self.assertIn(key, style)

    def test_style_values_are_valid(self):
        style = self.pm.infer_communication_style("alice")
        valid = {"low", "medium", "high"}
        for key, val in style.items():
            self.assertIn(val, valid, f"{key}={val!r} is not a valid style level")

    def test_preference_respected(self):
        self.pm.update_preference("alice", "formality", "high")
        self.pm.update_preference("alice", "directness", "low")
        style = self.pm.infer_communication_style("alice")
        self.assertEqual(style["formality"], "high")
        self.assertEqual(style["directness"], "low")

    def test_unknown_person_returns_defaults(self):
        style = self.pm.infer_communication_style("nobody_xyz")
        for key in ("formality", "verbosity", "technicality", "directness"):
            self.assertIn(key, style)
            self.assertEqual(style[key], "medium")


class TestPersonalityLayerPersonId(unittest.TestCase):
    """PersonalityLayer.inject() adapts system prompt when person_id is given."""

    def _make_layer(self):
        from core.personality.middleware import PersonalityLayer
        return PersonalityLayer()

    def test_inject_no_person_id_still_works(self):
        layer = self._make_layer()
        msgs = [{"role": "user", "content": "Hello"}]
        out = layer.inject(msgs)
        self.assertIsInstance(out, list)
        self.assertGreater(len(out), 0)

    def test_inject_with_person_id_returns_list(self):
        layer = self._make_layer()
        msgs = [{"role": "user", "content": "Hello"}]
        out = layer.inject(msgs, person_id="owner")
        self.assertIsInstance(out, list)
        self.assertGreater(len(out), 0)

    def test_inject_high_formality_adds_rule(self):
        """System prompt must contain formalisation rule when formality=high."""
        import tempfile
        from core.brain.person_model import PersonModel
        from core.personality.middleware import PersonalityLayer

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            pm = PersonModel(db_path=db)
            pm.add_person("formal_user", "Formal User")
            pm.update_preference("formal_user", "formality", "high")
            pm.close()

            layer = PersonalityLayer()
            msgs = [{"role": "user", "content": "Explain transformers"}]
            out = layer.inject(msgs, person_id="formal_user")
            system_content = " ".join(
                m["content"] for m in out if m.get("role") == "system"
            )
            self.assertIn("formal", system_content.lower())
        finally:
            Path(db).unlink(missing_ok=True)

    def test_style_suffix_returns_empty_for_all_medium(self):
        """When all style values are medium, no personalisation suffix is added."""
        import tempfile
        from core.brain.person_model import PersonModel
        from core.personality.middleware import PersonalityLayer

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            pm = PersonModel(db_path=db)
            pm.add_person("mid_user", "Mid User")
            # all defaults are "medium" — no rules should be appended
            pm.close()

            layer = PersonalityLayer()
            suffix = layer._style_suffix("mid_user")
            self.assertEqual(suffix, "")
        finally:
            Path(db).unlink(missing_ok=True)


class TestProviderClientPersonIdParam(unittest.TestCase):
    """ProviderClient.chat() accepts person_id without raising."""

    def test_chat_signature_has_person_id(self):
        import inspect
        from core.inference.provider_client import ProviderClient
        sig = inspect.signature(ProviderClient.chat)
        self.assertIn("person_id", sig.parameters)

    def test_person_id_defaults_to_none(self):
        import inspect
        from core.inference.provider_client import ProviderClient
        sig = inspect.signature(ProviderClient.chat)
        self.assertIsNone(sig.parameters["person_id"].default)


class TestAutonomousLoopHandleUserInput(unittest.TestCase):
    """_handle_user_input exists, stores person_id, returns it."""

    def setUp(self):
        from core.loop.autonomous_loop import AutonomousLoop
        self.loop = AutonomousLoop()

    def test_method_exists(self):
        self.assertTrue(hasattr(self.loop, "_handle_user_input"))

    def test_returns_owner_by_default(self):
        result = self.loop._handle_user_input("Hello VECTOR")
        self.assertEqual(result, "owner")

    def test_custom_person_id_returned(self):
        result = self.loop._handle_user_input("Hi", person_id="alice")
        self.assertEqual(result, "alice")

    def test_stores_current_person_id(self):
        self.loop._handle_user_input("Test", person_id="bob")
        self.assertEqual(self.loop._current_person_id, "bob")

    def test_empty_text_does_not_raise(self):
        result = self.loop._handle_user_input("")
        self.assertEqual(result, "owner")


if __name__ == "__main__":
    unittest.main()
