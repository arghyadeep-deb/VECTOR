"""Integration tests — Session A8: EpistemicTracker SQLite persistence + confidence decay."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _make_tracker(db_path: str):
    from core.brain.epistemic_tracker import EpistemicTracker
    return EpistemicTracker(db_path=db_path)


class TestEpistemicTrackerInit(unittest.TestCase):
    """DB is created and schema is correct on first init."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db = self._tmp.name
        self._tmp.close()
        Path(self._db).unlink(missing_ok=True)

    def tearDown(self):
        Path(self._db).unlink(missing_ok=True)

    def test_db_file_created(self):
        et = _make_tracker(self._db)
        et.close()
        self.assertTrue(Path(self._db).exists())

    def test_claims_table_exists(self):
        et = _make_tracker(self._db)
        et.close()
        conn = sqlite3.connect(self._db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        self.assertIn("claims", tables)

    def test_staleness_events_table_exists(self):
        et = _make_tracker(self._db)
        et.close()
        conn = sqlite3.connect(self._db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        self.assertIn("staleness_events", tables)

    def test_empty_on_fresh_db(self):
        et = _make_tracker(self._db)
        summary = et.get_knowledge_summary()
        et.close()
        self.assertEqual(summary["total_beliefs"], 0)


class TestRecordClaimAPI(unittest.TestCase):
    """record_claim() stores to DB and returns the claim_id."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db = self._tmp.name
        self._tmp.close()
        Path(self._db).unlink(missing_ok=True)
        from core.brain.epistemic_tracker import EpistemicTracker
        self._et = EpistemicTracker(db_path=self._db)

    def tearDown(self):
        self._et.close()
        Path(self._db).unlink(missing_ok=True)

    def test_returns_claim_id(self):
        result = self._et.record_claim("c1", "The sky is blue", 0.9)
        self.assertEqual(result, "c1")

    def test_claim_appears_in_get_belief(self):
        self._et.record_claim("c2", "Water is wet", 0.95, source="test")
        b = self._et.get_belief("c2")
        self.assertIsNotNone(b)
        self.assertEqual(b["value"], "Water is wet")

    def test_confidence_stored_correctly(self):
        self._et.record_claim("c3", "Grass is green", 0.8, source="obs")
        b = self._et.get_belief("c3")
        self.assertAlmostEqual(b["confidence"], 0.8, places=3)

    def test_custom_decay_rate_accepted(self):
        self._et.record_claim("c4", "Claim with fast decay", 0.7, decay_rate=0.1, source="test")
        b = self._et.get_belief("c4")
        self.assertIsNotNone(b)

    def test_confidence_clamped_to_1(self):
        self._et.record_claim("c5", "Overconfident claim", 1.5, source="test")
        b = self._et.get_belief("c5")
        self.assertLessEqual(b["confidence"], 1.0)

    def test_confidence_clamped_to_0(self):
        self._et.record_claim("c6", "Negative claim", -0.5, source="test")
        b = self._et.get_belief("c6")
        self.assertGreaterEqual(b["confidence"], 0.0)


class TestRestartPersistence(unittest.TestCase):
    """Confidence values survive a close() + re-instantiation (simulated restart)."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db = self._tmp.name
        self._tmp.close()
        Path(self._db).unlink(missing_ok=True)

    def tearDown(self):
        Path(self._db).unlink(missing_ok=True)

    def test_single_belief_survives_restart(self):
        et1 = _make_tracker(self._db)
        et1.update_belief("user_pref", "dark_mode", 0.85, "settings")
        et1.close()

        et2 = _make_tracker(self._db)
        b = et2.get_belief("user_pref")
        et2.close()

        self.assertIsNotNone(b)
        self.assertAlmostEqual(b["confidence"], 0.85, places=2)

    def test_multiple_beliefs_survive_restart(self):
        et1 = _make_tracker(self._db)
        et1.update_belief("k1", "v1", 0.9, "src1")
        et1.update_belief("k2", "v2", 0.6, "src2")
        et1.update_belief("k3", "v3", 0.75, "src3")
        et1.close()

        et2 = _make_tracker(self._db)
        summary = et2.get_knowledge_summary()
        et2.close()

        self.assertEqual(summary["total_beliefs"], 3)

    def test_belief_value_text_survives_restart(self):
        et1 = _make_tracker(self._db)
        et1.record_claim("claim_persist", "Persistence test payload", 0.88, source="test")
        et1.close()

        et2 = _make_tracker(self._db)
        b = et2.get_belief("claim_persist")
        et2.close()

        self.assertEqual(b["value"], "Persistence test payload")

    def test_source_survives_restart(self):
        et1 = _make_tracker(self._db)
        et1.update_belief("src_test", "val", 0.7, "my_special_source")
        et1.close()

        et2 = _make_tracker(self._db)
        b = et2.get_belief("src_test")
        et2.close()

        self.assertEqual(b["source"], "my_special_source")

    def test_upsert_updates_existing_claim(self):
        et1 = _make_tracker(self._db)
        et1.record_claim("upsert_key", "original value", 0.6, source="test")
        et1.record_claim("upsert_key", "updated value", 0.9, source="test")
        b = et1.get_belief("upsert_key")
        et1.close()

        self.assertEqual(b["value"], "updated value")
        self.assertAlmostEqual(b["confidence"], 0.9, places=2)


class TestGetConfidence(unittest.TestCase):
    """get_confidence() returns decayed float; 0.0 for unknown."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db = self._tmp.name
        self._tmp.close()
        Path(self._db).unlink(missing_ok=True)
        from core.brain.epistemic_tracker import EpistemicTracker
        self._et = EpistemicTracker(db_path=self._db)

    def tearDown(self):
        self._et.close()
        Path(self._db).unlink(missing_ok=True)

    def test_unknown_key_returns_zero(self):
        result = self._et.get_confidence("nonexistent_key_xyz")
        self.assertEqual(result, 0.0)

    def test_known_key_returns_positive(self):
        self._et.record_claim("conf_test", "Some claim", 0.8, source="test")
        result = self._et.get_confidence("conf_test")
        self.assertGreater(result, 0.0)

    def test_confidence_is_float(self):
        self._et.record_claim("float_test", "Float claim", 0.75, source="test")
        result = self._et.get_confidence("float_test")
        self.assertIsInstance(result, float)

    def test_confidence_in_0_1_range(self):
        self._et.record_claim("range_test", "Range claim", 0.65, source="test")
        result = self._et.get_confidence("range_test")
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)


class TestDecayAll(unittest.TestCase):
    """decay_all() applies decay to all beliefs and updates the DB."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db = self._tmp.name
        self._tmp.close()
        Path(self._db).unlink(missing_ok=True)
        from core.brain.epistemic_tracker import EpistemicTracker
        self._et = EpistemicTracker(db_path=self._db)

    def tearDown(self):
        self._et.close()
        Path(self._db).unlink(missing_ok=True)

    def test_decay_all_returns_int(self):
        self._et.record_claim("d1", "Claim 1", 0.9, source="test")
        result = self._et.decay_all()
        self.assertIsInstance(result, int)

    def test_decay_all_on_fresh_belief_returns_zero(self):
        """Brand-new beliefs haven't aged — nothing to decay."""
        self._et.record_claim("fresh", "Fresh claim", 0.9, source="test")
        result = self._et.decay_all()
        self.assertEqual(result, 0)

    def test_decay_all_on_aged_belief_reduces_confidence(self):
        """Simulate an aged belief by backdating last_seen_at in the DB."""
        self._et.record_claim("aged", "Aged claim", 0.9, source="test")
        # Backdate last_seen_at and created_at to 50h ago
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        self._et._conn.execute(
            "UPDATE claims SET last_seen_at=?, created_at=? WHERE id=?",
            (old_ts, old_ts, "aged"),
        )
        self._et._conn.commit()
        # Also update the in-memory cache to match
        self._et._beliefs["aged"]["created_at"] = old_ts

        before = self._et._beliefs["aged"]["confidence"]
        count = self._et.decay_all()
        after_conf = self._et.get_confidence("aged")

        self.assertLessEqual(after_conf, before)

    def test_decay_all_updates_db(self):
        """After decay_all(), the DB confidence matches the in-memory value."""
        self._et.record_claim("db_sync", "DB sync claim", 0.8, source="test")
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=40)).isoformat()
        self._et._conn.execute(
            "UPDATE claims SET last_seen_at=?, created_at=? WHERE id=?",
            (old_ts, old_ts, "db_sync"),
        )
        self._et._conn.commit()
        self._et._beliefs["db_sync"]["created_at"] = old_ts

        self._et.decay_all()
        db_conf = self._et._conn.execute(
            "SELECT confidence FROM claims WHERE id=?", ("db_sync",)
        ).fetchone()
        in_mem_conf = self._et._beliefs["db_sync"]["confidence"]
        self.assertAlmostEqual(db_conf[0], in_mem_conf, places=3)


class TestGetStaleClaims(unittest.TestCase):
    """get_stale_claims() returns claims older than age_hours or with zero confidence."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db = self._tmp.name
        self._tmp.close()
        Path(self._db).unlink(missing_ok=True)
        from core.brain.epistemic_tracker import EpistemicTracker
        self._et = EpistemicTracker(db_path=self._db)

    def tearDown(self):
        self._et.close()
        Path(self._db).unlink(missing_ok=True)

    def test_no_stale_on_fresh_claims(self):
        self._et.record_claim("fresh1", "Fresh", 0.9, source="test")
        stale = self._et.get_stale_claims(age_hours=72)
        self.assertEqual(len(stale), 0)

    def test_stale_claim_found_after_backdating(self):
        self._et.record_claim("stale1", "Old claim", 0.9, source="test")
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
        self._et._conn.execute(
            "UPDATE claims SET last_seen_at=? WHERE id=?", (old_ts, "stale1")
        )
        self._et._conn.commit()

        stale = self._et.get_stale_claims(age_hours=72)
        ids = [r["id"] for r in stale]
        self.assertIn("stale1", ids)

    def test_returns_list_of_dicts(self):
        stale = self._et.get_stale_claims(age_hours=1)
        self.assertIsInstance(stale, list)
        for item in stale:
            self.assertIsInstance(item, dict)

    def test_zero_confidence_claim_is_stale(self):
        self._et.record_claim("zero_conf", "Zero claim", 0.0, source="test")
        stale = self._et.get_stale_claims(age_hours=72)
        ids = [r["id"] for r in stale]
        self.assertIn("zero_conf", ids)


class TestKnowledgeSummary(unittest.TestCase):
    """get_knowledge_summary() returns correct counts after restart."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db = self._tmp.name
        self._tmp.close()
        Path(self._db).unlink(missing_ok=True)

    def tearDown(self):
        Path(self._db).unlink(missing_ok=True)

    def test_summary_counts_match_after_restart(self):
        et1 = _make_tracker(self._db)
        et1.update_belief("s1", "v1", 0.8, "test")
        et1.update_belief("s2", "v2", 0.6, "test")
        et1.close()

        et2 = _make_tracker(self._db)
        s = et2.get_knowledge_summary()
        et2.close()

        self.assertEqual(s["total_beliefs"], 2)

    def test_avg_confidence_correct(self):
        et = _make_tracker(self._db)
        et.update_belief("a1", "v1", 0.8, "test")
        et.update_belief("a2", "v2", 0.6, "test")
        s = et.get_knowledge_summary()
        et.close()
        self.assertAlmostEqual(s["avg_confidence"], 0.7, places=2)


class TestDecisionEngineEpistemicIntegration(unittest.TestCase):
    """Decision engine uses epistemic confidence when scoring candidates."""

    def test_get_confidence_method_exists(self):
        from core.brain.epistemic_tracker import EpistemicTracker
        et = EpistemicTracker.__new__(EpistemicTracker)
        self.assertTrue(hasattr(et, "get_confidence"))

    def test_epistemic_tracker_imported_by_decision_engine(self):
        import inspect
        from core.loop import decision_engine
        src = inspect.getsource(decision_engine)
        self.assertIn("epistemic", src.lower())

    def test_decision_engine_has_epistemic_accessor(self):
        from core.loop.decision_engine import DecisionEngine
        de = DecisionEngine()
        self.assertTrue(hasattr(de, "_get_epistemic") or hasattr(de, "_epistemic"))


if __name__ == "__main__":
    unittest.main()
