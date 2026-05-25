"""Integration tests for Phase 4 Science layer and CausalReasoner."""
import sys
import math
import asyncio
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestPhysicsEngine(unittest.TestCase):
    def setUp(self):
        from core.science.physics_engine import PhysicsEngine
        self.eng = PhysicsEngine()

    def test_projectile_returns_dict(self):
        r = self.eng.simulate_projectile(20.0, 45.0)
        self.assertIn("landing_distance_m", r)
        self.assertIn("max_height_m", r)
        self.assertGreater(r["landing_distance_m"], 0)

    def test_projectile_45_deg_optimal(self):
        r30 = self.eng.simulate_projectile(20.0, 30.0)
        r45 = self.eng.simulate_projectile(20.0, 45.0)
        r60 = self.eng.simulate_projectile(20.0, 60.0)
        # 45 degrees gives max range
        self.assertGreater(r45["landing_distance_m"], r30["landing_distance_m"])
        self.assertGreater(r45["landing_distance_m"], r60["landing_distance_m"])

    def test_pendulum_period_formula(self):
        r = self.eng.simulate_pendulum(1.0, 10.0)
        self.assertIn("period_s", r)
        expected = 2 * math.pi * math.sqrt(1.0 / 9.81)
        self.assertAlmostEqual(r["period_s"], expected, delta=0.01)

    def test_pendulum_trajectory_non_empty(self):
        r = self.eng.simulate_pendulum(1.0, 5.0)
        self.assertIn("trajectory", r)
        self.assertGreater(len(r["trajectory"]), 0)

    def test_degradation_never_raises(self):
        # Even with invalid inputs, must not raise
        r = self.eng.simulate_projectile(-1.0, 200.0)
        self.assertIsInstance(r, dict)

    def test_get_capabilities(self):
        caps = self.eng.get_capabilities()
        self.assertIn("mode", caps)
        self.assertIn(caps["mode"], ("pybullet", "analytical"))


class TestChemistryEngine(unittest.TestCase):
    def setUp(self):
        from core.science.chemistry_engine import ChemistryEngine
        self.eng = ChemistryEngine()

    def test_water_is_valid(self):
        r = self.eng.analyze_molecule("O")
        self.assertIn("valid", r)
        self.assertTrue(r["valid"])

    def test_returns_molecular_weight(self):
        r = self.eng.analyze_molecule("CC(=O)O")  # acetic acid
        self.assertIn("molecular_weight", r)
        self.assertGreater(r["molecular_weight"], 0)

    def test_empty_smiles_handled(self):
        r = self.eng.analyze_molecule("")
        self.assertIsInstance(r, dict)

    def test_method_field_present(self):
        r = self.eng.analyze_molecule("C")
        self.assertIn("method", r)

    def test_get_capabilities(self):
        caps = self.eng.get_capabilities()
        self.assertIn("rdkit_available", caps)
        self.assertIn("mode", caps)


class TestCADEngine(unittest.TestCase):
    def setUp(self):
        from core.science.cad_engine import CADEngine
        self.eng = CADEngine()

    def test_box_volume(self):
        r = self.eng.analyze_box(3.0, 4.0, 5.0)
        self.assertAlmostEqual(r["volume"], 60.0, places=2)

    def test_box_surface_area(self):
        r = self.eng.analyze_box(3.0, 4.0, 5.0)
        self.assertAlmostEqual(r["surface_area"], 94.0, places=2)

    def test_box_diagonal(self):
        r = self.eng.analyze_box(3.0, 4.0, 5.0)
        expected = math.sqrt(3**2 + 4**2 + 5**2)
        self.assertAlmostEqual(r["diagonal"], expected, places=3)

    def test_cylinder_volume(self):
        r = self.eng.analyze_cylinder(2.0, 5.0)
        expected = math.pi * 4 * 5
        self.assertAlmostEqual(r["volume"], expected, places=2)

    def test_sphere_volume(self):
        r = self.eng.analyze_sphere(3.0)
        expected = (4/3) * math.pi * 27
        self.assertAlmostEqual(r["volume"], expected, places=2)

    def test_get_capabilities(self):
        caps = self.eng.get_capabilities()
        self.assertIn("shapes", caps)
        self.assertIn("box", caps["shapes"])


class TestCausalReasoner(unittest.TestCase):
    def setUp(self):
        from core.causal.causal_reasoner import CausalReasoner
        self.cr = CausalReasoner()

    def test_explain_returns_dict(self):
        r = self.cr.explain("outcome:ok")
        self.assertIsInstance(r, dict)
        self.assertIn("causes", r)

    def test_explain_causes_is_list(self):
        r = self.cr.explain("nonexistent_node")
        self.assertIsInstance(r["causes"], list)

    def test_what_if_returns_dict(self):
        r = self.cr.what_if("deploy", "run_tests_first")
        self.assertIsInstance(r, dict)
        self.assertIn("action", r)

    def test_estimate_effect_graph_heuristic(self):
        r = self.cr.estimate_effect("action:code_review", "outcome:ok")
        self.assertIsInstance(r, dict)
        self.assertIn("ate", r)
        self.assertIn("method", r)

    def test_estimate_effect_no_data_no_crash(self):
        r = self.cr.estimate_effect("x", "y", data=None)
        self.assertIsInstance(r, dict)

    def test_never_raises_on_bad_input(self):
        r = self.cr.explain(None)
        self.assertIsInstance(r, dict)


class TestScienceAgent(unittest.TestCase):
    def setUp(self):
        from districts.science.science_agent import ScienceAgent
        self.agent = ScienceAgent()

    def test_physics_task(self):
        task = {"type": "physics", "params": {"simulation": "projectile", "velocity": 15.0, "angle_deg": 30.0}}
        result = asyncio.run(self.agent.run(task))
        self.assertEqual(result["status"], "ok")
        self.assertIn("result", result)
        self.assertGreater(result["result"]["landing_distance_m"], 0)

    def test_chemistry_task(self):
        task = {"type": "chemistry", "params": {"smiles": "O"}}
        result = asyncio.run(self.agent.run(task))
        self.assertEqual(result["status"], "ok")

    def test_chemistry_missing_smiles(self):
        task = {"type": "chemistry", "params": {}}
        result = asyncio.run(self.agent.run(task))
        self.assertEqual(result["status"], "error")

    def test_cad_box_task(self):
        task = {"type": "cad", "params": {"shape": "box", "length": 2.0, "width": 3.0, "height": 4.0}}
        result = asyncio.run(self.agent.run(task))
        self.assertEqual(result["status"], "ok")
        self.assertAlmostEqual(result["result"]["volume"], 24.0, places=2)

    def test_causal_query_task(self):
        task = {"type": "causal_query", "params": {"mode": "explain", "node": "outcome:ok"}}
        result = asyncio.run(self.agent.run(task))
        self.assertEqual(result["status"], "ok")

    def test_general_science_capabilities(self):
        task = {"type": "science", "params": {}}
        result = asyncio.run(self.agent.run(task))
        self.assertEqual(result["status"], "ok")
        self.assertIn("capabilities", result)

    def test_unknown_task_handled(self):
        task = {"type": "teleport", "params": {}}
        result = asyncio.run(self.agent.run(task))
        self.assertIn("status", result)

    def test_pendulum_physics(self):
        task = {"type": "physics", "params": {"simulation": "pendulum", "length_m": 1.0}}
        result = asyncio.run(self.agent.run(task))
        self.assertEqual(result["status"], "ok")
        self.assertIn("period_s", result["result"])

    def test_avatar_voice_formats_science_output(self):
        """Session 4: science output must pass through AvatarVoice — no internal names leaked."""
        from core.avatar.avatar_core import AvatarCore
        task = {"type": "physics", "params": {"simulation": "projectile", "velocity": 20.0, "angle_deg": 45.0}}
        raw = asyncio.run(self.agent.run(task))
        avatar = AvatarCore.get_instance()
        wrapped = avatar.on_act(raw, task_context={"task_type": "physics", "district": "science"},
                                user_message="If I drop this from 5m will it break?")
        # Avatar must mark the result as formatted
        self.assertIn("_avatar_formatted", wrapped)
        response = wrapped.get("response", "")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 0)
        # No internal bot/engine names must leak through AvatarVoice
        for bad in ("ScienceAgent", "ScienceBot", "PhysicsEngine", "CADEngine", "ChemistryEngine"):
            self.assertNotIn(bad, response)


class TestVADSentiment(unittest.TestCase):
    """Test Phase 2A — VAD properties on SentimentResult."""

    def test_happy_valence_positive(self):
        from core.personality.sentiment import SentimentResult
        r = SentimentResult(emotion="happy", intensity=0.8, urgency=0.0, confidence=0.8)
        self.assertGreater(r.valence, 0)
        self.assertGreater(r.arousal, 0)

    def test_frustrated_valence_negative(self):
        from core.personality.sentiment import SentimentResult
        r = SentimentResult(emotion="frustrated", intensity=0.9, urgency=0.0, confidence=0.9)
        self.assertLess(r.valence, 0)
        self.assertGreater(r.arousal, 0)

    def test_neutral_vad_zero(self):
        from core.personality.sentiment import SentimentResult
        r = SentimentResult(emotion="neutral", intensity=0.0, urgency=0.0, confidence=0.5)
        self.assertAlmostEqual(r.valence, 0.0)
        self.assertAlmostEqual(r.arousal, 0.0)

    def test_vad_tuple_length(self):
        from core.personality.sentiment import SentimentResult
        r = SentimentResult(emotion="curious", intensity=0.5, urgency=0.0, confidence=0.6)
        self.assertEqual(len(r.vad), 3)

    def test_unknown_emotion_defaults_to_zero(self):
        from core.personality.sentiment import SentimentResult
        r = SentimentResult(emotion="confused", intensity=0.5, urgency=0.0, confidence=0.5)
        self.assertEqual(r.valence, 0.0)

    def test_intensity_scales_vad(self):
        from core.personality.sentiment import SentimentResult
        r_low  = SentimentResult(emotion="happy", intensity=0.2, confidence=0.7)
        r_high = SentimentResult(emotion="happy", intensity=0.9, confidence=0.9)
        self.assertLess(abs(r_low.valence), abs(r_high.valence))

    def test_label_still_works(self):
        from core.personality.sentiment import SentimentResult
        r = SentimentResult(emotion="happy", intensity=0.5, urgency=0.8, confidence=0.8)
        self.assertIn("urgent", r.label)


class TestProactiveCare(unittest.TestCase):
    def test_check_returns_list(self):
        from core.avatar.proactive_care import ProactiveCare
        care = ProactiveCare()
        result = care.check()
        self.assertIsInstance(result, list)

    def test_record_break_resets_timer(self):
        import datetime
        from core.avatar.proactive_care import ProactiveCare
        care = ProactiveCare()
        care.record_break()
        self.assertIsNotNone(care._last_break_ts)
        self.assertLessEqual(
            (datetime.datetime.now() - care._last_break_ts).total_seconds(), 2.0
        )

    def test_intervention_dataclass(self):
        from core.avatar.proactive_care import Intervention
        iv = Intervention(kind="break", message="Rest", severity=0.5, source="test")
        self.assertEqual(iv.kind, "break")
        self.assertEqual(iv.severity, 0.5)

    def test_never_raises_on_broken_monitors(self):
        from core.avatar.proactive_care import ProactiveCare
        care = ProactiveCare()
        care._health_monitor = object()   # broken object, no methods
        result = care.check()
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
