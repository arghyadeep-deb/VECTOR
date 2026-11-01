"""
VECTOR WikiMerger — assembles Karpathy-wiki scan manifest with LLM analysis batches.

Adapted from Understand-Anything-main (MIT) — Python algorithm reimplementation.

Combines a deterministic scan-manifest.json with LLM analysis-batch-*.json files
into a final assembled graph with entity deduplication, edge normalization, layer
building from index.md categories, and tour generation.

Usage:
    merger = WikiMerger()
    graph = merger.merge(wiki_root, batches=[{"nodes": [...], "edges": [...]}])
    # or from files on disk:
    graph = merger.merge_from_disk(wiki_root)
"""
from __future__ import annotations

__all__ = ["WikiMerger"]

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# ── Canonical type sets ────────────────────────────────────────────────────

_VALID_NODE_TYPES = {
    "article", "entity", "topic", "claim", "source",
    "file", "function", "class", "module", "concept",
    "config", "document", "service", "table", "endpoint",
    "pipeline", "schema", "resource", "domain", "flow", "step",
}

_VALID_EDGE_TYPES = {
    "cites", "contradicts", "builds_on", "exemplifies",
    "categorized_under", "authored_by", "related", "similar_to",
    "imports", "exports", "contains", "inherits", "implements",
    "calls", "subscribes", "publishes", "middleware",
    "reads_from", "writes_to", "transforms", "validates",
    "depends_on", "tested_by", "configures",
    "deploys", "serves", "provisions", "triggers",
    "migrates", "documents", "routes", "defines_schema",
    "contains_flow", "flow_step", "cross_domain",
}

_NODE_TYPE_ALIASES = {
    "note": "article", "page": "article", "wiki_page": "article",
    "person": "entity", "actor": "entity", "organization": "entity",
    "tag": "topic", "category": "topic", "theme": "topic",
    "assertion": "claim", "decision": "claim", "thesis": "claim",
    "reference": "source", "raw": "source", "paper": "source",
}

_EDGE_TYPE_ALIASES = {
    "references": "cites", "cites_source": "cites",
    "conflicts_with": "contradicts", "disagrees_with": "contradicts",
    "refines": "builds_on", "elaborates": "builds_on",
    "illustrates": "exemplifies", "instance_of": "exemplifies", "example_of": "exemplifies",
    "belongs_to": "categorized_under", "tagged_with": "categorized_under",
    "written_by": "authored_by", "created_by": "authored_by",
    "relates_to": "related", "related_to": "related",
}


def _normalize_node_type(t: str) -> str:
    t = t.lower().strip()
    return _NODE_TYPE_ALIASES.get(t, t)


def _normalize_edge_type(t: str) -> str:
    t = t.lower().strip()
    return _EDGE_TYPE_ALIASES.get(t, t)


def _normalize_entity_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


class WikiMerger:
    """
    Assembles a scan manifest with LLM analysis batches into a final knowledge graph.

    Two entry points:
      merge(root, manifest, batches) — takes already-loaded dicts
      merge_from_disk(root)          — loads manifest + batches from .understand-anything/
    """

    # ── Public API ─────────────────────────────────────────────────────────

    def merge(
        self,
        root: Path,
        manifest: dict[str, Any],
        batches: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Merge manifest with optional LLM batches into an assembled graph.

        Args:
            root:     Wiki root directory (used for project name detection + git hash).
            manifest: Scan manifest produced by WikiParser (nodes, edges, categories).
            batches:  LLM analysis batches (each: {nodes: [...], edges: [...]}).

        Returns:
            Assembled graph dict (version, kind, project, nodes, edges, layers, tour).
        """
        batches = batches or []

        nodes: dict[str, Any] = {n["id"]: n for n in manifest.get("nodes", [])}
        edges: list[dict[str, Any]] = list(manifest.get("edges", []))
        categories = manifest.get("categories", [])

        report = {
            "base_nodes": len(nodes),
            "base_edges": len(edges),
            "batches": len(batches),
            "new_entities": 0, "new_claims": 0,
            "new_edges": 0, "deduped_entities": 0, "dropped_edges": 0,
        }

        entity_name_map: dict[str, str] = {}  # normalized_name → entity_id
        dedup_remap: dict[str, str] = {}       # duplicate_id → canonical_id

        for batch in batches:
            self._process_batch(batch, nodes, edges, entity_name_map, dedup_remap, report)

        final_edges = self._dedup_edges(edges)
        layers = self._build_layers(categories, final_edges, nodes)
        tour = self._build_tour(categories, final_edges, nodes)
        project_name = self._detect_project_name(root)

        graph = {
            "version": "1.0.0",
            "kind": "knowledge",
            "project": {
                "name": project_name,
                "languages": ["markdown"],
                "frameworks": ["karpathy-wiki"],
                "description": f"Knowledge graph for {project_name}",
                "analyzedAt": datetime.now(timezone.utc).isoformat(),
                "gitCommitHash": self._git_hash(root),
            },
            "nodes": list(nodes.values()),
            "edges": final_edges,
            "layers": layers,
            "tour": tour,
        }

        logger.debug(
            "[VECTOR][knowledge] WikiMerger: {} nodes, {} edges, {} layers, {} tour steps",
            len(graph["nodes"]), len(final_edges), len(layers), len(tour),
        )
        logger.debug(
            "[VECTOR][knowledge] WikiMerger: +{} entities, +{} claims, +{} edges "
            "({} deduped, {} dropped)",
            report["new_entities"], report["new_claims"], report["new_edges"],
            report["deduped_entities"], report["dropped_edges"],
        )
        return graph

    def merge_from_disk(self, root: Path) -> dict[str, Any]:
        """Load scan-manifest.json + analysis-batch-*.json from disk and merge."""
        root = Path(root)
        intermediate = root / ".understand-anything" / "intermediate"
        manifest_path = intermediate / "scan-manifest.json"

        if not manifest_path.is_file():
            raise FileNotFoundError(
                f"scan-manifest.json not found at {manifest_path}. "
                "Run WikiParser.parse_to_file() first."
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        batches: list[dict[str, Any]] = []
        for bf in sorted(intermediate.glob("analysis-batch-*.json")):
            try:
                batch = json.loads(bf.read_text(encoding="utf-8"))
                batches.append(batch)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("[VECTOR][knowledge] WikiMerger: skipping {}: {}", bf.name, e)

        return self.merge(root, manifest, batches)

    def write(self, root: Path, graph: dict[str, Any]) -> Path:
        """Write assembled graph JSON to .understand-anything/intermediate/assembled-graph.json."""
        out = root / ".understand-anything" / "intermediate" / "assembled-graph.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(graph, indent=2), encoding="utf-8")
        size_kb = len(json.dumps(graph).encode()) / 1024
        logger.info("[VECTOR][knowledge] WikiMerger: written {:.0f} KB → {}", size_kb, out)
        return out

    # ── Internal helpers ───────────────────────────────────────────────────

    def _process_batch(
        self,
        batch: dict[str, Any],
        nodes: dict[str, Any],
        edges: list[dict[str, Any]],
        entity_name_map: dict[str, str],
        dedup_remap: dict[str, str],
        report: dict[str, int],
    ) -> None:
        for node in (batch.get("nodes") or []):
            node_type = _normalize_node_type(node.get("type", ""))
            if node_type not in _VALID_NODE_TYPES:
                logger.warning("[VECTOR][knowledge] WikiMerger: unknown node type '{}' — skipping", node.get("type"))
                continue
            node["type"] = node_type
            node_id = node.get("id", "")

            if node_type == "entity":
                norm_name = _normalize_entity_name(node.get("name", ""))
                if norm_name in entity_name_map:
                    dedup_remap[node_id] = entity_name_map[norm_name]
                    report["deduped_entities"] += 1
                    continue
                entity_name_map[norm_name] = node_id
                report["new_entities"] += 1
            elif node_type == "claim":
                report["new_claims"] += 1

            node.setdefault("summary", node.get("name", ""))
            node.setdefault("tags", [])
            node.setdefault("complexity", "simple")
            nodes[node_id] = node

        for edge in (batch.get("edges") or []):
            edge_type = _normalize_edge_type(edge.get("type", ""))
            if edge_type not in _VALID_EDGE_TYPES:
                edge_type = "related"
            edge["type"] = edge_type
            edge.setdefault("direction", "forward")
            edge.setdefault("weight", 0.5)

            src = dedup_remap.get(edge.get("source", ""), edge.get("source", ""))
            tgt = dedup_remap.get(edge.get("target", ""), edge.get("target", ""))
            edge["source"] = src
            edge["target"] = tgt
            if src in nodes and tgt in nodes:
                edges.append(edge)
                report["new_edges"] += 1
            else:
                report["dropped_edges"] += 1

    def _dedup_edges(self, edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str]] = set()
        result = []
        for edge in edges:
            key = (edge["source"], edge["target"], edge["type"])
            if key not in seen:
                seen.add(key)
                result.append(edge)
        return result

    def _build_layers(
        self,
        categories: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        nodes: dict[str, Any],
    ) -> list[dict[str, Any]]:
        article_layer_map: dict[str, str] = {}
        layer_members: dict[str, list[str]] = {}

        for cat in categories:
            cat_slug = cat["name"].lower().replace(" ", "-")
            layer_id = f"layer:{cat_slug}"
            topic_id = f"topic:{cat_slug}"
            members = [
                e["source"] for e in edges
                if e["type"] == "categorized_under" and e["target"] == topic_id
            ]
            if topic_id in nodes:
                members.append(topic_id)
            layer_members[layer_id] = members
            for mid in members:
                article_layer_map[mid] = layer_id

        # Map entity/claim children to parent article's layer
        child_to_article = self._map_children_to_articles(edges, nodes)
        for child_id, article_id in child_to_article.items():
            layer_id = article_layer_map.get(article_id)
            if layer_id and layer_id in layer_members:
                layer_members[layer_id].append(child_id)
                article_layer_map[child_id] = layer_id

        layers = []
        for cat in categories:
            cat_name = cat["name"]
            cat_slug = cat_name.lower().replace(" ", "-")
            layer_id = f"layer:{cat_slug}"
            members = list(dict.fromkeys(layer_members.get(layer_id, [])))
            layers.append({
                "id": layer_id,
                "name": cat_name,
                "description": f"{cat_name} ({len(members)} nodes)",
                "nodeIds": members,
            })

        # "Other" layer for uncategorized
        categorized = set(nid for layer in layers for nid in layer["nodeIds"])
        uncategorized = [nid for nid in nodes if nid not in categorized]
        if uncategorized:
            layers.append({
                "id": "layer:other",
                "name": "Other",
                "description": f"Uncategorized nodes ({len(uncategorized)})",
                "nodeIds": uncategorized,
            })

        return layers

    def _map_children_to_articles(
        self,
        edges: list[dict[str, Any]],
        nodes: dict[str, Any],
    ) -> dict[str, str]:
        child_to_article: dict[str, str] = {}

        # Direct edge connections
        for edge in edges:
            src_type = nodes.get(edge["source"], {}).get("type", "")
            tgt_type = nodes.get(edge["target"], {}).get("type", "")
            if src_type == "article" and tgt_type in ("entity", "claim"):
                child_to_article.setdefault(edge["target"], edge["source"])
            elif tgt_type == "article" and src_type in ("entity", "claim"):
                child_to_article.setdefault(edge["source"], edge["target"])

        # ID-stem matching for orphan children
        bare_to_article: dict[str, str] = {}
        for nid in nodes:
            if nid.startswith("article:"):
                bare = nid.split("/")[-1] if "/" in nid else nid.replace("article:", "")
                bare_to_article[bare] = nid

        for nid, node in nodes.items():
            if node["type"] not in ("entity", "claim") or nid in child_to_article:
                continue
            raw = nid.split(":", 1)[1] if ":" in nid else nid
            stem = raw.split(":")[0]

            if stem in bare_to_article:
                child_to_article[nid] = bare_to_article[stem]
                continue

            for bare, aid in bare_to_article.items():
                if stem in bare or bare in stem or bare.endswith(f"-{stem}"):
                    child_to_article[nid] = aid
                    break

        return child_to_article

    def _build_tour(
        self,
        categories: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        nodes: dict[str, Any],
    ) -> list[dict[str, Any]]:
        tour = []
        for i, cat in enumerate(categories):
            cat_slug = cat["name"].lower().replace(" ", "-")
            topic_id = f"topic:{cat_slug}"
            members = [
                e["source"] for e in edges
                if e["type"] == "categorized_under" and e["target"] == topic_id
            ][:3]
            if not members and topic_id in nodes:
                members = [topic_id]
            if members:
                tour.append({
                    "order": i + 1,
                    "title": cat["name"],
                    "description": f"Explore the {cat['name']} section ({cat.get('count', len(members))} articles)",
                    "nodeIds": members,
                })
        return tour

    def _detect_project_name(self, root: Path) -> str:
        for candidate in (root / "wiki" / "index.md", root / "index.md"):
            if candidate.is_file():
                text = candidate.read_text(encoding="utf-8", errors="replace")
                m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
                if m:
                    return m.group(1).strip()
        return root.name

    def _git_hash(self, root: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, cwd=str(root), timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return ""


if __name__ == "__main__":
    import tempfile
    import gc

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        root = Path(d)
        (root / "wiki").mkdir()

        # Minimal scan manifest
        manifest = {
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

        # Batch with a new entity + edge
        batch = {
            "nodes": [
                {"id": "entity:python", "type": "entity", "name": "Python",
                 "summary": "Programming language", "tags": [], "complexity": "simple"},
            ],
            "edges": [
                {"source": "article:wiki/intro", "target": "entity:python",
                 "type": "related", "direction": "forward", "weight": 0.8},
            ],
        }

        merger = WikiMerger()
        graph = merger.merge(root, manifest, [batch])

        assert graph["version"] == "1.0.0"
        assert graph["kind"] == "knowledge"
        node_ids = {n["id"] for n in graph["nodes"]}
        assert "article:wiki/intro" in node_ids
        assert "entity:python" in node_ids
        assert len(graph["edges"]) == 2
        assert len(graph["layers"]) >= 1
        layer_basics = next((l for l in graph["layers"] if l["id"] == "layer:basics"), None)
        assert layer_basics is not None
        assert "article:wiki/intro" in layer_basics["nodeIds"]

        # Entity deduplication — adding same entity twice should only keep one
        batch2 = {
            "nodes": [
                {"id": "entity:python-dup", "type": "entity", "name": "Python",
                 "summary": "Dup", "tags": [], "complexity": "simple"},
            ],
            "edges": [],
        }
        graph2 = merger.merge(root, manifest, [batch, batch2])
        python_nodes = [n for n in graph2["nodes"] if n["type"] == "entity" and n["name"] == "Python"]
        assert len(python_nodes) == 1, "Entity deduplication failed"

        # Dangling edge (target not in nodes) should be dropped
        batch3 = {
            "nodes": [],
            "edges": [
                {"source": "article:wiki/intro", "target": "entity:nonexistent",
                 "type": "related", "direction": "forward", "weight": 0.5},
            ],
        }
        graph3 = merger.merge(root, manifest, [batch3])
        dangling = [e for e in graph3["edges"] if e.get("target") == "entity:nonexistent"]
        assert len(dangling) == 0, "Dangling edge not dropped"

        gc.collect()

    print("OK wiki_merger.py — merge, entity dedup, dangling edge drop, layer assignment verified")
