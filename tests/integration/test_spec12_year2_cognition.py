"""
Session 19 — Year 2 Cognition Integration Tests.
Tests for:
  - core/brain/person_model.py (Gap 7: theory of mind per person)
  - core/city/meta_cognition.py (Gap 8: bias detection + calibration)
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.brain.person_model import PersonModel
from core.city.meta_cognition import MetaCognition


def _tmp_db(suffix=".db") -> str:
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.close()
    return f.name


# ── PersonModel — CRUD ───────────────────────────────────────────────────────

class TestPersonModelCRUD(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.pm = PersonModel(self.db)

    def tearDown(self):
        self.pm.close()
        Path(self.db).unlink(missing_ok=True)

    def test_add_person_returns_dict(self):
        p = self.pm.add_person("alice", "Alice")
        self.assertIsInstance(p, dict)

    def test_add_person_required_keys(self):
        p = self.pm.add_person("alice", "Alice")
        for key in ("id", "name", "relationship_type", "trust_score"):
            self.assertIn(key, p)

    def test_add_person_id_matches(self):
        p = self.pm.add_person("bob", "Bob")
        self.assertEqual(p["id"], "bob")

    def test_invalid_relationship_defaults_unknown(self):
        p = self.pm.add_person("carol", "Carol", relationship_type="alien")
        self.assertEqual(p["relationship_type"], "unknown")

    def test_valid_relationship_owner(self):
        p = self.pm.add_person("owner1", "Owner", relationship_type="owner")
        self.assertEqual(p["relationship_type"], "owner")

    def test_trust_score_defaults_05(self):
        p = self.pm.add_person("dave", "Dave")
        self.assertAlmostEqual(p["trust_score"], 0.5)

    def test_email_stored(self):
        self.pm.add_person("eve", "Eve", email="eve@example.com")
        m = self.pm.get_model("eve")
        self.assertEqual(m["email"], "eve@example.com")

    def test_metadata_stored_as_dict(self):
        self.pm.add_person("frank", "Frank", metadata={"kiit": True})
        m = self.pm.get_model("frank")
        self.assertEqual(m["metadata"], {"kiit": True})

    def test_get_model_unknown_returns_none(self):
        result = self.pm.get_model("nobody")
        self.assertIsNone(result)

    def test_get_all_persons_returns_list(self):
        self.pm.add_person("g1", "G1")
        self.pm.add_person("g2", "G2")
        persons = self.pm.get_all_persons()
        self.assertIsInstance(persons, list)
        self.assertEqual(len(persons), 2)

    def test_person_exists_true(self):
        self.pm.add_person("hank", "Hank")
        self.assertTrue(self.pm.person_exists("hank"))

    def test_person_exists_false(self):
        self.assertFalse(self.pm.person_exists("ghost"))

    def test_duplicate_person_insert_replace(self):
        self.pm.add_person("ivan", "Ivan Old")
        self.pm.add_person("ivan", "Ivan New")
        persons = self.pm.get_all_persons()
        ivan_rows = [p for p in persons if p["id"] == "ivan"]
        self.assertEqual(len(ivan_rows), 1)

    def test_get_model_includes_beliefs_key(self):
        self.pm.add_person("julia", "Julia")
        m = self.pm.get_model("julia")
        self.assertIn("beliefs", m)

    def test_get_model_includes_preferences_key(self):
        self.pm.add_person("karl", "Karl")
        m = self.pm.get_model("karl")
        self.assertIn("preferences", m)

    def test_get_model_includes_recent_interactions_key(self):
        self.pm.add_person("laura", "Laura")
        m = self.pm.get_model("laura")
        self.assertIn("recent_interactions", m)


# ── PersonModel — Beliefs ────────────────────────────────────────────────────

class TestPersonModelBeliefs(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.pm = PersonModel(self.db)
        self.pm.add_person("p1", "Person One")

    def tearDown(self):
        self.pm.close()
        Path(self.db).unlink(missing_ok=True)

    def test_update_belief_returns_true(self):
        result = self.pm.update_belief("p1", "AI", "transformative", 0.9)
        self.assertTrue(result)

    def test_update_belief_unknown_person_returns_false(self):
        result = self.pm.update_belief("ghost", "AI", "transformative", 0.9)
        self.assertFalse(result)

    def test_confidence_clamped_above_1(self):
        self.pm.update_belief("p1", "climate", "urgent", 1.5)
        m = self.pm.get_model("p1")
        self.assertLessEqual(m["beliefs"]["climate"]["confidence"], 1.0)

    def test_confidence_clamped_below_0(self):
        self.pm.update_belief("p1", "topic", "belief", -0.5)
        m = self.pm.get_model("p1")
        self.assertGreaterEqual(m["beliefs"]["topic"]["confidence"], 0.0)

    def test_belief_visible_in_model(self):
        self.pm.update_belief("p1", "AI", "transformative", 0.9)
        m = self.pm.get_model("p1")
        self.assertIn("AI", m["beliefs"])
        self.assertEqual(m["beliefs"]["AI"]["belief"], "transformative")

    def test_same_topic_replaces_belief(self):
        self.pm.update_belief("p1", "AI", "useful", 0.6)
        self.pm.update_belief("p1", "AI", "transformative", 0.9)
        m = self.pm.get_model("p1")
        self.assertEqual(m["beliefs"]["AI"]["belief"], "transformative")

    def test_multiple_topics_coexist(self):
        self.pm.update_belief("p1", "AI", "transformative", 0.9)
        self.pm.update_belief("p1", "climate", "urgent", 0.8)
        m = self.pm.get_model("p1")
        self.assertIn("AI", m["beliefs"])
        self.assertIn("climate", m["beliefs"])

    def test_confidence_stored_correctly(self):
        self.pm.update_belief("p1", "AI", "transformative", 0.75)
        m = self.pm.get_model("p1")
        self.assertAlmostEqual(m["beliefs"]["AI"]["confidence"], 0.75)


# ── PersonModel — Preferences ────────────────────────────────────────────────

class TestPersonModelPreferences(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.pm = PersonModel(self.db)
        self.pm.add_person("p2", "Person Two")

    def tearDown(self):
        self.pm.close()
        Path(self.db).unlink(missing_ok=True)

    def test_update_preference_returns_true(self):
        result = self.pm.update_preference("p2", "formality", "low")
        self.assertTrue(result)

    def test_update_preference_unknown_person_returns_false(self):
        result = self.pm.update_preference("ghost", "formality", "low")
        self.assertFalse(result)

    def test_preference_visible_in_model(self):
        self.pm.update_preference("p2", "verbosity", "high")
        m = self.pm.get_model("p2")
        self.assertEqual(m["preferences"]["verbosity"], "high")

    def test_same_key_replaces_preference(self):
        self.pm.update_preference("p2", "formality", "low")
        self.pm.update_preference("p2", "formality", "high")
        m = self.pm.get_model("p2")
        self.assertEqual(m["preferences"]["formality"], "high")

    def test_multiple_pref_keys_coexist(self):
        self.pm.update_preference("p2", "formality", "low")
        self.pm.update_preference("p2", "verbosity", "medium")
        self.pm.update_preference("p2", "technicality", "high")
        m = self.pm.get_model("p2")
        self.assertEqual(len(m["preferences"]), 3)

    def test_preference_value_stored_correctly(self):
        self.pm.update_preference("p2", "directness", "medium")
        m = self.pm.get_model("p2")
        self.assertEqual(m["preferences"]["directness"], "medium")


# ── PersonModel — Interactions ───────────────────────────────────────────────

class TestPersonModelInteractions(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.pm = PersonModel(self.db)
        self.pm.add_person("p3", "Person Three")

    def tearDown(self):
        self.pm.close()
        Path(self.db).unlink(missing_ok=True)

    def test_record_interaction_returns_id(self):
        iid = self.pm.record_interaction("p3", "Discussed VECTOR roadmap", "positive", "cli")
        self.assertIsNotNone(iid)
        self.assertIsInstance(iid, str)

    def test_record_interaction_unknown_person_returns_none(self):
        result = self.pm.record_interaction("ghost", "Hello", "neutral", "cli")
        self.assertIsNone(result)

    def test_get_interaction_history_returns_list(self):
        self.pm.record_interaction("p3", "Meeting 1", "positive", "cli")
        history = self.pm.get_interaction_history("p3")
        self.assertIsInstance(history, list)
        self.assertEqual(len(history), 1)

    def test_get_interaction_history_limit(self):
        for i in range(8):
            self.pm.record_interaction("p3", f"Interaction {i}", "neutral", "cli")
        history = self.pm.get_interaction_history("p3", limit=3)
        self.assertEqual(len(history), 3)

    def test_sentiment_stored_correctly(self):
        self.pm.record_interaction("p3", "Bad day", "negative", "cli")
        history = self.pm.get_interaction_history("p3")
        self.assertEqual(history[0]["sentiment"], "negative")

    def test_channel_stored_correctly(self):
        self.pm.record_interaction("p3", "Chat msg", "neutral", "telegram")
        history = self.pm.get_interaction_history("p3")
        self.assertEqual(history[0]["channel"], "telegram")

    def test_get_model_recent_interactions_capped(self):
        for i in range(10):
            self.pm.record_interaction("p3", f"Interaction {i}", "neutral", "cli")
        m = self.pm.get_model("p3")
        self.assertLessEqual(len(m["recent_interactions"]), 5)

    def test_interaction_history_sorted_desc(self):
        self.pm.record_interaction("p3", "First", "positive", "cli")
        self.pm.record_interaction("p3", "Second", "negative", "cli")
        history = self.pm.get_interaction_history("p3")
        self.assertEqual(history[0]["summary"], "Second")


# ── PersonModel — Trust ──────────────────────────────────────────────────────

class TestPersonModelTrust(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.pm = PersonModel(self.db)
        self.pm.add_person("p4", "Person Four")

    def tearDown(self):
        self.pm.close()
        Path(self.db).unlink(missing_ok=True)

    def test_update_trust_increases(self):
        score = self.pm.update_trust("p4", 0.2)
        self.assertGreater(score, 0.5)

    def test_update_trust_decreases(self):
        score = self.pm.update_trust("p4", -0.2)
        self.assertLess(score, 0.5)

    def test_trust_clamped_at_one(self):
        score = self.pm.update_trust("p4", 2.0)
        self.assertAlmostEqual(score, 1.0)

    def test_trust_clamped_at_zero(self):
        score = self.pm.update_trust("p4", -2.0)
        self.assertAlmostEqual(score, 0.0)

    def test_get_trust_unknown_returns_05(self):
        t = self.pm.get_trust("ghost")
        self.assertAlmostEqual(t, 0.5)

    def test_update_trust_unknown_returns_05(self):
        t = self.pm.update_trust("ghost", 0.1)
        self.assertAlmostEqual(t, 0.5)


# ── PersonModel — Inference ──────────────────────────────────────────────────

class TestPersonModelInference(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.pm = PersonModel(self.db)
        self.pm.add_person("p5", "Person Five")

    def tearDown(self):
        self.pm.close()
        Path(self.db).unlink(missing_ok=True)

    def test_infer_style_returns_all_keys(self):
        style = self.pm.infer_communication_style("p5")
        for key in ("formality", "verbosity", "technicality", "directness"):
            self.assertIn(key, style)

    def test_formality_from_preferences(self):
        self.pm.update_preference("p5", "formality", "high")
        style = self.pm.infer_communication_style("p5")
        self.assertEqual(style["formality"], "high")

    def test_verbosity_from_preferences(self):
        self.pm.update_preference("p5", "verbosity", "low")
        style = self.pm.infer_communication_style("p5")
        self.assertEqual(style["verbosity"], "low")

    def test_defaults_to_medium_without_prefs(self):
        style = self.pm.infer_communication_style("p5")
        self.assertEqual(style["technicality"], "medium")

    def test_predict_response_returns_string(self):
        result = self.pm.predict_response("p5", "AI")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_predict_response_includes_belief_if_present(self):
        self.pm.update_belief("p5", "AI", "transformative", 0.9)
        result = self.pm.predict_response("p5", "AI")
        self.assertIn("transformative", result)

    def test_predict_response_stance_high_trust(self):
        self.pm.update_trust("p5", 0.3)  # takes to 0.8
        result = self.pm.predict_response("p5", "AI")
        self.assertIn("receptive", result)

    def test_predict_response_stance_low_trust(self):
        self.pm.update_trust("p5", -0.3)  # takes to 0.2
        result = self.pm.predict_response("p5", "AI")
        self.assertIn("sceptical", result)


# ── PersonModel — Summary ────────────────────────────────────────────────────

class TestPersonModelSummary(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.pm = PersonModel(self.db)

    def tearDown(self):
        self.pm.close()
        Path(self.db).unlink(missing_ok=True)

    def test_summary_total_persons(self):
        self.pm.add_person("s1", "S1", "owner")
        self.pm.add_person("s2", "S2", "colleague")
        s = self.pm.get_model_summary()
        self.assertEqual(s["total_persons"], 2)

    def test_summary_by_relationship_type(self):
        self.pm.add_person("s1", "S1", "owner")
        self.pm.add_person("s2", "S2", "owner")
        self.pm.add_person("s3", "S3", "colleague")
        s = self.pm.get_model_summary()
        self.assertEqual(s["by_relationship_type"]["owner"], 2)
        self.assertEqual(s["by_relationship_type"]["colleague"], 1)

    def test_summary_avg_trust(self):
        self.pm.add_person("s1", "S1")
        s = self.pm.get_model_summary()
        self.assertIn("avg_trust", s)
        self.assertAlmostEqual(s["avg_trust"], 0.5)


# ── MetaCognition — Core ─────────────────────────────────────────────────────

class TestMetaCognitionCore(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.mc = MetaCognition(self.db)

    def tearDown(self):
        self.mc.close()
        Path(self.db).unlink(missing_ok=True)

    def test_observe_persists_thought(self):
        self.mc.observe("Test thought", 0.8, "success", "coding")
        report = self.mc.get_self_report()
        self.assertEqual(report["total_thoughts"], 1)

    def test_get_self_report_avg_confidence(self):
        self.mc.observe("Thought A", 0.6)
        self.mc.observe("Thought B", 0.8)
        report = self.mc.get_self_report()
        self.assertAlmostEqual(report["avg_confidence"], 0.7, places=2)

    def test_detect_blind_spot_returns_entry(self):
        bs = self.mc.detect_blind_spot("Missed signal", "Some context")
        self.assertIsInstance(bs, dict)
        self.assertIn("missed_signal", bs)
        self.assertIn("id", bs)

    def test_detect_blind_spot_unresolved(self):
        bs = self.mc.detect_blind_spot("Missed signal", "context")
        self.assertFalse(bs["resolved"])

    def test_resolve_blind_spot_returns_true(self):
        self.mc.detect_blind_spot("Missed exam", "calendar gap")
        result = self.mc.resolve_blind_spot("Missed exam", "added watcher")
        self.assertTrue(result)

    def test_resolve_blind_spot_unknown_returns_false(self):
        result = self.mc.resolve_blind_spot("ghost signal", "irrelevant")
        self.assertFalse(result)

    def test_resolution_rate_computed(self):
        self.mc.detect_blind_spot("S1", "C1")
        self.mc.detect_blind_spot("S2", "C2")
        self.mc.resolve_blind_spot("S1", "fixed")
        report = self.mc.get_self_report()
        self.assertAlmostEqual(report["resolution_rate"], 0.5)

    def test_get_all_blind_spots_unresolved_filter(self):
        self.mc.detect_blind_spot("Open1", "ctx")
        self.mc.detect_blind_spot("Open2", "ctx")
        self.mc.resolve_blind_spot("Open1", "done")
        unresolved = self.mc.get_all_blind_spots(resolved=False)
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["missed_signal"], "Open2")


# ── MetaCognition — Calibration ──────────────────────────────────────────────

class TestMetaCognitionCalibration(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.mc = MetaCognition(self.db)

    def tearDown(self):
        self.mc.close()
        Path(self.db).unlink(missing_ok=True)

    def test_record_calibration_returns_id(self):
        cid = self.mc.record_calibration_error(0.8, True, "coding")
        self.assertIsInstance(cid, str)
        self.assertGreater(len(cid), 0)

    def test_calibration_report_total_samples(self):
        self.mc.record_calibration_error(0.9, False)
        self.mc.record_calibration_error(0.7, True)
        report = self.mc.get_calibration_report()
        self.assertEqual(report["total_samples"], 2)

    def test_calibration_report_empty_returns_zeros(self):
        report = self.mc.get_calibration_report()
        self.assertEqual(report["total_samples"], 0)
        self.assertAlmostEqual(report["calibration_error"], 0.0)

    def test_calibration_avg_predicted(self):
        self.mc.record_calibration_error(0.8, True)
        self.mc.record_calibration_error(0.6, True)
        report = self.mc.get_calibration_report()
        self.assertAlmostEqual(report["avg_predicted"], 0.7, places=2)

    def test_calibration_avg_actual(self):
        self.mc.record_calibration_error(0.8, True)
        self.mc.record_calibration_error(0.8, False)
        report = self.mc.get_calibration_report()
        self.assertAlmostEqual(report["avg_actual"], 0.5, places=2)

    def test_overconfidence_rate_detected(self):
        for _ in range(5):
            self.mc.record_calibration_error(0.95, False)
        report = self.mc.get_calibration_report()
        self.assertGreater(report["overconfidence_rate"], 0.0)

    def test_underconfidence_rate_detected(self):
        for _ in range(5):
            self.mc.record_calibration_error(0.2, True)
        report = self.mc.get_calibration_report()
        self.assertGreater(report["underconfidence_rate"], 0.0)

    def test_domain_filtered_report(self):
        self.mc.record_calibration_error(0.8, True, "coding")
        self.mc.record_calibration_error(0.7, False, "coding")
        self.mc.record_calibration_error(0.6, True, "finance")
        report = self.mc.get_calibration_report(domain="coding")
        self.assertEqual(report["total_samples"], 2)


# ── MetaCognition — Bias Detection ──────────────────────────────────────────

class TestMetaCognitionBiasDetection(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.mc = MetaCognition(self.db)

    def tearDown(self):
        self.mc.close()
        Path(self.db).unlink(missing_ok=True)

    def test_detect_bias_empty_list_returns_empty(self):
        biases = self.mc.detect_bias([])
        self.assertEqual(biases, [])

    def test_detect_bias_returns_list(self):
        samples = [{"thought": "T", "confidence": 0.8, "outcome": None, "domain": "general"}]
        biases = self.mc.detect_bias(samples)
        self.assertIsInstance(biases, list)

    def test_detect_bias_overconfidence_detected(self):
        samples = [
            {"thought": f"T{i}", "confidence": 0.9, "outcome": "failed", "domain": "coding"}
            for i in range(6)
        ]
        biases = self.mc.detect_bias(samples)
        bias_types = [b["bias_type"] for b in biases]
        self.assertIn("overconfidence", bias_types)

    def test_detect_bias_overconfidence_has_evidence(self):
        samples = [
            {"thought": f"T{i}", "confidence": 0.95, "outcome": "failed", "domain": "coding"}
            for i in range(6)
        ]
        biases = self.mc.detect_bias(samples)
        oc = [b for b in biases if b["bias_type"] == "overconfidence"]
        self.assertGreater(len(oc), 0)
        self.assertIn("evidence", oc[0])
        self.assertIn("recommendation", oc[0])

    def test_detect_bias_recency_bias(self):
        early = [
            {"thought": f"E{i}", "confidence": 0.3, "outcome": None, "domain": "general"}
            for i in range(8)
        ]
        recent = [
            {"thought": f"R{i}", "confidence": 0.9, "outcome": None, "domain": "general"}
            for i in range(4)
        ]
        biases = self.mc.detect_bias(early + recent)
        bias_types = [b["bias_type"] for b in biases]
        self.assertIn("recency", bias_types)

    def test_detect_bias_confirmation_bias(self):
        samples = [
            {"thought": f"T{i}", "confidence": 0.9, "outcome": None, "domain": "coding"}
            for i in range(7)
        ] + [
            {"thought": "other", "confidence": 0.4, "outcome": None, "domain": "finance"}
        ]
        biases = self.mc.detect_bias(samples)
        bias_types = [b["bias_type"] for b in biases]
        self.assertIn("confirmation", bias_types)

    def test_detect_bias_no_bias_when_calibrated(self):
        samples = [
            {"thought": f"T{i}", "confidence": 0.7,
             "outcome": "success" if i % 2 == 0 else "failed",
             "domain": "coding"}
            for i in range(6)
        ]
        biases = self.mc.detect_bias(samples)
        oc = [b for b in biases if b["bias_type"] == "overconfidence"]
        self.assertEqual(len(oc), 0)

    def test_detect_systematic_bias_insufficient_data(self):
        result = self.mc.detect_systematic_bias(window_days=30)
        self.assertIn("summary", result)
        self.assertIn("detected_biases", result)
        self.assertIn("Insufficient", result["summary"])

    def test_detect_systematic_bias_detects_overconfidence(self):
        for i in range(6):
            self.mc.observe(f"Thought {i}", 0.9, "failed", "coding")
        result = self.mc.detect_systematic_bias(window_days=30)
        bias_types = [b["bias_type"] for b in result["detected_biases"]]
        self.assertIn("overconfidence", bias_types)

    def test_detect_systematic_bias_domain_analysis_present(self):
        for i in range(6):
            self.mc.observe(f"T{i}", 0.8, "success", "finance")
        result = self.mc.detect_systematic_bias(window_days=30)
        self.assertIn("domain_analysis", result)
        if "finance" in result["domain_analysis"]:
            self.assertIn("avg_confidence", result["domain_analysis"]["finance"])


# ── MetaCognition — Monthly Report ──────────────────────────────────────────

class TestMetaCognitionMonthly(unittest.TestCase):
    def setUp(self):
        self.db = _tmp_db()
        self.mc = MetaCognition(self.db)

    def tearDown(self):
        self.mc.close()
        Path(self.db).unlink(missing_ok=True)

    def test_monthly_report_has_required_keys(self):
        report = self.mc.get_monthly_report()
        for key in ("thought_summary", "calibration", "bias_analysis", "recommendations",
                    "generated_at", "period_days"):
            self.assertIn(key, report)

    def test_monthly_report_period_is_30(self):
        report = self.mc.get_monthly_report()
        self.assertEqual(report["period_days"], 30)

    def test_monthly_report_generated_at_is_string(self):
        report = self.mc.get_monthly_report()
        self.assertIsInstance(report["generated_at"], str)

    def test_monthly_report_recommendations_overconfidence(self):
        for _ in range(5):
            self.mc.record_calibration_error(0.95, False)
        report = self.mc.get_monthly_report()
        self.assertIsInstance(report["recommendations"], list)
        rec_text = " ".join(report["recommendations"])
        self.assertIn("overconfidence", rec_text.lower())

    def test_monthly_report_blind_spots_counted(self):
        self.mc.detect_blind_spot("Signal A", "ctx")
        self.mc.detect_blind_spot("Signal B", "ctx")
        report = self.mc.get_monthly_report()
        self.assertGreaterEqual(report["new_blind_spots_30d"], 2)

    def test_monthly_report_domain_breakdown(self):
        self.mc.observe("Thought A", 0.7, None, "coding")
        self.mc.observe("Thought B", 0.8, None, "finance")
        report = self.mc.get_monthly_report()
        self.assertIn("domain_breakdown", report)


# ── Year 2 Cognition Integration ─────────────────────────────────────────────

class TestYear2CognitionIntegration(unittest.TestCase):
    def setUp(self):
        self.pm_db = _tmp_db()
        self.mc_db = _tmp_db()
        self.pm = PersonModel(self.pm_db)
        self.mc = MetaCognition(self.mc_db)

    def tearDown(self):
        self.pm.close()
        self.mc.close()
        Path(self.pm_db).unlink(missing_ok=True)
        Path(self.mc_db).unlink(missing_ok=True)

    def test_person_model_and_meta_cognition_independent(self):
        self.pm.add_person("arghyadeep", "Arghyadeep Deb", "owner")
        self.mc.observe("owner interaction", 0.9, "positive", "relationships")
        pm_summary = self.pm.get_model_summary()
        mc_report = self.mc.get_self_report()
        self.assertEqual(pm_summary["total_persons"], 1)
        self.assertEqual(mc_report["total_thoughts"], 1)

    def test_trust_and_calibration_correlated(self):
        self.pm.add_person("alice", "Alice", "colleague")
        self.pm.update_trust("alice", 0.3)
        trust = self.pm.get_trust("alice")
        self.mc.record_calibration_error(trust, True, "relationship")
        report = self.mc.get_calibration_report(domain="relationship")
        self.assertEqual(report["total_samples"], 1)
        self.assertAlmostEqual(report["avg_predicted"], round(trust, 3), places=2)

    def test_interaction_history_feeds_style_inference(self):
        self.pm.add_person("bob", "Bob", "colleague")
        self.pm.update_preference("bob", "formality", "high")
        self.pm.record_interaction("bob", "Formal meeting", "formal", "email")
        style = self.pm.infer_communication_style("bob")
        self.assertEqual(style["formality"], "high")

    def test_bias_detection_after_rich_observations(self):
        samples = [
            {"thought": f"Decision {i}", "confidence": 0.85,
             "outcome": "failed" if i % 3 == 0 else "success",
             "domain": "coding"}
            for i in range(9)
        ]
        biases = self.mc.detect_bias(samples)
        self.assertIsInstance(biases, list)
        report = self.mc.get_self_report()
        self.assertEqual(report["total_thoughts"], 9)

    def test_monthly_report_after_full_session(self):
        self.pm.add_person("carol", "Carol", "friend")
        self.pm.update_belief("carol", "AI", "transformative", 0.9)
        self.pm.record_interaction("carol", "VECTOR demo", "positive", "cli")
        for i in range(5):
            self.mc.observe(f"T{i}", 0.75, "success", "coding")
        self.mc.record_calibration_error(0.75, True, "coding")
        report = self.mc.get_monthly_report()
        self.assertIn("thought_summary", report)
        self.assertEqual(report["thought_summary"]["total_thoughts"], 5)
        pm_summary = self.pm.get_model_summary()
        self.assertEqual(pm_summary["total_persons"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
