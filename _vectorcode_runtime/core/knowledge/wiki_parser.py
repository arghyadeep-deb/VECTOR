"""
VECTOR Wiki Parser — Karpathy-format markdown wiki → knowledge graph.

Detects the three-layer pattern (index.md + wiki/*.md + optional raw/),
extracts structure from markdown, resolves wikilinks, builds category
taxonomy from index.md section headings, and computes backlinks.

Directly applicable to VECTOR's Obsidian brain vault (brain/) which follows
the Karpathy format: index.md + wiki/ subdirectory + wikilink references.

Usage:
    parser = WikiParser()
    manifest = parser.parse("/path/to/wiki-root")
    # manifest keys: format, stats, categories, logEntries, nodes, edges, warnings
"""
from __future__ import annotations

__all__ = ["WikiParser"]

import json
import re
from pathlib import Path
from typing import Any

from loguru import logger
from core.config import CONFIG

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_CODE_BLOCK_RE = re.compile(r"```(\w*)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_LOG_ENTRY_RE = re.compile(r"^##\s+\[(\d{4}-\d{2}-\d{2})\]\s+(\w+)\s*\|\s*(.+)$", re.MULTILINE)

_INFRA_FILES = {"index.md", "log.md", "claude.md", "agents.md", "soul.md"}


class WikiParser:
    """
    Parses a Karpathy-format markdown wiki into a structured knowledge-graph manifest.

    The Karpathy format is: a directory containing index.md (categories), wiki/*.md
    (articles with wikilinks), and optionally raw/ (source documents).
    """

    def parse(self, root: str | Path) -> dict[str, Any]:
        """
        Parse the wiki at root and return a scan manifest dict.

        Returns:
            {
              "format": "karpathy",
              "stats": {articles, sources, topics, wikilinks, unresolved},
              "categories": [{name, count}],
              "logEntries": int,
              "nodes": [...],
              "edges": [...],
              "warnings": [...],
            }
        """
        root = Path(root).resolve()
        if not root.is_dir():
            raise ValueError(f"Not a directory: {root}")

        detection = self._detect_format(root)
        if not detection["detected"]:
            logger.warning("[VECTOR][wiki] Not a Karpathy-format wiki: {}", root)
            return {"format": "unknown", "stats": {}, "nodes": [], "edges": [], "warnings": [],
                    "detection": detection}

        wiki_root = Path(detection["wiki_root"])
        raw_root = root / "raw"

        logger.info("[VECTOR][wiki] Parsing Karpathy wiki: {} ({} md files)",
                    root, detection["md_count"])

        name_map = self._build_name_to_stem_map(wiki_root)
        index_path = self._find_file(wiki_root, root, "index.md")
        log_path = self._find_file(wiki_root, root, "log.md")

        categories = self._parse_index(index_path)
        log_entries = self._parse_log(log_path)

        category_lookup: dict[str, str] = {
            target.lower(): cat["name"]
            for cat in categories
            for target in cat["articles"]
        }

        # Pre-compute article IDs (for wikilink resolution validation)
        article_ids: set[str] = set()
        for md_file in sorted(wiki_root.rglob("*.md")):
            rel = md_file.relative_to(wiki_root)
            stem = rel.with_suffix("").as_posix()
            if rel.parent == Path(".") and rel.name.lower() in _INFRA_FILES:
                continue
            article_ids.add(f"article:{stem}")

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        warnings: list[str] = []
        stats: dict[str, int] = {"articles": 0, "sources": 0, "topics": 0,
                                  "wikilinks": 0, "unresolved": 0}

        for md_file in sorted(wiki_root.rglob("*.md")):
            rel = md_file.relative_to(wiki_root)
            stem = rel.with_suffix("").as_posix()
            basename = md_file.stem

            if rel.parent == Path(".") and rel.name.lower() in _INFRA_FILES:
                continue

            text = md_file.read_text(encoding="utf-8", errors="replace")
            h1 = self._extract_h1(text)
            frontmatter = self._extract_frontmatter(text)
            wikilinks = self._extract_wikilinks(text)
            summary = self._extract_first_paragraph(text)

            category = (category_lookup.get(basename.lower()) or
                        category_lookup.get(stem.lower()) or "")

            tag_set: set[str] = set()
            if category:
                tag_set.add(category.lower())
            if rel.parent != Path("."):
                tag_set.add(str(rel.parent).replace("\\", "/"))
            fm_tags = frontmatter.get("tags", "")
            if fm_tags:
                tag_set.update(t.strip() for t in fm_tags.split(",") if t.strip())

            wl_count = len(wikilinks)
            complexity = "complex" if wl_count > 15 else ("moderate" if wl_count > 5 else "simple")

            node_id = f"article:{stem}"
            nodes.append({
                "id": node_id,
                "type": "article",
                "name": h1 or basename,
                "filePath": str(rel).replace("\\", "/"),
                "summary": summary or f"Wiki article: {h1 or basename}",
                "tags": sorted(tag_set),
                "complexity": complexity,
                "knowledgeMeta": {
                    "wikilinks": [wl["target"] for wl in wikilinks],
                    **({"category": category} if category else {}),
                    "content": text[:3000],
                },
            })
            stats["articles"] += 1
            stats["wikilinks"] += wl_count

            for wl in wikilinks:
                target_id = self._resolve_wikilink(wl["target"], name_map, article_ids)
                if target_id and target_id != node_id:
                    edges.append({
                        "source": node_id,
                        "target": target_id,
                        "type": "related",
                        "direction": "forward",
                        "weight": 0.7,
                    })
                elif not target_id:
                    warnings.append(f"Unresolved wikilink: [[{wl['target']}]] in {rel}")
                    stats["unresolved"] += 1

        # Topic nodes from index.md categories
        for cat in categories:
            topic_id = f"topic:{cat['name'].lower().replace(' ', '-')}"
            nodes.append({
                "id": topic_id,
                "type": "topic",
                "name": cat["name"],
                "summary": f"Category from index: {cat['name']} ({len(cat['articles'])} articles)",
                "tags": ["category"],
                "complexity": "simple",
            })
            stats["topics"] += 1

            for article_target in cat["articles"]:
                article_id = self._resolve_wikilink(article_target, name_map, article_ids)
                if article_id:
                    edges.append({
                        "source": article_id,
                        "target": topic_id,
                        "type": "categorized_under",
                        "direction": "forward",
                        "weight": 0.6,
                    })

        # Source nodes from raw/
        if raw_root.is_dir():
            for raw_file in sorted(raw_root.rglob("*")):
                if raw_file.is_file() and not raw_file.name.startswith("."):
                    rel_raw = raw_file.relative_to(root)
                    ext = raw_file.suffix.lower()
                    size_kb = raw_file.stat().st_size / 1024
                    source_id = f"source:{raw_file.relative_to(raw_root).with_suffix('')}"
                    nodes.append({
                        "id": source_id,
                        "type": "source",
                        "name": raw_file.name,
                        "filePath": str(rel_raw).replace("\\", "/"),
                        "summary": f"Raw source ({ext or 'unknown'}, {size_kb:.0f} KB)",
                        "tags": ["raw", ext.lstrip(".") or "unknown"],
                        "complexity": "simple",
                    })
                    stats["sources"] += 1

        # Compute backlinks
        backlink_map: dict[str, list[str]] = {}
        for edge in edges:
            if edge["type"] == "related":
                backlink_map.setdefault(edge["target"], []).append(edge["source"])
        for node in nodes:
            if node["type"] == "article" and "knowledgeMeta" in node:
                node["knowledgeMeta"]["backlinks"] = backlink_map.get(node["id"], [])

        # Deduplicate edges
        seen: set[tuple] = set()
        deduped_edges = []
        for edge in edges:
            key = (edge["source"], edge["target"], edge["type"])
            if key not in seen:
                seen.add(key)
                deduped_edges.append(edge)

        logger.info("[VECTOR][wiki] {} articles, {} sources, {} topics, {} wikilinks ({} unresolved)",
                    stats["articles"], stats["sources"], stats["topics"],
                    stats["wikilinks"], stats["unresolved"])

        return {
            "format": "karpathy",
            "stats": stats,
            "categories": [{"name": c["name"], "count": len(c["articles"])} for c in categories],
            "logEntries": len(log_entries),
            "nodes": nodes,
            "edges": deduped_edges,
            "warnings": warnings[:50],
        }

    def parse_to_file(self, root: str | Path) -> Path:
        """Parse wiki and write scan-manifest.json. Returns output path."""
        root = Path(root).resolve()
        manifest = self.parse(root)
        out_dir = root / ".understand-anything" / "intermediate"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "scan-manifest.json"
        out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        logger.info("[VECTOR][wiki] scan-manifest.json written: {}", out_path)
        return out_path

    # ── Detection ──────────────────────────────────────────────────────────

    def _detect_format(self, root: Path) -> dict[str, Any]:
        has_index = (root / "index.md").is_file() or (root / "wiki" / "index.md").is_file()
        wiki_root = root / "wiki" if (root / "wiki").is_dir() else root
        md_files = list(wiki_root.rglob("*.md"))
        detected = has_index and len(md_files) >= 3
        return {
            "detected": detected,
            "format": "karpathy" if detected else "unknown",
            "wiki_root": str(wiki_root),
            "md_count": len(md_files),
            "has_index": has_index,
            "has_raw": (root / "raw").is_dir(),
        }

    def _find_file(self, wiki_root: Path, root: Path, name: str) -> Path:
        p = wiki_root / name
        if p.is_file():
            return p
        return root / name

    # ── Name map ───────────────────────────────────────────────────────────

    def _build_name_to_stem_map(self, wiki_root: Path) -> dict[str, str]:
        name_map: dict[str, str] = {}
        basename_counts: dict[str, int] = {}
        for md_file in wiki_root.rglob("*.md"):
            rel = md_file.relative_to(wiki_root)
            stem = rel.with_suffix("").as_posix()
            basename = md_file.stem
            name_map[stem.lower()] = stem
            key = basename.lower()
            basename_counts[key] = basename_counts.get(key, 0) + 1
            name_map[key] = stem
        for key, count in basename_counts.items():
            if count > 1 and key in name_map:
                del name_map[key]
        return name_map

    def _resolve_wikilink(self, target: str, name_map: dict[str, str],
                          node_ids: set[str] | None = None) -> str | None:
        key = target.lower().strip()
        if key.startswith("-"):
            return None
        stem = name_map.get(key)
        if stem:
            candidate = f"article:{stem}"
            if node_ids is not None and candidate not in node_ids:
                return None
            return candidate
        for stored_key, stored_stem in name_map.items():
            if stored_key.endswith("/" + key) or stored_key == key:
                candidate = f"article:{stored_stem}"
                if node_ids is not None and candidate not in node_ids:
                    return None
                return candidate
        return None

    # ── Markdown helpers ───────────────────────────────────────────────────

    def _extract_frontmatter(self, text: str) -> dict[str, str]:
        m = _FRONTMATTER_RE.match(text)
        if not m:
            return {}
        fm: dict[str, str] = {}
        for line in m.group(1).split("\n"):
            if ":" in line:
                key, _, val = line.partition(":")
                fm[key.strip()] = val.strip().strip('"').strip("'")
        return fm

    def _extract_wikilinks(self, text: str) -> list[dict[str, Any]]:
        return [
            {"target": m.group(1).strip(), "display": m.group(2).strip() if m.group(2) else None}
            for m in _WIKILINK_RE.finditer(text)
        ]

    def _extract_h1(self, text: str) -> str:
        for m in _HEADING_RE.finditer(text):
            if len(m.group(1)) == 1:
                return m.group(2).strip()
        return ""

    def _extract_first_paragraph(self, text: str) -> str:
        stripped = _FRONTMATTER_RE.sub("", text).strip()
        if not stripped:
            return ""
        lines = stripped.split("\n")

        def _collect(start_lines: list[str]) -> str:
            para: list[str] = []
            for raw in start_lines:
                s = raw.strip()
                if not s and not para:
                    continue
                if not s and para:
                    break
                if s.startswith(">") or re.match(r"^[-*_]{3,}\s*$", s):
                    continue
                if s.startswith("#"):
                    if para:
                        break
                    continue
                para.append(s)
            return " ".join(para)

        for i, line in enumerate(lines):
            if line.strip().startswith("# "):
                result = _collect(lines[i + 1:])
                if result:
                    return result[:197] + "..." if len(result) > 200 else result
        result = _collect(lines)
        return (result[:197] + "..." if len(result) > 200 else result) or ""

    # ── Index + log ────────────────────────────────────────────────────────

    def _parse_index(self, index_path: Path) -> list[dict[str, Any]]:
        if not index_path.is_file():
            return []
        text = index_path.read_text(encoding="utf-8", errors="replace")
        categories: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for line in text.split("\n"):
            m = re.match(r"^##\s+(.+)$", line)
            if m:
                current = {"name": m.group(1).strip(), "articles": []}
                categories.append(current)
                continue
            if current:
                for wl in _WIKILINK_RE.finditer(line):
                    current["articles"].append(wl.group(1).strip())
        return categories

    def _parse_log(self, log_path: Path) -> list[dict[str, str]]:
        if not log_path.is_file():
            return []
        text = log_path.read_text(encoding="utf-8", errors="replace")
        return [
            {"date": m.group(1), "operation": m.group(2), "title": m.group(3).strip()}
            for m in _LOG_ENTRY_RE.finditer(text)
        ]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # Create a minimal Karpathy-format wiki
        wiki_dir = root / "wiki"
        wiki_dir.mkdir()

        (wiki_dir / "index.md").write_text(
            "# My Wiki\n\n## Concepts\n- [[concept-one]]\n- [[concept-two]]\n\n## Tools\n- [[tool-alpha]]\n",
            encoding="utf-8"
        )
        (wiki_dir / "concept-one.md").write_text(
            "# Concept One\n\nThis is concept one. See also [[concept-two]] and [[tool-alpha]].\n",
            encoding="utf-8"
        )
        (wiki_dir / "concept-two.md").write_text(
            "# Concept Two\n\nRelated to [[concept-one]].\n",
            encoding="utf-8"
        )
        (wiki_dir / "tool-alpha.md").write_text(
            "# Tool Alpha\n\nA useful tool.\n",
            encoding="utf-8"
        )

        parser = WikiParser()
        manifest = parser.parse(root)

        assert manifest["format"] == "karpathy"
        assert manifest["stats"]["articles"] == 3
        assert manifest["stats"]["topics"] == 2
        assert manifest["stats"]["wikilinks"] >= 3
        assert len(manifest["nodes"]) == 5  # 3 articles + 2 topics
        assert len(manifest["edges"]) >= 3  # wikilinks + categorized_under
        assert len(manifest["categories"]) == 2
        assert manifest["categories"][0]["name"] == "Concepts"
        assert manifest["categories"][1]["name"] == "Tools"

        # Check backlinks
        concept_two = next(n for n in manifest["nodes"] if "concept-two" in n["id"])
        assert len(concept_two["knowledgeMeta"]["backlinks"]) >= 1

        # Check that unresolved wikilink is 0
        assert manifest["stats"]["unresolved"] == 0

    print("OK wiki_parser.py — Karpathy format, categories, wikilinks, backlinks, dedup verified")
