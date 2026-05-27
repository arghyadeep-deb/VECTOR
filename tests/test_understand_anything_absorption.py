"""
Tests for VECTOR's Understand-Anything-main absorption:
  core/knowledge/domain_extractor.py  — DomainExtractor, DomainContext
  core/knowledge/wiki_parser.py        — WikiParser
  core/knowledge/wiki_merger.py        — WikiMerger
  core/knowledge/graph_merger.py       — GraphMerger, SubgraphMerger
"""
import gc
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_project(root: Path) -> None:
    """Create a minimal fake project for DomainExtractor tests."""
    src = root / "src"
    src.mkdir()
    (src / "app.py").write_text('@app.route("/api/users")\ndef get_users():\n    pass\n')
    (src / "cli.py").write_text('parser.add_subparsers()\nparser.add_parser("run")\n')
    (root / "README.md").write_text("# Test Project\nA sample project.\n")
    (root / "requirements.txt").write_text("fastapi\nloguru\n")


def _make_wiki(root: Path) -> None:
    """Create a minimal Karpathy-format wiki."""
    wiki = root / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "index.md").write_text(
        "# My Project\n\n"
        "## Core\n\n- [[introduction]]\n- [[architecture]]\n\n"
        "## Tools\n\n- [[tooling]]\n"
    )
    (wiki / "introduction.md").write_text(
        "# Introduction\n\nThis is the intro.\n\n[[architecture]] is the next step.\n"
    )
    (wiki / "architecture.md").write_text(
        "# Architecture\n\nBuilt on [[tooling]].\n"
    )
    (wiki / "tooling.md").write_text(
        "# Tooling\n\nUses Python and FastAPI.\n"
    )


# ══════════════════════════════════════════════════════════════════════════════
# DomainExtractor tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDomainExtractor(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        _make_project(self.root)
        from core.knowledge.domain_extractor import DomainExtractor
        self.extractor = DomainExtractor()

    def tearDown(self):
        gc.collect()
        self._tmp.cleanup()

    def test_scan_returns_domain_context(self):
        from core.knowledge.domain_extractor import DomainContext
        ctx = self.extractor.scan(self.root)
        self.assertIsInstance(ctx, DomainContext)

    def test_file_count_positive(self):
        ctx = self.extractor.scan(self.root)
        self.assertGreaterEqual(ctx.file_count, 2)

    def test_detects_http_route(self):
        ctx = self.extractor.scan(self.root)
        self.assertTrue(any(ep["type"] == "http" for ep in ctx.entry_points),
                        "Should detect @app.route HTTP entry point")

    def test_detects_cli_subparser(self):
        ctx = self.extractor.scan(self.root)
        self.assertTrue(any(ep["type"] == "cli" for ep in ctx.entry_points),
                        "Should detect argparse CLI subparser")

    def test_entry_point_has_required_fields(self):
        ctx = self.extractor.scan(self.root)
        for ep in ctx.entry_points:
            self.assertIn("file", ep)
            self.assertIn("type", ep)
            self.assertIn("line", ep)
            self.assertIn("match", ep)

    def test_file_signatures_extracted(self):
        ctx = self.extractor.scan(self.root)
        self.assertGreaterEqual(len(ctx.file_signatures), 1)
        sig = ctx.file_signatures[0]
        self.assertIn("file", sig)
        self.assertIn("imports", sig)
        self.assertIn("exports", sig)
        self.assertIn("lines", sig)

    def test_readme_in_metadata(self):
        ctx = self.extractor.scan(self.root)
        self.assertIn("README.md", ctx.metadata)

    def test_to_dict_structure(self):
        ctx = self.extractor.scan(self.root)
        d = ctx.to_dict()
        self.assertIn("projectRoot", d)
        self.assertIn("fileCount", d)
        self.assertIn("fileTree", d)
        self.assertIn("entryPoints", d)
        self.assertIn("fileSignatures", d)
        self.assertIn("metadata", d)

    def test_to_dict_values_consistent(self):
        ctx = self.extractor.scan(self.root)
        d = ctx.to_dict()
        self.assertEqual(d["fileCount"], ctx.file_count)
        self.assertEqual(d["projectRoot"], str(self.root.resolve()))

    def test_write_output_json(self):
        output = self.root / "domain-context.json"
        ctx = self.extractor.scan(self.root, output_path=output)
        self.assertTrue(output.exists())
        data = json.loads(output.read_text())
        self.assertIn("projectRoot", data)
        self.assertGreater(data["fileCount"], 0)

    def test_output_json_size_under_512kb(self):
        output = self.root / "domain-context.json"
        self.extractor.scan(self.root, output_path=output)
        size = output.stat().st_size
        self.assertLessEqual(size, 512 * 1024)

    def test_invalid_root_raises(self):
        with self.assertRaises(ValueError):
            self.extractor.scan(self.root / "nonexistent_dir")

    def test_skip_dirs_excluded(self):
        (self.root / "node_modules" / "lib").mkdir(parents=True)
        (self.root / "node_modules" / "lib" / "index.js").write_text("module.exports = {}")
        ctx = self.extractor.scan(self.root)
        for rel in ctx.file_tree:
            self.assertNotIn("node_modules", rel)

    def test_source_extensions_filtered(self):
        (self.root / "data.csv").write_text("a,b,c")
        (self.root / "image.png").write_bytes(b"\x89PNG")
        ctx = self.extractor.scan(self.root)
        for rel in ctx.file_tree:
            self.assertFalse(rel.endswith(".csv") or rel.endswith(".png"))

    def test_file_tree_uses_forward_slashes(self):
        ctx = self.extractor.scan(self.root)
        for rel in ctx.file_tree:
            self.assertNotIn("\\", rel)

    def test_entry_points_from_fastapi_decorator(self):
        (self.root / "src" / "api.py").write_text('@router.get("/items")\nasync def list_items(): pass\n')
        ctx = self.extractor.scan(self.root)
        routes = [ep for ep in ctx.entry_points if ep["type"] == "http"]
        self.assertGreaterEqual(len(routes), 1)


# ══════════════════════════════════════════════════════════════════════════════
# WikiParser tests
# ══════════════════════════════════════════════════════════════════════════════

class TestWikiParser(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        _make_wiki(self.root)
        from core.knowledge.wiki_parser import WikiParser
        self.parser = WikiParser()

    def tearDown(self):
        gc.collect()
        self._tmp.cleanup()

    def test_parse_returns_manifest_dict(self):
        result = self.parser.parse(self.root)
        self.assertIsInstance(result, dict)

    def test_manifest_has_required_keys(self):
        result = self.parser.parse(self.root)
        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertIn("categories", result)

    def test_detects_article_nodes(self):
        result = self.parser.parse(self.root)
        articles = [n for n in result["nodes"] if n["type"] == "article"]
        self.assertGreaterEqual(len(articles), 3)

    def test_detects_topic_nodes_from_index(self):
        result = self.parser.parse(self.root)
        topics = [n for n in result["nodes"] if n["type"] == "topic"]
        self.assertGreaterEqual(len(topics), 2)

    def test_article_node_has_required_fields(self):
        result = self.parser.parse(self.root)
        articles = [n for n in result["nodes"] if n["type"] == "article"]
        for article in articles:
            self.assertIn("id", article)
            self.assertIn("type", article)
            self.assertIn("name", article)
            self.assertIn("summary", article)
            self.assertIn("complexity", article)
            self.assertIn("tags", article)

    def test_complexity_valid_values(self):
        result = self.parser.parse(self.root)
        valid = {"simple", "moderate", "complex"}
        for node in result["nodes"]:
            self.assertIn(node.get("complexity", "simple"), valid)

    def test_categorized_under_edges(self):
        result = self.parser.parse(self.root)
        cat_edges = [e for e in result["edges"] if e["type"] == "categorized_under"]
        self.assertGreaterEqual(len(cat_edges), 2)

    def test_wikilink_resolved_to_related_edge(self):
        result = self.parser.parse(self.root)
        related_edges = [e for e in result["edges"] if e["type"] == "related"]
        # introduction links to architecture, architecture links to tooling
        self.assertGreaterEqual(len(related_edges), 1)

    def test_categories_from_index_headings(self):
        result = self.parser.parse(self.root)
        cat_names = {c["name"] for c in result["categories"]}
        self.assertIn("Core", cat_names)
        self.assertIn("Tools", cat_names)

    def test_backlinks_computed(self):
        result = self.parser.parse(self.root)
        arch = next((n for n in result["nodes"] if "architecture" in n["id"]), None)
        if arch:
            meta = arch.get("knowledgeMeta", {})
            # architecture is linked from introduction → should have backlink
            backlinks = meta.get("backlinks", [])
            self.assertIsInstance(backlinks, list)

    def test_edge_has_required_fields(self):
        result = self.parser.parse(self.root)
        for edge in result["edges"]:
            self.assertIn("source", edge)
            self.assertIn("target", edge)
            self.assertIn("type", edge)
            self.assertIn("weight", edge)

    def test_parse_to_file_writes_json(self):
        out_path = self.parser.parse_to_file(self.root)
        self.assertTrue(out_path.exists())
        data = json.loads(out_path.read_text())
        self.assertIn("nodes", data)
        self.assertGreater(len(data["nodes"]), 0)

    def test_no_duplicate_node_ids(self):
        result = self.parser.parse(self.root)
        ids = [n["id"] for n in result["nodes"]]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate node IDs found")

    def test_no_duplicate_edges(self):
        result = self.parser.parse(self.root)
        keys = [(e["source"], e["target"], e["type"]) for e in result["edges"]]
        self.assertEqual(len(keys), len(set(keys)), "Duplicate edges found")

    def test_articles_have_article_prefix(self):
        result = self.parser.parse(self.root)
        articles = [n for n in result["nodes"] if n["type"] == "article"]
        for a in articles:
            self.assertTrue(a["id"].startswith("article:"), f"Bad article ID: {a['id']}")

    def test_topics_have_topic_prefix(self):
        result = self.parser.parse(self.root)
        topics = [n for n in result["nodes"] if n["type"] == "topic"]
        for t in topics:
            self.assertTrue(t["id"].startswith("topic:"), f"Bad topic ID: {t['id']}")

    def test_empty_wiki_returns_minimal_manifest(self):
        tmp2 = tempfile.mkdtemp()
        try:
            root2 = Path(tmp2)
            (root2 / "wiki").mkdir()
            (root2 / "wiki" / "index.md").write_text("# Empty\n")
            (root2 / "wiki" / "note.md").write_text("# Note\nContent.\n")
            result = WikiParser().parse(root2)
            self.assertIn("nodes", result)
            self.assertIsInstance(result["nodes"], list)
        finally:
            import shutil
            shutil.rmtree(tmp2, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# WikiMerger tests
# ══════════════════════════════════════════════════════════════════════════════

class TestWikiMerger(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        from core.knowledge.wiki_merger import WikiMerger
        self.merger = WikiMerger()

        self.manifest = {
            "nodes": [
                {"id": "article:wiki/intro", "type": "article", "name": "Intro",
                 "summary": "Introduction", "tags": [], "complexity": "simple",
                 "knowledgeMeta": {}},
                {"id": "topic:basics", "type": "topic", "name": "Basics",
                 "summary": "Basics", "tags": [], "complexity": "simple",
                 "knowledgeMeta": {}},
            ],
            "edges": [
                {"source": "article:wiki/intro", "target": "topic:basics",
                 "type": "categorized_under", "direction": "forward", "weight": 1.0},
            ],
            "categories": [{"name": "Basics", "count": 1}],
        }

    def tearDown(self):
        gc.collect()
        self._tmp.cleanup()

    def test_merge_returns_graph_dict(self):
        graph = self.merger.merge(self.root, self.manifest)
        self.assertIsInstance(graph, dict)

    def test_graph_version(self):
        graph = self.merger.merge(self.root, self.manifest)
        self.assertEqual(graph["version"], "1.0.0")

    def test_graph_kind_knowledge(self):
        graph = self.merger.merge(self.root, self.manifest)
        self.assertEqual(graph["kind"], "knowledge")

    def test_graph_has_required_keys(self):
        graph = self.merger.merge(self.root, self.manifest)
        for key in ("nodes", "edges", "layers", "tour", "project"):
            self.assertIn(key, graph)

    def test_base_nodes_preserved(self):
        graph = self.merger.merge(self.root, self.manifest)
        node_ids = {n["id"] for n in graph["nodes"]}
        self.assertIn("article:wiki/intro", node_ids)
        self.assertIn("topic:basics", node_ids)

    def test_batch_entity_added(self):
        batch = {
            "nodes": [{"id": "entity:python", "type": "entity", "name": "Python",
                       "summary": "Lang", "tags": [], "complexity": "simple"}],
            "edges": [{"source": "article:wiki/intro", "target": "entity:python",
                       "type": "related", "direction": "forward", "weight": 0.8}],
        }
        graph = self.merger.merge(self.root, self.manifest, [batch])
        node_ids = {n["id"] for n in graph["nodes"]}
        self.assertIn("entity:python", node_ids)

    def test_entity_deduplication(self):
        batch1 = {
            "nodes": [{"id": "entity:python", "type": "entity", "name": "Python",
                       "summary": "Lang", "tags": [], "complexity": "simple"}],
            "edges": [],
        }
        batch2 = {
            "nodes": [{"id": "entity:python-dup", "type": "entity", "name": "Python",
                       "summary": "Dup", "tags": [], "complexity": "simple"}],
            "edges": [],
        }
        graph = self.merger.merge(self.root, self.manifest, [batch1, batch2])
        python_nodes = [n for n in graph["nodes"] if n.get("name") == "Python"]
        self.assertEqual(len(python_nodes), 1)

    def test_dangling_edge_dropped(self):
        batch = {
            "nodes": [],
            "edges": [
                {"source": "article:wiki/intro", "target": "entity:ghost",
                 "type": "related", "direction": "forward", "weight": 0.5},
            ],
        }
        graph = self.merger.merge(self.root, self.manifest, [batch])
        ghost_edges = [e for e in graph["edges"] if e.get("target") == "entity:ghost"]
        self.assertEqual(len(ghost_edges), 0)

    def test_edge_deduplication(self):
        batch = {
            "nodes": [],
            "edges": [
                {"source": "article:wiki/intro", "target": "topic:basics",
                 "type": "categorized_under", "direction": "forward", "weight": 0.8},
            ],
        }
        graph = self.merger.merge(self.root, self.manifest, [batch])
        cat_edges = [e for e in graph["edges"]
                     if e["type"] == "categorized_under"
                     and e["source"] == "article:wiki/intro"
                     and e["target"] == "topic:basics"]
        self.assertEqual(len(cat_edges), 1)

    def test_layer_built_from_categories(self):
        graph = self.merger.merge(self.root, self.manifest)
        layer_ids = {l["id"] for l in graph["layers"]}
        self.assertIn("layer:basics", layer_ids)

    def test_layer_contains_article(self):
        graph = self.merger.merge(self.root, self.manifest)
        basics_layer = next(l for l in graph["layers"] if l["id"] == "layer:basics")
        self.assertIn("article:wiki/intro", basics_layer["nodeIds"])

    def test_uncategorized_gets_other_layer(self):
        manifest2 = {
            "nodes": [
                {"id": "article:wiki/intro", "type": "article", "name": "Intro",
                 "summary": "...", "tags": [], "complexity": "simple", "knowledgeMeta": {}},
                {"id": "article:wiki/orphan", "type": "article", "name": "Orphan",
                 "summary": "...", "tags": [], "complexity": "simple", "knowledgeMeta": {}},
                {"id": "topic:basics", "type": "topic", "name": "Basics",
                 "summary": "...", "tags": [], "complexity": "simple", "knowledgeMeta": {}},
            ],
            "edges": [
                {"source": "article:wiki/intro", "target": "topic:basics",
                 "type": "categorized_under", "direction": "forward", "weight": 1.0},
            ],
            "categories": [{"name": "Basics", "count": 1}],
        }
        graph = self.merger.merge(self.root, manifest2)
        layer_ids = {l["id"] for l in graph["layers"]}
        self.assertIn("layer:other", layer_ids)
        other = next(l for l in graph["layers"] if l["id"] == "layer:other")
        self.assertIn("article:wiki/orphan", other["nodeIds"])

    def test_tour_generated(self):
        graph = self.merger.merge(self.root, self.manifest)
        self.assertIsInstance(graph["tour"], list)
        self.assertGreaterEqual(len(graph["tour"]), 1)

    def test_tour_step_has_order(self):
        graph = self.merger.merge(self.root, self.manifest)
        for step in graph["tour"]:
            self.assertIn("order", step)
            self.assertIsInstance(step["order"], int)

    def test_node_type_alias_normalized(self):
        batch = {
            "nodes": [{"id": "entity:alice", "type": "person", "name": "Alice",
                       "summary": "A person", "tags": [], "complexity": "simple"}],
            "edges": [],
        }
        graph = self.merger.merge(self.root, self.manifest, [batch])
        alice = next((n for n in graph["nodes"] if n["id"] == "entity:alice"), None)
        self.assertIsNotNone(alice)
        self.assertEqual(alice["type"], "entity")

    def test_edge_type_alias_normalized(self):
        batch = {
            "nodes": [{"id": "entity:pylib", "type": "entity", "name": "PyLib",
                       "summary": "Lib", "tags": [], "complexity": "simple"}],
            "edges": [
                {"source": "article:wiki/intro", "target": "entity:pylib",
                 "type": "references", "direction": "forward", "weight": 0.7},
            ],
        }
        graph = self.merger.merge(self.root, self.manifest, [batch])
        ref_edges = [e for e in graph["edges"] if e["type"] == "cites"]
        self.assertGreaterEqual(len(ref_edges), 1)

    def test_unknown_node_type_skipped(self):
        batch = {
            "nodes": [{"id": "entity:xyz", "type": "UNKNOWN_TYPE_12345",
                       "name": "XYZ", "summary": "", "tags": [], "complexity": "simple"}],
            "edges": [],
        }
        graph = self.merger.merge(self.root, self.manifest, [batch])
        xyz = next((n for n in graph["nodes"] if n.get("id") == "entity:xyz"), None)
        self.assertIsNone(xyz)

    def test_write_output(self):
        graph = self.merger.merge(self.root, self.manifest)
        out = self.merger.write(self.root, graph)
        self.assertTrue(out.exists())
        data = json.loads(out.read_text())
        self.assertEqual(data["version"], "1.0.0")

    def test_project_name_detected(self):
        (self.root / "wiki").mkdir()
        (self.root / "wiki" / "index.md").write_text("# My Cool Project\n")
        graph = self.merger.merge(self.root, self.manifest)
        self.assertEqual(graph["project"]["name"], "My Cool Project")

    def test_no_batches_returns_manifest_graph(self):
        graph = self.merger.merge(self.root, self.manifest, [])
        self.assertEqual(len(graph["nodes"]), len(self.manifest["nodes"]))

    def test_empty_batches_accepted(self):
        graph = self.merger.merge(self.root, self.manifest, [{}, {"nodes": None}])
        self.assertIsNotNone(graph)


# ══════════════════════════════════════════════════════════════════════════════
# GraphMerger tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGraphMerger(unittest.TestCase):

    def setUp(self):
        from core.knowledge.graph_merger import GraphMerger
        self.gm = GraphMerger()

    def _node(self, nid, ntype="file", name=None, complexity="simple", **kw):
        return {"id": nid, "type": ntype, "name": name or nid, "complexity": complexity, **kw}

    def _edge(self, src, tgt, etype="imports", direction="forward", weight=0.5):
        return {"source": src, "target": tgt, "type": etype,
                "direction": direction, "weight": weight}

    def test_merge_returns_tuple(self):
        assembled, report = self.gm.merge([])
        self.assertIsInstance(assembled, dict)
        self.assertIsInstance(report, list)

    def test_empty_batches(self):
        assembled, _ = self.gm.merge([])
        self.assertEqual(len(assembled["nodes"]), 0)
        self.assertEqual(len(assembled["edges"]), 0)

    def test_double_prefix_stripped(self):
        b = {"nodes": [self._node("file:file:src/app.ts")], "edges": []}
        assembled, _ = self.gm.merge([b])
        self.assertIn("file:src/app.ts", {n["id"] for n in assembled["nodes"]})

    def test_func_prefix_canonicalized(self):
        b = {"nodes": [self._node("func:utils/helper", ntype="function")], "edges": []}
        assembled, _ = self.gm.merge([b])
        self.assertIn("function:utils/helper", {n["id"] for n in assembled["nodes"]})

    def test_project_name_prefix_stripped(self):
        b = {"nodes": [self._node("myproject:class:MyClass", ntype="class")], "edges": []}
        assembled, _ = self.gm.merge([b])
        ids = {n["id"] for n in assembled["nodes"]}
        self.assertIn("class:MyClass", ids)

    def test_bare_path_gets_file_prefix(self):
        b = {"nodes": [{"id": "src/bare.ts", "type": "file", "name": "bare", "complexity": "simple"}], "edges": []}
        assembled, _ = self.gm.merge([b])
        ids = {n["id"] for n in assembled["nodes"]}
        self.assertTrue(any("bare.ts" in nid for nid in ids))

    def test_complexity_low_to_simple(self):
        b = {"nodes": [self._node("file:a.py", complexity="low")], "edges": []}
        assembled, _ = self.gm.merge([b])
        node = assembled["nodes"][0]
        self.assertEqual(node["complexity"], "simple")

    def test_complexity_medium_to_moderate(self):
        b = {"nodes": [self._node("file:a.py", complexity="medium")], "edges": []}
        assembled, _ = self.gm.merge([b])
        self.assertEqual(assembled["nodes"][0]["complexity"], "moderate")

    def test_complexity_high_to_complex(self):
        b = {"nodes": [self._node("file:a.py", complexity="high")], "edges": []}
        assembled, _ = self.gm.merge([b])
        self.assertEqual(assembled["nodes"][0]["complexity"], "complex")

    def test_complexity_numeric_low(self):
        b = {"nodes": [self._node("file:a.py", complexity=2)], "edges": []}
        assembled, _ = self.gm.merge([b])
        self.assertEqual(assembled["nodes"][0]["complexity"], "simple")

    def test_complexity_numeric_mid(self):
        b = {"nodes": [self._node("file:a.py", complexity=5)], "edges": []}
        assembled, _ = self.gm.merge([b])
        self.assertEqual(assembled["nodes"][0]["complexity"], "moderate")

    def test_complexity_numeric_high(self):
        b = {"nodes": [self._node("file:a.py", complexity=8)], "edges": []}
        assembled, _ = self.gm.merge([b])
        self.assertEqual(assembled["nodes"][0]["complexity"], "complex")

    def test_complexity_already_valid_unchanged(self):
        b = {"nodes": [self._node("file:a.py", complexity="moderate")], "edges": []}
        assembled, _ = self.gm.merge([b])
        self.assertEqual(assembled["nodes"][0]["complexity"], "moderate")

    def test_complexity_unknown_defaults_to_moderate(self):
        b = {"nodes": [self._node("file:a.py", complexity="extreme")], "edges": []}
        assembled, _ = self.gm.merge([b])
        self.assertEqual(assembled["nodes"][0]["complexity"], "moderate")

    def test_node_no_id_skipped(self):
        b = {"nodes": [{"type": "file", "name": "no-id"}], "edges": []}
        assembled, report = self.gm.merge([b])
        self.assertEqual(len(assembled["nodes"]), 0)
        self.assertTrue(any("missing 'id'" in l for l in report))

    def test_duplicate_nodes_last_wins(self):
        b1 = {"nodes": [self._node("file:a.py", name="first")], "edges": []}
        b2 = {"nodes": [self._node("file:a.py", name="second")], "edges": []}
        assembled, _ = self.gm.merge([b1, b2])
        self.assertEqual(len(assembled["nodes"]), 1)
        self.assertEqual(assembled["nodes"][0]["name"], "second")

    def test_edge_dedup_higher_weight_wins(self):
        b = {
            "nodes": [self._node("file:a.py"), self._node("file:b.py")],
            "edges": [
                self._edge("file:a.py", "file:b.py", weight=0.3),
                self._edge("file:a.py", "file:b.py", weight=0.9),
            ],
        }
        assembled, _ = self.gm.merge([b])
        edges = assembled["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["weight"], 0.9)

    def test_dangling_edge_dropped(self):
        b = {
            "nodes": [self._node("file:real.py")],
            "edges": [self._edge("file:real.py", "file:ghost.py")],
        }
        assembled, report = self.gm.merge([b])
        self.assertEqual(len(assembled["edges"]), 0)
        self.assertTrue(any("dropped" in l for l in report))

    def test_direction_normalized_both_to_bidirectional(self):
        b = {
            "nodes": [self._node("file:a.py"), self._node("file:b.py")],
            "edges": [{"source": "file:a.py", "target": "file:b.py",
                       "type": "imports", "direction": "both", "weight": 0.5}],
        }
        assembled, _ = self.gm.merge([b])
        self.assertEqual(assembled["edges"][0]["direction"], "bidirectional")

    def test_direction_invalid_defaults_to_forward(self):
        b = {
            "nodes": [self._node("file:a.py"), self._node("file:b.py")],
            "edges": [{"source": "file:a.py", "target": "file:b.py",
                       "type": "imports", "direction": "INVALID", "weight": 0.5}],
        }
        assembled, _ = self.gm.merge([b])
        self.assertEqual(assembled["edges"][0]["direction"], "forward")

    def test_tested_by_inverted_flipped(self):
        # LLM emitted test → production (wrong direction)
        b = {
            "nodes": [
                self._node("file:src/calc.py", filePath="src/calc.py"),
                self._node("file:tests/test_calc.py", filePath="tests/test_calc.py"),
            ],
            "edges": [
                {"source": "file:tests/test_calc.py", "target": "file:src/calc.py",
                 "type": "tested_by", "direction": "forward", "weight": 0.8},
            ],
        }
        assembled, _ = self.gm.merge([b])
        tb_edges = [e for e in assembled["edges"] if e["type"] == "tested_by"]
        self.assertEqual(len(tb_edges), 1)
        self.assertEqual(tb_edges[0]["source"], "file:src/calc.py")
        self.assertEqual(tb_edges[0]["target"], "file:tests/test_calc.py")

    def test_tested_by_path_convention_go(self):
        b = {
            "nodes": [
                self._node("file:pkg/server.go", filePath="pkg/server.go"),
                self._node("file:pkg/server_test.go", filePath="pkg/server_test.go"),
            ],
            "edges": [],
        }
        assembled, _ = self.gm.merge([b])
        tb_edges = [e for e in assembled["edges"] if e["type"] == "tested_by"]
        self.assertEqual(len(tb_edges), 1)
        self.assertEqual(tb_edges[0]["source"], "file:pkg/server.go")

    def test_tested_by_path_convention_python(self):
        b = {
            "nodes": [
                self._node("file:myapp/utils.py", filePath="myapp/utils.py"),
                self._node("file:tests/test_utils.py", filePath="tests/test_utils.py"),
            ],
            "edges": [],
        }
        assembled, _ = self.gm.merge([b])
        tb_edges = [e for e in assembled["edges"] if e["type"] == "tested_by"]
        self.assertEqual(len(tb_edges), 1)
        self.assertEqual(tb_edges[0]["source"], "file:myapp/utils.py")

    def test_tested_by_path_convention_ts(self):
        b = {
            "nodes": [
                self._node("file:src/util.ts", filePath="src/util.ts"),
                self._node("file:src/util.test.ts", filePath="src/util.test.ts"),
            ],
            "edges": [],
        }
        assembled, _ = self.gm.merge([b])
        tb_edges = [e for e in assembled["edges"] if e["type"] == "tested_by"]
        self.assertEqual(len(tb_edges), 1)
        self.assertEqual(tb_edges[0]["source"], "file:src/util.ts")

    def test_tested_by_production_tagged(self):
        b = {
            "nodes": [
                self._node("file:src/calc.py", filePath="src/calc.py"),
                self._node("file:tests/test_calc.py", filePath="tests/test_calc.py"),
            ],
            "edges": [],
        }
        assembled, _ = self.gm.merge([b])
        prod = next(n for n in assembled["nodes"] if n["id"] == "file:src/calc.py")
        self.assertIn("tested", prod.get("tags", []))

    def test_tested_by_test_test_dropped(self):
        # test → test: not recoverable
        b = {
            "nodes": [
                self._node("file:tests/test_a.py", filePath="tests/test_a.py"),
                self._node("file:tests/test_b.py", filePath="tests/test_b.py"),
            ],
            "edges": [
                {"source": "file:tests/test_a.py", "target": "file:tests/test_b.py",
                 "type": "tested_by", "direction": "forward", "weight": 0.5},
            ],
        }
        assembled, _ = self.gm.merge([b])
        tb_edges = [e for e in assembled["edges"] if e["type"] == "tested_by"]
        self.assertEqual(len(tb_edges), 0)

    def test_report_includes_input_output_summary(self):
        b = {"nodes": [self._node("file:a.py")], "edges": []}
        _, report = self.gm.merge([b])
        report_str = "\n".join(report)
        self.assertIn("Input:", report_str)
        self.assertIn("Output:", report_str)

    def test_recover_imports_from_scan(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            scan_path = Path(d) / "scan-result.json"
            scan_path.write_text(json.dumps({
                "importMap": {"src/a.ts": ["src/b.ts"], "src/c.ts": ["src/d.ts"]}
            }))
            assembled = {
                "nodes": [
                    {"id": "file:src/a.ts", "type": "file"},
                    {"id": "file:src/b.ts", "type": "file"},
                    # src/c.ts + src/d.ts intentionally absent → should skip
                ],
                "edges": [],
            }
            recovered, lines = self.gm.recover_imports(assembled, scan_path)
            gc.collect()
            self.assertEqual(recovered, 1)
            edges = [e for e in assembled["edges"] if e["type"] == "imports"]
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0]["source"], "file:src/a.ts")
            self.assertEqual(edges[0]["target"], "file:src/b.ts")

    def test_recover_imports_no_scan_file(self):
        assembled = {"nodes": [], "edges": []}
        recovered, lines = self.gm.recover_imports(assembled, Path("nonexistent.json"))
        self.assertEqual(recovered, 0)
        self.assertTrue(any("skipped" in l for l in lines))

    def test_recover_imports_no_importmap(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            scan_path = Path(d) / "scan-result.json"
            scan_path.write_text(json.dumps({"other": "data"}))
            assembled = {"nodes": [], "edges": []}
            recovered, lines = self.gm.recover_imports(assembled, scan_path)
            gc.collect()
            self.assertEqual(recovered, 0)

    def test_recover_imports_skip_duplicates(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            scan_path = Path(d) / "scan-result.json"
            scan_path.write_text(json.dumps({"importMap": {"src/a.ts": ["src/b.ts"]}}))
            assembled = {
                "nodes": [{"id": "file:src/a.ts", "type": "file"}, {"id": "file:src/b.ts", "type": "file"}],
                "edges": [{"source": "file:src/a.ts", "target": "file:src/b.ts",
                           "type": "imports", "direction": "forward", "weight": 0.5}],
            }
            recovered, _ = self.gm.recover_imports(assembled, scan_path)
            gc.collect()
            self.assertEqual(recovered, 0)


# ══════════════════════════════════════════════════════════════════════════════
# SubgraphMerger tests
# ══════════════════════════════════════════════════════════════════════════════

class TestSubgraphMerger(unittest.TestCase):

    def setUp(self):
        from core.knowledge.graph_merger import SubgraphMerger
        self.sm = SubgraphMerger()

    def _graph(self, nodes, edges, layers=None, tour=None, project=None):
        return {
            "nodes": nodes, "edges": edges,
            "layers": layers or [], "tour": tour or [],
            "project": project or {"name": "proj", "languages": ["python"],
                                   "frameworks": [], "description": "desc",
                                   "analyzedAt": "2026-01-01T00:00:00+00:00",
                                   "gitCommitHash": ""},
        }

    def _node(self, nid, ntype="article"):
        return {"id": nid, "type": ntype, "name": nid}

    def _edge(self, src, tgt, etype="related", weight=0.5):
        return {"source": src, "target": tgt, "type": etype, "weight": weight}

    def test_merge_empty(self):
        merged, report = self.sm.merge([])
        self.assertEqual(len(merged["nodes"]), 0)
        self.assertEqual(len(merged["edges"]), 0)

    def test_single_graph_passthrough(self):
        g = self._graph([self._node("article:a")], [])
        merged, _ = self.sm.merge([g])
        self.assertEqual(len(merged["nodes"]), 1)

    def test_node_dedup_last_wins(self):
        g1 = self._graph([{"id": "article:a", "type": "article", "name": "v1"}], [])
        g2 = self._graph([{"id": "article:a", "type": "article", "name": "v2"}], [])
        merged, _ = self.sm.merge([g1, g2])
        self.assertEqual(len(merged["nodes"]), 1)
        self.assertEqual(merged["nodes"][0]["name"], "v2")

    def test_edge_dedup_higher_weight_wins(self):
        nodes = [self._node("article:a"), self._node("article:b")]
        g1 = self._graph(nodes, [self._edge("article:a", "article:b", weight=0.3)])
        g2 = self._graph(nodes, [self._edge("article:a", "article:b", weight=0.9)])
        merged, _ = self.sm.merge([g1, g2])
        self.assertEqual(len(merged["edges"]), 1)
        self.assertEqual(merged["edges"][0]["weight"], 0.9)

    def test_dangling_edge_dropped(self):
        g = self._graph(
            [self._node("article:a")],
            [self._edge("article:a", "article:ghost")],
        )
        merged, _ = self.sm.merge([g])
        self.assertEqual(len(merged["edges"]), 0)

    def test_layer_union(self):
        nodes = [self._node("article:a"), self._node("article:b")]
        g1 = self._graph(nodes, [], layers=[{"id": "layer:x", "name": "X", "nodeIds": ["article:a"]}])
        g2 = self._graph(nodes, [], layers=[{"id": "layer:x", "name": "X", "nodeIds": ["article:b"]}])
        merged, _ = self.sm.merge([g1, g2])
        layer_x = next(l for l in merged["layers"] if l["id"] == "layer:x")
        self.assertIn("article:a", layer_x["nodeIds"])
        self.assertIn("article:b", layer_x["nodeIds"])

    def test_dangling_layer_refs_dropped(self):
        g = self._graph(
            [self._node("article:a")],
            [],
            layers=[{"id": "layer:x", "name": "X", "nodeIds": ["article:a", "article:ghost"]}],
        )
        merged, _ = self.sm.merge([g])
        layer_x = next(l for l in merged["layers"] if l["id"] == "layer:x")
        self.assertNotIn("article:ghost", layer_x["nodeIds"])

    def test_tour_merge_same_title(self):
        nodes = [self._node("article:a"), self._node("article:b")]
        g1 = self._graph(
            nodes, [],
            tour=[{"title": "Intro", "order": 1, "nodeIds": ["article:a"], "description": "Short"}],
        )
        g2 = self._graph(
            nodes, [],
            tour=[{"title": "Intro", "order": 1, "nodeIds": ["article:b"], "description": "Longer description"}],
        )
        merged, _ = self.sm.merge([g1, g2])
        intro = [s for s in merged["tour"] if s["title"] == "Intro"]
        self.assertEqual(len(intro), 1)
        self.assertIn("article:a", intro[0]["nodeIds"])
        self.assertIn("article:b", intro[0]["nodeIds"])
        self.assertEqual(intro[0]["description"], "Longer description")

    def test_tour_reordered(self):
        nodes = [self._node("article:a"), self._node("article:b")]
        g = self._graph(
            nodes, [],
            tour=[
                {"title": "Second", "order": 2, "nodeIds": ["article:b"], "description": ""},
                {"title": "First", "order": 1, "nodeIds": ["article:a"], "description": ""},
            ],
        )
        merged, _ = self.sm.merge([g])
        for i, step in enumerate(merged["tour"], start=1):
            self.assertEqual(step["order"], i)

    def test_project_languages_merged(self):
        g1 = self._graph([], [], project={"name": "P", "languages": ["python"],
                                           "frameworks": [], "description": "D1",
                                           "analyzedAt": "2026-01-01T00:00:00+00:00", "gitCommitHash": ""})
        g2 = self._graph([], [], project={"name": "P", "languages": ["typescript"],
                                           "frameworks": [], "description": "D2",
                                           "analyzedAt": "2026-06-01T00:00:00+00:00", "gitCommitHash": ""})
        merged, _ = self.sm.merge([g1, g2])
        self.assertIn("python", merged["project"]["languages"])
        self.assertIn("typescript", merged["project"]["languages"])

    def test_project_latest_analyzed_at(self):
        g1 = self._graph([], [], project={"name": "P", "languages": [], "frameworks": [],
                                           "description": "", "analyzedAt": "2026-01-01T00:00:00+00:00",
                                           "gitCommitHash": "old"})
        g2 = self._graph([], [], project={"name": "P", "languages": [], "frameworks": [],
                                           "description": "", "analyzedAt": "2026-06-01T00:00:00+00:00",
                                           "gitCommitHash": "new"})
        merged, _ = self.sm.merge([g1, g2])
        self.assertEqual(merged["project"]["gitCommitHash"], "new")

    def test_merged_has_required_keys(self):
        merged, _ = self.sm.merge([])
        for key in ("version", "nodes", "edges", "layers", "tour", "project"):
            self.assertIn(key, merged)

    def test_report_summary_line(self):
        g = self._graph([self._node("article:a")], [])
        _, report = self.sm.merge([g])
        report_str = "\n".join(report)
        self.assertIn("Input:", report_str)
        self.assertIn("Output:", report_str)

    def test_node_missing_id_reported(self):
        g = self._graph([{"type": "article", "name": "no-id"}], [])
        merged, report = self.sm.merge([g])
        self.assertEqual(len(merged["nodes"]), 0)
        self.assertTrue(any("missing" in l.lower() for l in report))


# ══════════════════════════════════════════════════════════════════════════════
# Integration: WikiParser → WikiMerger pipeline
# ══════════════════════════════════════════════════════════════════════════════

class TestKnowledgePipeline(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        _make_wiki(self.root)
        from core.knowledge.wiki_parser import WikiParser
        from core.knowledge.wiki_merger import WikiMerger
        self.parser = WikiParser()
        self.merger = WikiMerger()

    def tearDown(self):
        gc.collect()
        self._tmp.cleanup()

    def test_parser_to_merger_pipeline(self):
        manifest = self.parser.parse(self.root)
        graph = self.merger.merge(self.root, manifest)
        # All article node IDs from manifest should be in graph
        manifest_article_ids = {n["id"] for n in manifest["nodes"] if n["type"] == "article"}
        graph_node_ids = {n["id"] for n in graph["nodes"]}
        for aid in manifest_article_ids:
            self.assertIn(aid, graph_node_ids)

    def test_pipeline_graph_valid_structure(self):
        manifest = self.parser.parse(self.root)
        graph = self.merger.merge(self.root, manifest)
        self.assertIn("version", graph)
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertIn("layers", graph)
        self.assertIn("tour", graph)

    def test_all_edge_endpoints_exist(self):
        manifest = self.parser.parse(self.root)
        graph = self.merger.merge(self.root, manifest)
        node_ids = {n["id"] for n in graph["nodes"]}
        for edge in graph["edges"]:
            self.assertIn(edge["source"], node_ids,
                          f"Edge source {edge['source']} not in nodes")
            self.assertIn(edge["target"], node_ids,
                          f"Edge target {edge['target']} not in nodes")

    def test_all_layer_node_refs_exist(self):
        manifest = self.parser.parse(self.root)
        graph = self.merger.merge(self.root, manifest)
        node_ids = {n["id"] for n in graph["nodes"]}
        for layer in graph["layers"]:
            for nid in layer["nodeIds"]:
                self.assertIn(nid, node_ids,
                              f"Layer {layer['id']} references missing node {nid}")

    def test_parse_to_file_then_merge_from_disk(self):
        # Write manifest to disk
        manifest_path = self.parser.parse_to_file(self.root)
        self.assertTrue(manifest_path.exists())
        # Read back and merge
        manifest = json.loads(manifest_path.read_text())
        graph = self.merger.merge(self.root, manifest)
        self.assertGreater(len(graph["nodes"]), 0)


# ══════════════════════════════════════════════════════════════════════════════
# __init__.py imports
# ══════════════════════════════════════════════════════════════════════════════

class TestKnowledgeInit(unittest.TestCase):

    def test_imports(self):
        from core.knowledge import DomainExtractor, DomainContext
        from core.knowledge import WikiParser
        from core.knowledge import WikiMerger
        from core.knowledge import GraphMerger, SubgraphMerger
        self.assertTrue(callable(DomainExtractor))
        self.assertTrue(callable(WikiParser))
        self.assertTrue(callable(WikiMerger))
        self.assertTrue(callable(GraphMerger))
        self.assertTrue(callable(SubgraphMerger))


if __name__ == "__main__":
    unittest.main(verbosity=2)
