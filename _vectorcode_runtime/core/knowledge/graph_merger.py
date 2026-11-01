"""
VECTOR GraphMerger — merge + normalize codebase analysis batch graphs.
VECTOR SubgraphMerger — merge multiple subdomain knowledge-graph files.

Adapted from Understand-Anything-main (MIT) — Python algorithm reimplementation.

GraphMerger:
  Combines batch-*.json files from LLM codebase analysis into a single
  assembled graph. Normalizes node IDs (double prefix, project-name prefix,
  func:→function:, bare paths), complexity values (low/medium/high → simple/
  moderate/complex), and edges. Includes a deterministic two-pass tested_by
  linker (Pass 1: flip inverted LLM edges; Pass 2: path-convention supplement).
  Recovers imports edges from importMap in scan-result.json.

SubgraphMerger:
  Merges multiple subdomain knowledge-graph JSON files into one, deduplicating
  nodes (last wins), edges (higher weight wins), and layers (union nodeIds).

Usage:
    gm = GraphMerger()
    assembled, report = gm.merge(batches)
    recovered, lines = gm.recover_imports(assembled, scan_result_path)

    sm = SubgraphMerger()
    merged, report = sm.merge(graphs)
"""
from __future__ import annotations

__all__ = ["GraphMerger", "SubgraphMerger"]

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any


# ── Node / edge type registries ────────────────────────────────────────────

_VALID_NODE_PREFIXES = {
    "file", "func", "function", "class", "module", "concept",
    "config", "document", "service", "table", "endpoint",
    "pipeline", "schema", "resource",
    "domain", "flow", "step",
    "article", "entity", "topic", "claim", "source",
}

_TYPE_TO_PREFIX: dict[str, str] = {
    "file": "file", "function": "function", "func": "function",
    "class": "class", "module": "module", "concept": "concept",
    "config": "config", "document": "document", "service": "service",
    "table": "table", "endpoint": "endpoint", "pipeline": "pipeline",
    "schema": "schema", "resource": "resource",
    "domain": "domain", "flow": "flow", "step": "step",
    "article": "article", "entity": "entity", "topic": "topic",
    "claim": "claim", "source": "source",
}

_COMPLEXITY_MAP: dict[str, str] = {
    "low": "simple", "easy": "simple",
    "medium": "moderate", "intermediate": "moderate",
    "high": "complex", "hard": "complex", "difficult": "complex",
}
_VALID_COMPLEXITY = {"simple", "moderate", "complex"}

_DIRECTION_ALIASES: dict[str, str] = {"both": "bidirectional", "mutual": "bidirectional"}
_VALID_DIRECTIONS = frozenset({"forward", "backward", "bidirectional"})

# ── JS/TS test detection config ────────────────────────────────────────────

_JS_TS_EXTS: tuple[str, ...] = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue")
_JS_TS_TEST_EXTS = frozenset(_JS_TS_EXTS)
_MIRROR_PRODUCTION_ROOTS: tuple[str, ...] = ("src", "app", "lib", "")

_TEST_NAME_PATTERNS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    ".go": ((), ("_test",)),
    ".py": (("test_",), ("_test",)),
    ".java": ((), ("Test", "Tests", "IT")),
    ".kt": ((), ("Test", "Tests")),
    ".cs": ((), ("Test", "Tests")),
    ".c": (("test_",), ("_test",)),
    ".cpp": (("test_",), ("_test",)),
    ".cc": (("test_",), ("_test",)),
}


# ── Utility functions ──────────────────────────────────────────────────────

def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _normalize_direction(value: Any) -> str:
    candidate = value.lower() if isinstance(value, str) else ""
    candidate = _DIRECTION_ALIASES.get(candidate, candidate)
    return candidate if candidate in _VALID_DIRECTIONS else "forward"


def _normalize_node_id(node_id: str, node: dict[str, Any]) -> str:
    nid = node_id

    # Strip double prefix: "file:file:src/foo.ts" → "file:src/foo.ts"
    for prefix in _VALID_NODE_PREFIXES:
        if nid.startswith(f"{prefix}:{prefix}:"):
            nid = nid[len(prefix) + 1:]
            break

    # Strip project-name prefix: "myproject:file:src/foo.ts" → "file:src/foo.ts"
    m = re.match(
        r"^[^:]+:(" + "|".join(re.escape(p) for p in _VALID_NODE_PREFIXES) + r"):(.+)$",
        nid,
    )
    if m and nid.split(":")[0] not in _VALID_NODE_PREFIXES:
        nid = f"{m.group(1)}:{m.group(2)}"

    # func: → function:
    if nid.startswith("func:") and not nid.startswith("function:"):
        nid = "function:" + nid[5:]

    # Add missing prefix for bare paths
    if not any(nid.startswith(f"{p}:") for p in _VALID_NODE_PREFIXES):
        node_type = node.get("type", "file")
        prefix = _TYPE_TO_PREFIX.get(node_type, "file")
        if node_type in ("function", "class"):
            file_path = node.get("filePath", "")
            name = node.get("name", nid)
            nid = f"{prefix}:{file_path}:{name}" if file_path else f"{prefix}:__nofilepath__:{name}"
        else:
            nid = f"{prefix}:{nid}"

    return nid


def _normalize_complexity(value: Any) -> tuple[str, str]:
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in _VALID_COMPLEXITY:
            return lower, "valid"
        if lower in _COMPLEXITY_MAP:
            return _COMPLEXITY_MAP[lower], "mapped"
        return "moderate", "unknown"
    if isinstance(value, (int, float)):
        n = int(value)
        if n <= 3:
            return "simple", "mapped"
        if n <= 6:
            return "moderate", "mapped"
        return "complex", "mapped"
    return "moderate", "unknown"


# ── Test path detection ────────────────────────────────────────────────────

def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1] if "/" in path else path


def _path_segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _is_test_path(path: str) -> bool:
    stem, ext = os.path.splitext(_basename(path))
    if ext in _JS_TS_TEST_EXTS:
        return stem.endswith(".test") or stem.endswith(".spec")
    patterns = _TEST_NAME_PATTERNS.get(ext)
    if patterns is None:
        return False
    prefixes, suffixes = patterns
    return any(stem.startswith(p) for p in prefixes) or any(stem.endswith(s) for s in suffixes)


def _strip_test_infix(stem: str) -> str | None:
    for infix in (".test", ".spec"):
        if stem.endswith(infix):
            return stem[: -len(infix)]
    return None


def _join_path(dir_path: str, name: str) -> str:
    return f"{dir_path}/{name}" if dir_path else name


def _add_unique(out: list[str], path: str) -> None:
    if path and path not in out:
        out.append(path)


def _js_ts_sibling_candidates(dir_path: str, base_stem: str) -> list[str]:
    return [_join_path(dir_path, f"{base_stem}{e}") for e in _JS_TS_EXTS]


def _production_candidates(test_path: str) -> list[str]:
    stem, ext = os.path.splitext(_basename(test_path))
    segs = _path_segments(test_path)
    dir_segs = segs[:-1]
    dir_path = "/".join(dir_segs)
    candidates: list[str] = []

    if ext in _JS_TS_TEST_EXTS:
        base_stem = _strip_test_infix(stem)
        if base_stem is not None:
            _add_unique(candidates, _join_path(dir_path, f"{base_stem}{ext}"))
            for c in _js_ts_sibling_candidates(dir_path, base_stem):
                _add_unique(candidates, c)
            if dir_segs and dir_segs[-1] in ("__tests__", "test", "spec", "tests"):
                parent = "/".join(dir_segs[:-1])
                _add_unique(candidates, _join_path(parent, f"{base_stem}{ext}"))
                for c in _js_ts_sibling_candidates(parent, base_stem):
                    _add_unique(candidates, c)
            if dir_segs and dir_segs[0] in ("tests", "test", "__tests__"):
                tail = "/".join(dir_segs[1:])
                for root_seg in _MIRROR_PRODUCTION_ROOTS:
                    new_dir = "/".join(p for p in (root_seg, tail) if p)
                    _add_unique(candidates, _join_path(new_dir, f"{base_stem}{ext}"))
                    for c in _js_ts_sibling_candidates(new_dir, base_stem):
                        _add_unique(candidates, c)

    elif ext == ".go" and stem.endswith("_test"):
        _add_unique(candidates, _join_path(dir_path, f"{stem[:-5]}.go"))

    elif ext == ".py" and (stem.startswith("test_") or stem.endswith("_test")):
        base_stem = stem[5:] if stem.startswith("test_") else stem[:-5]
        _add_unique(candidates, _join_path(dir_path, f"{base_stem}.py"))
        if dir_segs and dir_segs[-1] in ("tests", "test"):
            _add_unique(candidates, _join_path("/".join(dir_segs[:-1]), f"{base_stem}.py"))
        if dir_segs and dir_segs[0] in ("tests", "test"):
            tail = "/".join(dir_segs[1:])
            for root_seg in _MIRROR_PRODUCTION_ROOTS:
                new_dir = "/".join(p for p in (root_seg, tail) if p)
                _add_unique(candidates, _join_path(new_dir, f"{base_stem}.py"))

    elif ext == ".java":
        for suffix in ("Tests", "Test", "IT"):
            if stem.endswith(suffix):
                base_stem = stem[: -len(suffix)]
                if len(dir_segs) >= 3 and dir_segs[:3] == ["src", "test", "java"]:
                    _add_unique(candidates, "/".join(["src", "main", "java"] + dir_segs[3:] + [f"{base_stem}.java"]))
                _add_unique(candidates, _join_path(dir_path, f"{base_stem}.java"))
                break

    elif ext == ".kt":
        for suffix in ("Tests", "Test"):
            if stem.endswith(suffix):
                base_stem = stem[: -len(suffix)]
                if len(dir_segs) >= 3 and dir_segs[:3] == ["src", "test", "kotlin"]:
                    _add_unique(candidates, "/".join(["src", "main", "kotlin"] + dir_segs[3:] + [f"{base_stem}.kt"]))
                _add_unique(candidates, _join_path(dir_path, f"{base_stem}.kt"))
                break

    elif ext == ".cs":
        for suffix in ("Tests", "Test"):
            if stem.endswith(suffix):
                base_stem = stem[: -len(suffix)]
                _add_unique(candidates, _join_path(dir_path, f"{base_stem}.cs"))
                tests_idx = next((i for i in range(len(dir_segs) - 1, -1, -1) if dir_segs[i].lower() in ("tests", "test")), None)
                if tests_idx is not None:
                    parent_segs = dir_segs[:tests_idx]
                    tail_segs = dir_segs[tests_idx + 1:]
                    _add_unique(candidates, _join_path("/".join(parent_segs), f"{base_stem}.cs"))
                    _add_unique(candidates, "/".join([*parent_segs, "src", *tail_segs, f"{base_stem}.cs"]))
                if dir_segs:
                    top = dir_segs[0]
                    for ts in (".Tests", ".Test"):
                        if top.endswith(ts):
                            sibling = top[: -len(ts)]
                            if sibling:
                                _add_unique(candidates, _join_path("/".join([sibling] + dir_segs[1:]), f"{base_stem}.cs"))
                            break
                break

    elif ext in {".c", ".cpp", ".cc"}:
        if stem.startswith("test_"):
            _add_unique(candidates, _join_path(dir_path, f"{stem[5:]}{ext}"))
        elif stem.endswith("_test"):
            _add_unique(candidates, _join_path(dir_path, f"{stem[:-5]}{ext}"))

    return candidates


# ── tested_by linker ───────────────────────────────────────────────────────

def _file_node_path(node: dict[str, Any]) -> str | None:
    nid = node.get("id", "")
    if not isinstance(nid, str) or not nid.startswith("file:"):
        return None
    fp = node.get("filePath")
    if isinstance(fp, str) and fp:
        return fp
    return nid[len("file:"):]


def _ensure_tested_tag(node: dict[str, Any]) -> bool:
    tags = node.get("tags")
    if not isinstance(tags, list):
        tags = []
        node["tags"] = tags
    if "tested" in tags:
        return False
    tags.append("tested")
    return True


def _link_tests(
    nodes_by_id: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[int, int, int, int]:
    """Two-pass tested_by linker. Returns (added, dropped, tagged, swapped)."""
    file_paths: dict[str, dict[str, Any]] = {}
    node_class: dict[str, str] = {}
    test_nodes: list[tuple[str, dict[str, Any]]] = []

    for node in nodes_by_id.values():
        path = _file_node_path(node)
        if path is None:
            continue
        file_paths[path] = node
        if _is_test_path(path):
            node_class[node["id"]] = "test"
            test_nodes.append((path, node))
        else:
            node_class[node["id"]] = "prod"

    # Pass 1: canonicalize existing tested_by edges
    covered: set[tuple[str, str]] = set()
    pair_to_idx: dict[tuple[str, str], int] = {}
    swapped_pairs: set[tuple[str, str]] = set()
    dropped = 0
    write_idx = 0

    for edge in edges:
        if edge.get("type") != "tested_by":
            edges[write_idx] = edge
            write_idx += 1
            continue

        src = edge.get("source", "")
        tgt = edge.get("target", "")
        sc = node_class.get(src)
        tc = node_class.get(tgt)

        if (sc, tc) == ("prod", "test"):
            pair = (src, tgt)
            needs_swap = False
        elif (sc, tc) == ("test", "prod"):
            pair = (tgt, src)
            needs_swap = True
        else:
            dropped += 1
            continue

        if pair in covered:
            existing_idx = pair_to_idx[pair]
            if _num(edge.get("weight", 0)) > _num(edges[existing_idx].get("weight", 0)):
                if needs_swap:
                    edge["source"] = tgt
                    edge["target"] = src
                    edge["direction"] = "forward"
                    swapped_pairs.add(pair)
                else:
                    swapped_pairs.discard(pair)
                edges[existing_idx] = edge
            dropped += 1
            continue

        if needs_swap:
            edge["source"] = tgt
            edge["target"] = src
            edge["direction"] = "forward"
            swapped_pairs.add(pair)
        covered.add(pair)
        pair_to_idx[pair] = write_idx
        edges[write_idx] = edge
        write_idx += 1

    del edges[write_idx:]
    swapped = len(swapped_pairs)

    # Pass 2: path-convention supplement
    paired_tests = {test_id for (_, test_id) in covered}
    added = 0
    for test_path, test_node in test_nodes:
        if test_node["id"] in paired_tests:
            continue
        for cand in _production_candidates(test_path):
            prod_node = file_paths.get(cand)
            if prod_node is None or _is_test_path(cand):
                continue
            pair = (prod_node["id"], test_node["id"])
            if pair in covered:
                continue
            edges.append({
                "source": prod_node["id"],
                "target": test_node["id"],
                "type": "tested_by",
                "direction": "forward",
                "weight": 0.5,
                "description": "Path-based pairing (deterministic)",
            })
            covered.add(pair)
            added += 1
            break

    tagged = sum(
        1 for prod_id, _ in covered
        if nodes_by_id.get(prod_id) and _ensure_tested_tag(nodes_by_id[prod_id])
    )

    return added, dropped, tagged, swapped


# ── GraphMerger ────────────────────────────────────────────────────────────

class GraphMerger:
    """
    Merges LLM codebase-analysis batch dicts into a normalized assembled graph.

    Steps:
      1. Combine all nodes + edges from all batches
      2. Normalize node IDs (double-prefix, project-name prefix, func:, bare paths)
      3. Normalize complexity values
      4. Rewrite edge references after ID mapping
      5. Deduplicate nodes by ID (last wins)
      5b. Deterministic tested_by linker (two-pass)
      6. Deduplicate edges, drop dangling, direction normalization
    """

    def merge(
        self,
        batches: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Merge and normalize batch results.

        Args:
            batches: List of batch dicts, each with "nodes" and "edges" lists.

        Returns:
            (assembled_graph, report_lines) where assembled_graph has "nodes" + "edges".
        """
        id_fix_patterns: Counter[str] = Counter()
        complexity_fix_patterns: Counter[str] = Counter()
        unfixable: list[str] = []

        # Step 1: combine
        all_nodes: list[dict[str, Any]] = []
        all_edges: list[dict[str, Any]] = []
        for batch in batches:
            all_nodes.extend(batch.get("nodes", []))
            all_edges.extend(batch.get("edges", []))

        total_input_nodes = len(all_nodes)
        total_input_edges = len(all_edges)

        # Step 2: normalize node IDs
        id_mapping: dict[str, str] = {}
        nodes_with_ids: list[dict[str, Any]] = []
        unknown_types: Counter[str] = Counter()

        for i, node in enumerate(all_nodes):
            original_id = node.get("id")
            if not original_id:
                unfixable.append(f"Node[{i}] missing 'id' (name={node.get('name', '?')})")
                continue
            node_type = node.get("type", "")
            if node_type and node_type not in _TYPE_TO_PREFIX:
                unknown_types[node_type] += 1
            nodes_with_ids.append(node)
            corrected = _normalize_node_id(original_id, node)
            if corrected != original_id:
                pattern = self._classify_id_fix(original_id, corrected)
                id_fix_patterns[pattern] += 1
                id_mapping[original_id] = corrected
                node["id"] = corrected

        # Step 3: normalize complexity
        complexity_unknown: Counter[str] = Counter()
        for node in nodes_with_ids:
            original = node.get("complexity")
            normalized, status = _normalize_complexity(original)
            if status == "mapped":
                repr_val = repr(original) if not isinstance(original, str) else f'"{original}"'
                complexity_fix_patterns[f"{repr_val} → \"{normalized}\""] += 1
            elif status == "unknown":
                repr_val = repr(original) if not isinstance(original, str) else f'"{original}"'
                complexity_unknown[f'complexity {repr_val} → defaulted to "moderate"'] += 1
            node["complexity"] = normalized

        # Step 4: rewrite edge references
        edges_rewritten = 0
        for edge in all_edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            new_src = id_mapping.get(src, src)
            new_tgt = id_mapping.get(tgt, tgt)
            if new_src != src or new_tgt != tgt:
                edges_rewritten += 1
                edge["source"] = new_src
                edge["target"] = new_tgt

        # Step 5: deduplicate nodes
        dup_count = 0
        nodes_by_id: dict[str, dict[str, Any]] = {}
        for node in nodes_with_ids:
            nid = node.get("id", "")
            if nid in nodes_by_id:
                dup_count += 1
            nodes_by_id[nid] = node

        # Step 5b: tested_by linker
        tb_added, tb_dropped, tb_tagged, tb_swapped = _link_tests(nodes_by_id, all_edges)

        # Step 6: deduplicate edges, drop dangling
        node_ids = set(nodes_by_id.keys())
        edges_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for edge in all_edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            etype = edge.get("type", "")
            direction = _normalize_direction(edge.get("direction"))
            edge["direction"] = direction

            if src not in node_ids or tgt not in node_ids:
                missing = []
                if src not in node_ids:
                    missing.append(f"source '{src}'")
                if tgt not in node_ids:
                    missing.append(f"target '{tgt}'")
                unfixable.append(f"Edge {src} → {tgt} ({etype}): dropped, missing {', '.join(missing)}")
                continue

            key = (src, tgt, etype, direction)
            existing = edges_by_key.get(key)
            if existing is None or _num(edge.get("weight", 0)) > _num(existing.get("weight", 0)):
                edges_by_key[key] = edge

        # Build report
        report = self._build_report(
            total_input_nodes, total_input_edges,
            id_fix_patterns, complexity_fix_patterns, edges_rewritten,
            dup_count, tb_swapped, tb_dropped, tb_added, tb_tagged,
            complexity_unknown, unknown_types, unfixable,
            len(nodes_by_id), len(edges_by_key),
        )

        assembled = {
            "nodes": list(nodes_by_id.values()),
            "edges": list(edges_by_key.values()),
        }
        return assembled, report

    def recover_imports(
        self,
        assembled: dict[str, Any],
        scan_result_path: Path,
    ) -> tuple[int, list[str]]:
        """
        Recover imports edges from importMap in scan-result.json that LLM batches dropped.

        Returns (recovered_count, report_lines).
        """
        if not Path(scan_result_path).is_file():
            return 0, [f"  importMap recovery skipped — {Path(scan_result_path).name} not found"]

        try:
            scan = json.loads(Path(scan_result_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return 0, [f"  importMap recovery skipped — could not parse: {e}"]

        import_map = scan.get("importMap")
        if not isinstance(import_map, dict):
            return 0, [f"  importMap recovery skipped — no importMap field in scan-result.json"]

        file_node_ids = {n.get("id", "") for n in assembled["nodes"] if n.get("type") == "file"}
        existing = {(e.get("source", ""), e.get("target", "")) for e in assembled["edges"] if e.get("type") == "imports"}

        recovered = 0
        skip_src = 0
        skip_tgt = 0
        for src_path, targets in import_map.items():
            if not isinstance(targets, list):
                continue
            src_id = f"file:{src_path}"
            if src_id not in file_node_ids:
                if targets:
                    skip_src += 1
                continue
            for tgt_path in targets:
                if not isinstance(tgt_path, str) or not tgt_path:
                    continue
                tgt_id = f"file:{tgt_path}"
                if tgt_id not in file_node_ids:
                    skip_tgt += 1
                    continue
                if src_id == tgt_id or (src_id, tgt_id) in existing:
                    continue
                assembled["edges"].append({
                    "source": src_id,
                    "target": tgt_id,
                    "type": "imports",
                    "direction": "forward",
                    "weight": 0.7,
                    "recoveredFromImportMap": True,
                })
                existing.add((src_id, tgt_id))
                recovered += 1

        lines = [f"  Recovered {recovered} `imports` edges from importMap ({len(import_map)} entries)"]
        if skip_src:
            lines.append(f"  Skipped {skip_src} source files with no file: node in graph")
        if skip_tgt:
            lines.append(f"  Skipped {skip_tgt} target paths with no file: node in graph")
        return recovered, lines

    def _classify_id_fix(self, original: str, corrected: str) -> str:
        for prefix in _VALID_NODE_PREFIXES:
            if original.startswith(f"{prefix}:{prefix}:"):
                return f"{prefix}:{prefix}: → {prefix}: (double prefix)"
        parts = original.split(":")
        if len(parts) >= 3 and parts[0] not in _VALID_NODE_PREFIXES and parts[1] in _VALID_NODE_PREFIXES:
            return f"<project>:{parts[1]}: → {parts[1]}: (project-name prefix)"
        if original.startswith("func:") and corrected.startswith("function:"):
            return "func: → function: (prefix canonicalization)"
        if not any(original.startswith(f"{p}:") for p in _VALID_NODE_PREFIXES):
            return f"bare path → {corrected.split(':')[0]}: (missing prefix)"
        return f"{original} → {corrected}"

    def _build_report(
        self,
        total_nodes: int, total_edges: int,
        id_fixes: Counter, complexity_fixes: Counter, edges_rewritten: int,
        dup_count: int, tb_swapped: int, tb_dropped: int,
        tb_added: int, tb_tagged: int,
        complexity_unknown: Counter, unknown_types: Counter,
        unfixable: list[str],
        output_nodes: int, output_edges: int,
    ) -> list[str]:
        report = [f"Input: {total_nodes} nodes, {total_edges} edges"]

        fixed_lines = []
        for pattern, count in id_fixes.most_common():
            fixed_lines.append(f"  {count:>4} × {pattern}")
        for pattern, count in complexity_fixes.most_common():
            fixed_lines.append(f"  {count:>4} × complexity {pattern}")
        if edges_rewritten:
            fixed_lines.append(f"  {edges_rewritten:>4} × edge references rewritten after ID normalization")
        if dup_count:
            fixed_lines.append(f"  {dup_count:>4} × duplicate node IDs removed (kept last)")
        if tb_swapped:
            fixed_lines.append(f"  {tb_swapped:>4} × tested_by edges flipped (test → production became production → test)")
        if tb_dropped:
            fixed_lines.append(f"  {tb_dropped:>4} × tested_by edges dropped (orphan endpoint or test↔test/prod↔prod)")

        if fixed_lines:
            total_fixed = (
                sum(id_fixes.values()) + sum(complexity_fixes.values())
                + edges_rewritten + dup_count + tb_swapped + tb_dropped
            )
            report.extend(["", f"Fixed ({total_fixed} corrections):"] + fixed_lines)

        if tb_added or tb_tagged:
            report.extend([
                "",
                "Tested-by linker:",
                f"  {tb_added:>4} × tested_by edges produced (path-convention supplement)",
                f"  {tb_tagged:>4} × production nodes tagged \"tested\"",
            ])

        unfixable_total = len(unfixable) + sum(complexity_unknown.values()) + sum(unknown_types.values())
        if unfixable_total:
            report.extend(["", f"Could not fix ({unfixable_total} issues — needs agent review):"])
            for ntype, count in unknown_types.most_common():
                report.append(f"  {count:>4} × unknown node type \"{ntype}\" (kept as-is)")
            for pattern, count in complexity_unknown.most_common():
                report.append(f"  {count:>4} × {pattern}")
            for detail in unfixable:
                report.append(f"  - {detail}")

        report.extend(["", f"Output: {output_nodes} nodes, {output_edges} edges"])
        return report


# ── SubgraphMerger ─────────────────────────────────────────────────────────

class SubgraphMerger:
    """
    Merges multiple subdomain knowledge-graph JSON dicts into one.

    Deduplication rules:
      nodes: last occurrence wins (later subdomain is more specific)
      edges: higher weight wins; (source, target, type) as key
      layers: union nodeIds per layer id
      tour: merge steps with same title, union nodeIds, keep longer description
    """

    def merge(
        self,
        graphs: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Merge multiple graph dicts.

        Args:
            graphs: List of knowledge-graph dicts (each with nodes, edges, layers, tour).

        Returns:
            (merged_graph, report_lines).
        """
        node_dedup_by_type: Counter[str] = Counter()
        unfixable: list[str] = []

        total_input_nodes = sum(len(g.get("nodes", [])) for g in graphs)
        total_input_edges = sum(len(g.get("edges", [])) for g in graphs)

        # Nodes: last wins
        nodes_by_id: dict[str, dict[str, Any]] = {}
        for g in graphs:
            for node in g.get("nodes", []):
                nid = node.get("id")
                if not nid:
                    unfixable.append(f"Node missing id (name={node.get('name', '?')})")
                    continue
                if nid in nodes_by_id:
                    node_dedup_by_type[node.get("type", "?")] += 1
                nodes_by_id[nid] = node

        # Edges: higher weight wins
        edge_dedup = 0
        edges_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
        for g in graphs:
            for edge in g.get("edges", []):
                key = (edge.get("source", ""), edge.get("target", ""), edge.get("type", ""))
                existing = edges_by_key.get(key)
                if existing is None:
                    edges_by_key[key] = edge
                else:
                    edge_dedup += 1
                    if _num(edge.get("weight", 0)) > _num(existing.get("weight", 0)):
                        edges_by_key[key] = edge

        # Drop dangling edges
        node_ids = set(nodes_by_id.keys())
        valid_edges: list[dict[str, Any]] = []
        for e in edges_by_key.values():
            src, tgt = e.get("source", ""), e.get("target", "")
            if src in node_ids and tgt in node_ids:
                valid_edges.append(e)
            else:
                missing = []
                if src not in node_ids:
                    missing.append(f"source '{src}'")
                if tgt not in node_ids:
                    missing.append(f"target '{tgt}'")
                unfixable.append(f"Edge {src} → {tgt} ({e.get('type', '?')}): dropped, missing {', '.join(missing)}")

        # Layers: union nodeIds
        layers_by_id: dict[str, dict[str, Any]] = {}
        dropped_layer = 0
        for g in graphs:
            for layer in g.get("layers", []):
                lid = layer.get("id", "")
                if lid in layers_by_id:
                    existing_ids = set(layers_by_id[lid].get("nodeIds", []))
                    existing_ids.update(layer.get("nodeIds", []))
                    layers_by_id[lid]["nodeIds"] = list(existing_ids)
                else:
                    layers_by_id[lid] = {**layer}
        for layer in layers_by_id.values():
            before = len(layer.get("nodeIds", []))
            layer["nodeIds"] = [nid for nid in layer.get("nodeIds", []) if nid in node_ids]
            dropped_layer += before - len(layer["nodeIds"])

        # Tour: merge by title
        tour_steps: list[dict[str, Any]] = []
        title_to_step: dict[str, dict[str, Any]] = {}
        dropped_tour = 0
        for g in graphs:
            for step in g.get("tour", []):
                title = step.get("title", "")
                if title in title_to_step:
                    existing = title_to_step[title]
                    for nid in step.get("nodeIds", []):
                        if nid not in existing.get("nodeIds", []):
                            existing.setdefault("nodeIds", []).append(nid)
                    if len(step.get("description", "")) > len(existing.get("description", "")):
                        existing["description"] = step["description"]
                else:
                    new_step = {**step}
                    title_to_step[title] = new_step
                    tour_steps.append(new_step)

        for i, step in enumerate(tour_steps, start=1):
            step["order"] = i
            before = len(step.get("nodeIds", []))
            step["nodeIds"] = [nid for nid in step.get("nodeIds", []) if nid in node_ids]
            dropped_tour += before - len(step["nodeIds"])

        # Merge project metadata
        languages: list[str] = []
        frameworks: list[str] = []
        descriptions: list[str] = []
        latest_at = ""
        latest_hash = ""
        project_name = ""
        for g in graphs:
            proj = g.get("project", {})
            project_name = proj.get("name", "") or project_name
            for lang in proj.get("languages", []):
                if lang not in languages:
                    languages.append(lang)
            for fw in proj.get("frameworks", []):
                if fw not in frameworks:
                    frameworks.append(fw)
            desc = proj.get("description", "")
            if desc and desc not in descriptions:
                descriptions.append(desc)
            analyzed = proj.get("analyzedAt", "")
            if analyzed > latest_at:
                latest_at = analyzed
                latest_hash = proj.get("gitCommitHash", latest_hash)

        # Report
        report = [f"Input: {total_input_nodes} nodes, {total_input_edges} edges (from {len(graphs)} graphs)"]
        fixed_lines = []
        for ntype, count in node_dedup_by_type.most_common():
            fixed_lines.append(f"  {count:>4} × duplicate '{ntype}' nodes removed (kept later)")
        if edge_dedup:
            fixed_lines.append(f"  {edge_dedup:>4} × duplicate edges removed (kept higher weight)")
        if dropped_layer:
            fixed_lines.append(f"  {dropped_layer:>4} × dangling layer nodeId refs removed")
        if dropped_tour:
            fixed_lines.append(f"  {dropped_tour:>4} × dangling tour nodeId refs removed")
        if fixed_lines:
            total_fixed = sum(node_dedup_by_type.values()) + edge_dedup + dropped_layer + dropped_tour
            report.extend(["", f"Fixed ({total_fixed} corrections):"] + fixed_lines)
        if unfixable:
            report.extend(["", f"Could not fix ({len(unfixable)} issues):"])
            for detail in unfixable:
                report.append(f"  - {detail}")
        report.extend(["", f"Output: {len(nodes_by_id)} nodes, {len(valid_edges)} edges, "
                       f"{len(layers_by_id)} layers, {len(tour_steps)} tour steps"])

        merged: dict[str, Any] = {
            "version": "1.0.0",
            "project": {
                "name": project_name,
                "languages": languages,
                "frameworks": frameworks,
                "description": " | ".join(descriptions) if len(descriptions) > 1 else (descriptions[0] if descriptions else ""),
                "analyzedAt": latest_at,
                "gitCommitHash": latest_hash,
            },
            "nodes": list(nodes_by_id.values()),
            "edges": valid_edges,
            "layers": list(layers_by_id.values()),
            "tour": tour_steps,
        }
        return merged, report


if __name__ == "__main__":
    # ── GraphMerger tests ────────────────────────────────────────────────────
    gm = GraphMerger()

    # Node ID normalization
    b1 = {
        "nodes": [
            {"id": "file:file:src/app.ts", "type": "file", "name": "app.ts", "complexity": "medium"},
            {"id": "func:utils/helper", "type": "function", "name": "helper", "complexity": "low"},
            {"id": "myproject:class:Foo", "type": "class", "name": "Foo", "complexity": "high"},
        ],
        "edges": [],
    }
    assembled, report = gm.merge([b1])
    node_ids = {n["id"] for n in assembled["nodes"]}
    assert "file:src/app.ts" in node_ids, f"Double prefix not stripped: {node_ids}"
    assert "function:utils/helper" in node_ids, f"func: not canonicalized: {node_ids}"
    assert "class:Foo" in node_ids, f"Project-name prefix not stripped: {node_ids}"

    # Complexity normalization
    complexities = {n["name"]: n["complexity"] for n in assembled["nodes"]}
    assert complexities["app.ts"] == "moderate"
    assert complexities["helper"] == "simple"
    assert complexities["Foo"] == "complex"

    # Edge deduplication: same (src, tgt, type, direction) → keep higher weight
    b2 = {
        "nodes": [
            {"id": "file:a.py", "type": "file", "name": "a", "complexity": "simple"},
            {"id": "file:b.py", "type": "file", "name": "b", "complexity": "simple"},
        ],
        "edges": [
            {"source": "file:a.py", "target": "file:b.py", "type": "imports", "direction": "forward", "weight": 0.3},
            {"source": "file:a.py", "target": "file:b.py", "type": "imports", "direction": "forward", "weight": 0.9},
        ],
    }
    assembled2, _ = gm.merge([b2])
    imports_edges = [e for e in assembled2["edges"] if e["type"] == "imports"]
    assert len(imports_edges) == 1
    assert imports_edges[0]["weight"] == 0.9

    # Dangling edge drop
    b3 = {
        "nodes": [{"id": "file:real.py", "type": "file", "name": "real", "complexity": "simple"}],
        "edges": [
            {"source": "file:real.py", "target": "file:ghost.py", "type": "imports", "direction": "forward", "weight": 0.5},
        ],
    }
    assembled3, _ = gm.merge([b3])
    assert len(assembled3["edges"]) == 0, "Dangling edge not dropped"

    # tested_by: inverted edge should be flipped
    b4 = {
        "nodes": [
            {"id": "file:src/calc.py", "type": "file", "name": "calc", "complexity": "simple", "filePath": "src/calc.py"},
            {"id": "file:tests/test_calc.py", "type": "file", "name": "test_calc", "complexity": "simple", "filePath": "tests/test_calc.py"},
        ],
        "edges": [
            # inverted: test → production
            {"source": "file:tests/test_calc.py", "target": "file:src/calc.py", "type": "tested_by", "direction": "forward", "weight": 0.8},
        ],
    }
    assembled4, _ = gm.merge([b4])
    tb_edges = [e for e in assembled4["edges"] if e["type"] == "tested_by"]
    assert len(tb_edges) == 1
    assert tb_edges[0]["source"] == "file:src/calc.py", "tested_by not flipped to production → test"
    assert tb_edges[0]["target"] == "file:tests/test_calc.py"

    # tested_by: path-convention supplement (Go style)
    b5 = {
        "nodes": [
            {"id": "file:pkg/server.go", "type": "file", "name": "server", "complexity": "moderate", "filePath": "pkg/server.go"},
            {"id": "file:pkg/server_test.go", "type": "file", "name": "server_test", "complexity": "simple", "filePath": "pkg/server_test.go"},
        ],
        "edges": [],
    }
    assembled5, _ = gm.merge([b5])
    tb_edges5 = [e for e in assembled5["edges"] if e["type"] == "tested_by"]
    assert len(tb_edges5) == 1
    assert tb_edges5[0]["source"] == "file:pkg/server.go"

    # importMap recovery
    import tempfile, gc
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        scan_path = Path(d) / "scan-result.json"
        scan_path.write_text(json.dumps({
            "importMap": {
                "src/a.ts": ["src/b.ts"],
                "src/b.ts": [],
            }
        }), encoding="utf-8")
        assembled_base = {
            "nodes": [
                {"id": "file:src/a.ts", "type": "file"},
                {"id": "file:src/b.ts", "type": "file"},
            ],
            "edges": [],
        }
        recovered, lines = gm.recover_imports(assembled_base, scan_path)
        assert recovered == 1
        assert any(e["type"] == "imports" for e in assembled_base["edges"])
        gc.collect()

    # ── SubgraphMerger tests ─────────────────────────────────────────────────
    sm = SubgraphMerger()
    g1 = {
        "nodes": [{"id": "article:a", "type": "article", "name": "A"}, {"id": "topic:x", "type": "topic", "name": "X"}],
        "edges": [{"source": "article:a", "target": "topic:x", "type": "related", "weight": 0.5}],
        "layers": [{"id": "layer:x", "name": "X", "nodeIds": ["article:a"]}],
        "tour": [{"title": "Intro", "order": 1, "nodeIds": ["article:a"], "description": "Short"}],
        "project": {"name": "Proj", "languages": ["python"], "frameworks": ["fastapi"],
                    "description": "Base", "analyzedAt": "2026-01-01T00:00:00+00:00", "gitCommitHash": "abc"},
    }
    g2 = {
        "nodes": [{"id": "article:b", "type": "article", "name": "B"}, {"id": "topic:x", "type": "topic", "name": "X updated"}],
        "edges": [{"source": "article:b", "target": "topic:x", "type": "related", "weight": 0.9}],
        "layers": [{"id": "layer:x", "name": "X", "nodeIds": ["article:b"]}],
        "tour": [{"title": "Intro", "order": 1, "nodeIds": ["article:b"], "description": "Longer description here"}],
        "project": {"name": "Proj", "languages": ["markdown"], "frameworks": ["vue"],
                    "description": "Extended", "analyzedAt": "2026-06-01T00:00:00+00:00", "gitCommitHash": "def"},
    }
    merged, report_lines = sm.merge([g1, g2])
    assert len(merged["nodes"]) == 3  # article:a, article:b, topic:x (deduped)
    # layer union
    layer_x = next(l for l in merged["layers"] if l["id"] == "layer:x")
    assert "article:a" in layer_x["nodeIds"] and "article:b" in layer_x["nodeIds"]
    # tour merge: both have "Intro" → merged into one with both nodeIds
    intro_steps = [s for s in merged["tour"] if s["title"] == "Intro"]
    assert len(intro_steps) == 1
    assert "article:a" in intro_steps[0]["nodeIds"] and "article:b" in intro_steps[0]["nodeIds"]
    assert intro_steps[0]["description"] == "Longer description here"
    # project metadata merged
    assert "python" in merged["project"]["languages"]
    assert "markdown" in merged["project"]["languages"]

    print("OK graph_merger.py — ID normalization, complexity, edge dedup, dangling drop, "
          "tested_by flip+supplement, importMap recovery, SubgraphMerger union all verified")
