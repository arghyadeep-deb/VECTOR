import json
import tempfile
import os
from pathlib import Path

import unittest

from core.memory.counterfactual import CounterfactualMemory, _jaccard
from core.memory.causal_graph import CausalGraph


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _cf_db() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


def _cg_json() -> str:
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    f.close()
    return f.name


# ─────────────────────────────────────────────────────────────
# TestJaccardSimilarity
# ─────────────────────────────────────────────────────────────

class TestJaccardSimilarity(unittest.TestCase):

    def test_identical_strings_return_one(self):
        self.assertAlmostEqual(_jaccard("hello world", "hello world"), 1.0)

    def test_completely_different_returns_zero(self):
        self.assertAlmostEqual(_jaccard("apple banana", "cat dog"), 0.0)

    def test_partial_overlap(self):
        val = _jaccard("delete all logs", "delete logs now")
        self.assertGreater(val, 0.0)
        self.assertLess(val, 1.0)

    def test_empty_both_returns_one(self):
        self.assertAlmostEqual(_jaccard("", ""), 1.0)

    def test_one_empty_returns_zero(self):
        self.assertAlmostEqual(_jaccard("hello", ""), 0.0)
        self.assertAlmostEqual(_jaccard("", "hello"), 0.0)

    def test_case_insensitive(self):
        a = _jaccard("Hello World", "hello world")
        self.assertAlmostEqual(a, 1.0)

    def test_symmetric(self):
        self.assertAlmostEqual(_jaccard("foo bar baz", "baz qux"), _jaccard("baz qux", "foo bar baz"))


# ─────────────────────────────────────────────────────────────
# TestCounterfactualMemory — Scenario API
# ─────────────────────────────────────────────────────────────

class TestCounterfactualScenarios(unittest.TestCase):

    def setUp(self):
        self._db = _cf_db()
        self.cf = CounterfactualMemory(self._db)

    def tearDown(self):
        self.cf.close()
        Path(self._db).unlink(missing_ok=True)

    def test_record_scenario_returns_dict_with_id(self):
        s = self.cf.record_scenario("linear search", "simpler", "binary search", "10x faster")
        self.assertIsInstance(s, dict)
        self.assertIn("id", s)
        self.assertGreater(len(s["id"]), 8)

    def test_record_scenario_has_all_fields(self):
        s = self.cf.record_scenario("A", "because A", "B", "B outcome", {"key": "value"})
        self.assertEqual(s["original_action"], "A")
        self.assertEqual(s["chosen_reason"], "because A")
        self.assertEqual(s["alternative"], "B")
        self.assertEqual(s["alternative_outcome"], "B outcome")

    def test_record_scenario_persisted_to_db(self):
        s = self.cf.record_scenario("action_x", "reason_x", "alt_x", "outcome_x")
        row = self.cf._conn.execute(
            "SELECT original_action FROM scenarios WHERE id=?", (s["id"],)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "action_x")

    def test_mark_useful_returns_true_for_known_id(self):
        s = self.cf.record_scenario("a", "r", "b", "o")
        result = self.cf.mark_useful(s["id"], True, "definitely better")
        self.assertTrue(result)

    def test_mark_useful_returns_false_for_unknown_id(self):
        result = self.cf.mark_useful("nonexistent-id-xyz", True)
        self.assertFalse(result)

    def test_get_insights_after_useful_mark(self):
        s = self.cf.record_scenario("linear search", "easier", "hash table", "O(1) lookup")
        self.cf.mark_useful(s["id"], True, "Much faster for lookups")
        insights = self.cf.get_insights()
        self.assertIsInstance(insights, list)
        self.assertGreater(len(insights), 0)
        self.assertTrue(any("linear search" in i for i in insights))

    def test_get_insights_empty_when_none_marked(self):
        self.cf.record_scenario("a", "r", "b", "o")
        insights = self.cf.get_insights()
        self.assertEqual(insights, [])

    def test_get_similar_returns_list(self):
        self.cf.record_scenario("delete old files", "cleanup", "archive files", "safer")
        result = self.cf.get_similar("delete files", limit=5)
        self.assertIsInstance(result, list)

    def test_get_similar_finds_related_action(self):
        self.cf.record_scenario("delete all logs", "free space", "compress logs", "save space")
        result = self.cf.get_similar("delete logs", limit=5)
        self.assertGreater(len(result), 0)

    def test_get_similar_obeys_limit(self):
        for i in range(5):
            self.cf.record_scenario(f"action {i}", "reason", f"alt {i}", f"outcome {i}")
        result = self.cf.get_similar("action", limit=3)
        self.assertLessEqual(len(result), 3)

    def test_get_all_scenarios_returns_list(self):
        self.cf.record_scenario("a", "r", "b", "o")
        result = self.cf.get_all_scenarios()
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_get_all_scenarios_obeys_limit(self):
        for i in range(5):
            self.cf.record_scenario(f"x{i}", "r", f"y{i}", "o")
        result = self.cf.get_all_scenarios(limit=3)
        self.assertLessEqual(len(result), 3)


# ─────────────────────────────────────────────────────────────
# TestCounterfactualMemory — Rejection / Gap 4 API
# ─────────────────────────────────────────────────────────────

class TestCounterfactualRejection(unittest.TestCase):

    def setUp(self):
        self._db = _cf_db()
        self.cf = CounterfactualMemory(self._db)

    def tearDown(self):
        self.cf.close()
        Path(self._db).unlink(missing_ok=True)

    def test_record_rejection_returns_uuid_string(self):
        rid = self.cf.record_rejection("dec-001", "Delete all logs", "Too destructive")
        self.assertIsInstance(rid, str)
        self.assertGreater(len(rid), 8)

    def test_record_rejection_persisted_to_db(self):
        rid = self.cf.record_rejection("dec-002", "Wipe database", "Irreversible", {"risk": "critical"})
        row = self.cf._conn.execute(
            "SELECT proposal, reason FROM rejections WHERE id=?", (rid,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Wipe database")
        self.assertEqual(row[1], "Irreversible")

    def test_record_rejection_with_context(self):
        rid = self.cf.record_rejection("dec-003", "Send mass email", "GDPR concern", {"gdpr": True})
        row = self.cf._conn.execute(
            "SELECT context FROM rejections WHERE id=?", (rid,)
        ).fetchone()
        ctx = json.loads(row[0])
        self.assertTrue(ctx.get("gdpr"))

    def test_get_similar_rejections_empty_initially(self):
        result = self.cf.get_similar_rejections("some proposal")
        self.assertEqual(result, [])

    def test_get_similar_rejections_finds_close_match(self):
        self.cf.record_rejection("dec-010", "delete all logs", "Too destructive")
        result = self.cf.get_similar_rejections("delete logs now")
        self.assertGreater(len(result), 0)

    def test_get_similar_rejections_respects_limit(self):
        for i in range(5):
            self.cf.record_rejection(f"dec-{i}", f"proposal {i}", "reason")
        result = self.cf.get_similar_rejections("proposal", limit=2)
        self.assertLessEqual(len(result), 2)

    def test_should_avoid_returns_false_for_novel_proposal(self):
        avoid, conf, reason = self.cf.should_avoid("completely novel proposal xyz")
        self.assertFalse(avoid)
        self.assertEqual(conf, 0.0)

    def test_should_avoid_returns_true_for_known_rejection(self):
        self.cf.record_rejection("dec-020", "delete all logs", "Too destructive — data loss")
        avoid, conf, reason = self.cf.should_avoid("delete all logs")
        self.assertTrue(avoid)
        self.assertGreater(conf, 0.0)
        self.assertIn("destructive", reason.lower())

    def test_should_avoid_tuple_structure(self):
        result = self.cf.should_avoid("any proposal")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[0], bool)
        self.assertIsInstance(result[1], float)
        self.assertIsInstance(result[2], str)

    def test_should_avoid_confidence_in_range(self):
        self.cf.record_rejection("dec-030", "restart the server", "Downtime risk")
        _, conf, _ = self.cf.should_avoid("restart server now")
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf, 1.0)

    def test_learn_from_outcome_returns_dict(self):
        result = self.cf.learn_from_outcome("dec-001", "System crashed", "System stable")
        self.assertIsInstance(result, dict)
        self.assertIn("lesson", result)
        self.assertIn("decision_id", result)

    def test_learn_from_outcome_persisted(self):
        self.cf.learn_from_outcome("dec-002", "Actual outcome", "Expected outcome")
        row = self.cf._conn.execute(
            "SELECT * FROM outcomes WHERE decision_id=?", ("dec-002",)
        ).fetchone()
        self.assertIsNotNone(row)

    def test_get_outcome_returns_dict_for_known_decision(self):
        self.cf.learn_from_outcome("dec-003", "actual", "expected")
        result = self.cf.get_outcome("dec-003")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["decision_id"], "dec-003")

    def test_get_outcome_returns_none_for_unknown(self):
        result = self.cf.get_outcome("nonexistent-dec-xyz")
        self.assertIsNone(result)

    def test_get_rejection_patterns_structure(self):
        self.cf.record_rejection("dec-040", "risky action", "Too dangerous")
        patterns = self.cf.get_rejection_patterns()
        self.assertIsInstance(patterns, dict)
        self.assertIn("total_rejections", patterns)
        self.assertIn("total_outcomes_learned", patterns)
        self.assertIn("total_scenarios", patterns)

    def test_get_rejection_patterns_count_correct(self):
        for i in range(3):
            self.cf.record_rejection(f"dec-{i}", f"proposal {i}", "reason")
        patterns = self.cf.get_rejection_patterns()
        self.assertEqual(patterns["total_rejections"], 3)

    def test_get_rejection_patterns_top_reasons_list(self):
        self.cf.record_rejection("dec-1", "delete db", "Irreversible")
        self.cf.record_rejection("dec-2", "wipe disk", "Irreversible")
        patterns = self.cf.get_rejection_patterns()
        self.assertIsInstance(patterns["top_rejection_reasons"], list)


# ─────────────────────────────────────────────────────────────
# TestCausalGraph — Node API
# ─────────────────────────────────────────────────────────────

class TestCausalGraphNodes(unittest.TestCase):

    def setUp(self):
        self._json = _cg_json()
        self.cg = CausalGraph(self._json)

    def tearDown(self):
        Path(self._json).unlink(missing_ok=True)

    def test_add_node_returns_dict(self):
        node = self.cg.add_node("n1", "action", "Test action")
        self.assertIsInstance(node, dict)
        self.assertEqual(node["id"], "n1")

    def test_add_node_persists_type_and_label(self):
        self.cg.add_node("n2", "outcome", "Test outcome")
        n = self.cg.get_node("n2")
        self.assertEqual(n["type"], "outcome")
        self.assertEqual(n["label"], "Test outcome")

    def test_add_node_with_metadata(self):
        self.cg.add_node("n3", "action", "With meta", {"priority": "high"})
        n = self.cg.get_node("n3")
        self.assertEqual(n["metadata"]["priority"], "high")

    def test_get_node_unknown_returns_none(self):
        self.assertIsNone(self.cg.get_node("nonexistent"))

    def test_get_all_nodes_returns_list(self):
        self.cg.add_node("a", "action", "A")
        self.cg.add_node("b", "outcome", "B")
        nodes = self.cg.get_all_nodes()
        self.assertIsInstance(nodes, list)
        self.assertEqual(len(nodes), 2)

    def test_remove_node_returns_true(self):
        self.cg.add_node("r1", "action", "Removable")
        self.assertTrue(self.cg.remove_node("r1"))

    def test_remove_node_returns_false_for_unknown(self):
        self.assertFalse(self.cg.remove_node("nonexistent"))

    def test_remove_node_cleans_connected_edges(self):
        self.cg.add_node("from_n", "action", "From")
        self.cg.add_node("to_n", "outcome", "To")
        self.cg.add_edge("from_n", "to_n", 0.8)
        self.cg.remove_node("from_n")
        edges = self.cg.get_all_edges()
        self.assertTrue(all(e["from"] != "from_n" for e in edges))

    def test_add_node_overwrite_updates_label(self):
        self.cg.add_node("x", "action", "Original")
        self.cg.add_node("x", "action", "Updated")
        self.assertEqual(self.cg.get_node("x")["label"], "Updated")


# ─────────────────────────────────────────────────────────────
# TestCausalGraph — Edge API
# ─────────────────────────────────────────────────────────────

class TestCausalGraphEdges(unittest.TestCase):

    def setUp(self):
        self._json = _cg_json()
        self.cg = CausalGraph(self._json)
        self.cg.add_node("a", "action", "A")
        self.cg.add_node("b", "outcome", "B")
        self.cg.add_node("c", "consequence", "C")

    def tearDown(self):
        Path(self._json).unlink(missing_ok=True)

    def test_add_edge_returns_dict(self):
        result = self.cg.add_edge("a", "b", 0.7, "causes")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["from"], "a")
        self.assertEqual(result["to"], "b")

    def test_add_edge_strength_clamped_to_0_1(self):
        result = self.cg.add_edge("a", "b", 1.5)
        self.assertLessEqual(result["strength"], 1.0)
        result2 = self.cg.add_edge("b", "c", -0.5)
        self.assertGreaterEqual(result2["strength"], 0.0)

    def test_add_edge_unknown_from_returns_error(self):
        result = self.cg.add_edge("MISSING", "b", 0.5)
        self.assertEqual(result.get("status"), "error")

    def test_add_edge_unknown_to_returns_error(self):
        result = self.cg.add_edge("a", "MISSING", 0.5)
        self.assertEqual(result.get("status"), "error")

    def test_get_all_edges_returns_list(self):
        self.cg.add_edge("a", "b", 0.5)
        edges = self.cg.get_all_edges()
        self.assertIsInstance(edges, list)
        self.assertGreater(len(edges), 0)

    def test_get_outcomes_returns_downstream(self):
        self.cg.add_edge("a", "b", 0.8, "causes")
        outcomes = self.cg.get_outcomes("a")
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["to"], "b")

    def test_get_causes_returns_upstream(self):
        self.cg.add_edge("a", "b", 0.8)
        causes = self.cg.get_causes("b")
        self.assertEqual(len(causes), 1)
        self.assertEqual(causes[0]["from"], "a")

    def test_update_edge_strength_returns_true(self):
        self.cg.add_edge("a", "b", 0.5)
        result = self.cg.update_edge_strength("a", "b", 0.9)
        self.assertTrue(result)
        edge = next(e for e in self.cg.get_all_edges() if e["from"] == "a" and e["to"] == "b")
        self.assertAlmostEqual(edge["strength"], 0.9)

    def test_update_edge_strength_returns_false_for_missing_edge(self):
        result = self.cg.update_edge_strength("a", "c", 0.7)  # no edge a→c
        self.assertFalse(result)

    def test_strongest_causes_sorted_descending(self):
        self.cg.add_edge("a", "c", 0.9, "strong")
        self.cg.add_edge("b", "c", 0.3, "weak")
        top = self.cg.strongest_causes("c", top_n=2)
        self.assertEqual(len(top), 2)
        self.assertGreaterEqual(top[0]["strength"], top[1]["strength"])


# ─────────────────────────────────────────────────────────────
# TestCausalGraph — Traversal
# ─────────────────────────────────────────────────────────────

class TestCausalGraphTraversal(unittest.TestCase):

    def setUp(self):
        self._json = _cg_json()
        self.cg = CausalGraph(self._json)
        for nid, ntype, label in [
            ("commit", "action", "Git commit"),
            ("test_fail", "outcome", "Tests fail"),
            ("deploy_blocked", "consequence", "Deploy blocked"),
            ("alert_fired", "consequence", "Alert fired"),
        ]:
            self.cg.add_node(nid, ntype, label)
        self.cg.add_edge("commit", "test_fail", 0.7)
        self.cg.add_edge("test_fail", "deploy_blocked", 0.9)
        self.cg.add_edge("test_fail", "alert_fired", 0.6)

    def tearDown(self):
        Path(self._json).unlink(missing_ok=True)

    def test_get_causal_chain_direct(self):
        chain = self.cg.get_causal_chain("commit", "deploy_blocked")
        self.assertEqual(chain, ["commit", "test_fail", "deploy_blocked"])

    def test_get_causal_chain_same_node(self):
        chain = self.cg.get_causal_chain("commit", "commit")
        self.assertEqual(chain, ["commit"])

    def test_get_causal_chain_disconnected_returns_empty(self):
        chain = self.cg.get_causal_chain("deploy_blocked", "commit")
        self.assertEqual(chain, [])

    def test_get_causal_chain_unknown_node_returns_empty(self):
        chain = self.cg.get_causal_chain("commit", "NONEXISTENT")
        self.assertEqual(chain, [])

    def test_find_common_causes_returns_shared_ancestor(self):
        common = self.cg.find_common_causes("deploy_blocked", "alert_fired")
        self.assertIn("commit", common)

    def test_find_common_causes_returns_list(self):
        common = self.cg.find_common_causes("deploy_blocked", "alert_fired")
        self.assertIsInstance(common, list)

    def test_get_influence_score_commit_reaches_3(self):
        score = self.cg.get_influence_score("commit")
        self.assertEqual(score, 3)  # test_fail, deploy_blocked, alert_fired

    def test_get_influence_score_leaf_is_zero(self):
        score = self.cg.get_influence_score("deploy_blocked")
        self.assertEqual(score, 0)

    def test_get_influence_score_unknown_returns_zero(self):
        score = self.cg.get_influence_score("NONEXISTENT")
        self.assertEqual(score, 0)


# ─────────────────────────────────────────────────────────────
# TestCausalGraph — Serialization & Persistence
# ─────────────────────────────────────────────────────────────

class TestCausalGraphPersistence(unittest.TestCase):

    def setUp(self):
        self._json = _cg_json()

    def tearDown(self):
        Path(self._json).unlink(missing_ok=True)

    def test_to_dict_contains_nodes_and_edges(self):
        cg = CausalGraph(self._json)
        cg.add_node("x", "action", "X")
        d = cg.to_dict()
        self.assertIn("nodes", d)
        self.assertIn("edges", d)
        self.assertIn("x", d["nodes"])

    def test_from_dict_round_trip(self):
        cg = CausalGraph(self._json)
        cg.add_node("p", "action", "P")
        cg.add_node("q", "outcome", "Q")
        cg.add_edge("p", "q", 0.5)
        data = cg.to_dict()
        cg2 = CausalGraph(self._json + "_new")
        cg2.from_dict(data)
        self.assertIn("p", {n["id"] for n in cg2.get_all_nodes()})
        Path(self._json + "_new").unlink(missing_ok=True)

    def test_persistence_reload(self):
        cg = CausalGraph(self._json)
        cg.add_node("n1", "action", "N1")
        cg.add_node("n2", "outcome", "N2")
        cg.add_edge("n1", "n2", 0.8)
        # Reload from same path
        cg2 = CausalGraph(self._json)
        self.assertEqual(len(cg2.get_all_nodes()), 2)
        self.assertEqual(len(cg2.get_all_edges()), 1)

    def test_get_graph_summary_structure(self):
        cg = CausalGraph(self._json)
        cg.add_node("a", "action", "A")
        cg.add_node("b", "outcome", "B")
        cg.add_edge("a", "b", 0.6)
        summary = cg.get_graph_summary()
        self.assertIn("total_nodes", summary)
        self.assertIn("total_edges", summary)
        self.assertIn("avg_edge_strength", summary)
        self.assertIn("node_types", summary)

    def test_get_graph_summary_counts(self):
        cg = CausalGraph(self._json)
        cg.add_node("x", "action", "X")
        cg.add_node("y", "outcome", "Y")
        cg.add_edge("x", "y", 0.7)
        summary = cg.get_graph_summary()
        self.assertEqual(summary["total_nodes"], 2)
        self.assertEqual(summary["total_edges"], 1)
        self.assertAlmostEqual(summary["avg_edge_strength"], 0.7, places=2)

    def test_get_graph_summary_empty_graph(self):
        cg = CausalGraph(self._json)
        summary = cg.get_graph_summary()
        self.assertEqual(summary["total_nodes"], 0)
        self.assertEqual(summary["total_edges"], 0)
        self.assertAlmostEqual(summary["avg_edge_strength"], 0.0)


# ─────────────────────────────────────────────────────────────
# TestYear2Integration
# ─────────────────────────────────────────────────────────────

class TestYear2Integration(unittest.TestCase):
    """End-to-end tests proving Gap 4 (counterfactual) and Gap 6 (causal_graph) interact."""

    def setUp(self):
        self._db = _cf_db()
        self._json = _cg_json()
        self.cf = CounterfactualMemory(self._db)
        self.cg = CausalGraph(self._json)

    def tearDown(self):
        self.cf.close()
        Path(self._db).unlink(missing_ok=True)
        Path(self._json).unlink(missing_ok=True)

    def test_reject_then_avoid_cycle(self):
        self.cf.record_rejection("dec-001", "drop production database", "irreversible data loss")
        avoid, conf, reason = self.cf.should_avoid("drop the production database")
        self.assertTrue(avoid)
        self.assertIn("irreversible", reason.lower())

    def test_learn_outcome_then_retrieve(self):
        self.cf.record_rejection("dec-010", "restart production", "causes downtime")
        self.cf.learn_from_outcome("dec-010", "service went down for 5 min", "brief maintenance window")
        outcome = self.cf.get_outcome("dec-010")
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome["decision_id"], "dec-010")

    def test_counterfactual_scenario_insights_flow(self):
        s = self.cf.record_scenario(
            "used polling loop", "simple to write",
            "used websocket push", "50% less CPU",
            {"context": "realtime dashboard"},
        )
        self.cf.mark_useful(s["id"], True, "Websocket approach saved resources")
        insights = self.cf.get_insights()
        self.assertTrue(any("websocket push" in i.lower() for i in insights))

    def test_causal_chain_decision_to_consequence(self):
        self.cg.add_node("skip_tests", "action", "Skipped test suite")
        self.cg.add_node("bug_in_prod", "outcome", "Bug in production")
        self.cg.add_node("user_complaints", "consequence", "User complaints")
        self.cg.add_edge("skip_tests", "bug_in_prod", 0.85)
        self.cg.add_edge("bug_in_prod", "user_complaints", 0.9)
        chain = self.cg.get_causal_chain("skip_tests", "user_complaints")
        self.assertEqual(len(chain), 3)
        self.assertEqual(chain[0], "skip_tests")
        self.assertEqual(chain[-1], "user_complaints")

    def test_influence_score_hub_node(self):
        for i in range(4):
            self.cg.add_node(f"effect_{i}", "outcome", f"Effect {i}")
        self.cg.add_node("root_cause", "action", "Root cause")
        for i in range(4):
            self.cg.add_edge("root_cause", f"effect_{i}", 0.5)
        score = self.cg.get_influence_score("root_cause")
        self.assertEqual(score, 4)

    def test_rejection_feeds_causal_graph(self):
        rid = self.cf.record_rejection("dec-020", "force push to main", "bypasses review")
        self.cg.add_node(f"rejection_{rid[:8]}", "rejection", "Force push to main rejected")
        self.assertIsNotNone(self.cg.get_node(f"rejection_{rid[:8]}"))

    def test_rejection_patterns_grow_with_multiple_rejections(self):
        reasons = ["Too risky", "Irreversible", "Requires approval", "Too risky"]
        for i, reason in enumerate(reasons):
            self.cf.record_rejection(f"dec-{i}", f"action {i}", reason)
        patterns = self.cf.get_rejection_patterns()
        self.assertEqual(patterns["total_rejections"], 4)
        top = patterns["top_rejection_reasons"]
        self.assertGreater(len(top), 0)
        top_reasons = [r["reason"] for r in top]
        self.assertTrue(any("risky" in r.lower() for r in top_reasons))

    def test_causal_graph_persistence_across_instances(self):
        self.cg.add_node("cause", "action", "Cause")
        self.cg.add_node("effect", "outcome", "Effect")
        self.cg.add_edge("cause", "effect", 0.75)
        # New instance same path
        cg2 = CausalGraph(self._json)
        self.assertEqual(len(cg2.get_all_nodes()), 2)
        chain = cg2.get_causal_chain("cause", "effect")
        self.assertEqual(chain, ["cause", "effect"])

    def test_counterfactual_accumulates_across_multiple_decisions(self):
        for i in range(5):
            self.cf.record_rejection(f"dec-{i}", f"proposal {i}", f"reason {i}")
        patterns = self.cf.get_rejection_patterns()
        self.assertEqual(patterns["total_rejections"], 5)

    def test_should_avoid_novel_proposal_stays_false(self):
        self.cf.record_rejection("dec-001", "delete database", "irreversible")
        avoid, _, _ = self.cf.should_avoid("send a friendly email")
        self.assertFalse(avoid)


if __name__ == "__main__":
    unittest.main()
