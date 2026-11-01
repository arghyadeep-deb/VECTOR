from __future__ import annotations

import ast
import re
from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)

_ROOT = Path(__file__).resolve().parents[3]  # module-level so tests can point it at a tmp dir
_REF_OK = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./@^~{}-]{0,199}")


def _count_symbols(source: str) -> int:
    """Number of function/class definitions in ``source`` (0 if it does not parse)."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return 0
    return sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in ast.walk(tree))


def add_graph_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _ROOT

    # â”€â”€ graph_* (28) — wired to core/memory/knowledge_graph.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.memory.knowledge_graph import get_knowledge_graph as _get_kg

        @mcp.tool
        def graph_index(entity: str, entity_type: str = "symbol", file_path: str = "") -> str:
            """Index a file or symbol into the knowledge graph."""
            kg = _get_kg()
            kg.add_entity(entity, entity_type, properties={"file": file_path} if file_path else {})
            return _safe_json({"ok": True, "entity": entity, "type": entity_type})

        @mcp.tool
        def graph_query(term: str, max_results: int = 10) -> str:
            """Query the knowledge graph."""
            kg = _get_kg()
            results = kg.query(term, max_results=max_results) if hasattr(kg, "query") else []
            return _safe_json({"query": term, "results": results})

        @mcp.tool
        def graph_dependents(entity: str) -> str:
            """Get entities that depend on a symbol."""
            kg = _get_kg()
            neighbors = kg.get_neighbors(entity) if hasattr(kg, "get_neighbors") else []
            return _safe_json({"entity": entity, "dependents": neighbors})

        @mcp.tool
        def graph_stats() -> str:
            """Get knowledge graph statistics."""
            kg = _get_kg()
            return _safe_json({"entities": kg.entity_count() if hasattr(kg, "entity_count") else 0, "relations": kg.relation_count() if hasattr(kg, "relation_count") else 0})

        @mcp.tool
        def graph_search(pattern: str, max_results: int = 10) -> str:
            """Search for symbols by name pattern."""
            kg = _get_kg()
            results = kg.query(pattern, max_results=max_results) if hasattr(kg, "query") else []
            return _safe_json({"pattern": pattern, "results": results})

        @mcp.tool
        def graph_filter(entity_type: str) -> str:
            """Filter graph by entity type."""
            kg = _get_kg()
            entities = kg.all_entities(entity_type) if hasattr(kg, "all_entities") else []
            return _safe_json({"type": entity_type, "entities": entities[:50]})

        @mcp.tool
        def graph_trace(start: str, end: str, max_depth: int = 5) -> str:
            """Trace call path between two symbols."""
            kg = _get_kg()
            path = kg.find_path(start, end, max_depth=max_depth) if hasattr(kg, "find_path") else []
            return _safe_json({"start": start, "end": end, "path": path})

        @mcp.tool
        def graph_annotate(entity: str, properties: str = "{}") -> str:
            """Annotate a symbol with metadata."""
            kg = _get_kg()
            props = _json.loads(properties) if properties else {}
            kg.add_entity(entity, "annotated", properties=props)
            return _safe_json({"ok": True, "entity": entity, "properties": props})

        @mcp.tool
        def graph_path(start: str, end: str) -> str:
            """Find shortest path between symbols."""
            kg = _get_kg()
            path = kg.find_path(start, end) if hasattr(kg, "find_path") else []
            return _safe_json({"start": start, "end": end, "path": path, "distance": len(path)})

        @mcp.tool
        def graph_symbols(file_path: str) -> str:
            """List all symbols in a file."""
            try:
                base = ROOT.resolve()
                scan_target = (base / file_path).resolve()
                if not scan_target.is_relative_to(base) or scan_target.suffix != ".py":
                    return _safe_json({"error": "file_path must be a .py file inside the repo root"})
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.scan_module(str(scan_target)) if hasattr(writer, "scan_module") else {"file": file_path, "symbols": []}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def graph_export(path: str = "") -> str:
            """Export knowledge graph to JSON."""
            kg = _get_kg()
            entities = kg.all_entities() if hasattr(kg, "all_entities") else []
            out_path, err = _resolve_memory_path(path, default_name="graph_export.json")
            if err:
                return _safe_json({"error": err})
            with open(out_path, "w", encoding="utf-8") as f:
                _json.dump({"entities": entities}, f, default=str)
            return _safe_json({"ok": True, "path": str(out_path), "entity_count": len(entities)})

        @mcp.tool
        def graph_import(path: str) -> str:
            """Import knowledge graph from JSON."""
            kg = _get_kg()
            in_path, err = _resolve_memory_path(path, default_name="graph_export.json")
            if err:
                return _safe_json({"error": err})
            try:
                with open(in_path, encoding="utf-8") as f:
                    data = _json.load(f)
                count = 0
                for entity in data.get("entities", []):
                    if not isinstance(entity, dict) or not entity.get("name"):
                        continue
                    kg.add_entity(entity["name"], entity.get("type", "unknown"), entity.get("properties", {}))
                    count += 1
            except Exception as e:
                logger.warning("[VECTOR][mcp] graph_import failed: {}", e)
                return _safe_json({"error": str(e)})
            return _safe_json({"ok": True, "imported": count})

        @mcp.tool
        def graph_blast_radius(entity: str) -> str:
            """Get blast radius for a changed symbol (recursive dependents)."""
            kg = _get_kg()
            visited = set()
            def _traverse(e, depth=0):
                if e in visited or depth > 5:
                    return
                visited.add(e)
                for dep in (kg.get_neighbors(e) if hasattr(kg, "get_neighbors") else []):
                    _traverse(dep, depth + 1)
            _traverse(entity)
            return _safe_json({"entity": entity, "blast_radius": list(visited), "count": len(visited)})

        @mcp.tool
        def graph_distance(start: str, end: str) -> str:
            """Get graph distance between symbols."""
            kg = _get_kg()
            path = kg.find_path(start, end) if hasattr(kg, "find_path") else []
            return _safe_json({"start": start, "end": end, "distance": len(path), "path": path})

        @mcp.tool
        def graph_report() -> str:
            """Generate a knowledge graph health report."""
            kg = _get_kg()
            return _safe_json({"entities": kg.entity_count() if hasattr(kg, "entity_count") else 0, "relations": kg.relation_count() if hasattr(kg, "relation_count") else 0, "status": "healthy"})

        @mcp.tool
        def graph_visualize(entity: str = "", format: str = "dot") -> str:
            """Visualize the knowledge graph as DOT format."""
            kg = _get_kg()
            if entity:
                neighbors = kg.get_neighbors(entity) if hasattr(kg, "get_neighbors") else []
                lines = [f"digraph {{", f'  "{entity}" [style=filled,fillcolor=lightblue];']
                for rel in neighbors:
                    subj = getattr(rel, "subject", "")
                    obj = getattr(rel, "obj", "") or getattr(rel, "object", "")
                    pred = getattr(rel, "predicate", "related_to")
                    lbl = pred
                    if subj and obj:
                        lines.append(f'  "{subj}" -> "{obj}" [label="{lbl}"];')
                lines.append("}")
                return _safe_json({"dot": "\n".join(lines), "entity": entity})
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            lines = ["digraph {", "  rankdir=LR;"]
            for ent in all_ents[:50]:
                name = getattr(ent, "name", str(ent))
                etype = getattr(ent, "entity_type", "") if hasattr(ent, "entity_type") else getattr(ent, "type", "")
                lines.append(f'  "{name}" [label="{name}",shape={"box" if etype=="module" else "ellipse"}];')
            lines.append("}")
            return _safe_json({"dot": "\n".join(lines), "entity_count": len(all_ents)})

        @mcp.tool
        def graph_clean(older_than_days: int = 90) -> str:
            """Remove stale entries from graph older than N days."""
            import time
            cutoff = time.time() - (older_than_days * 86400)
            kg = _get_kg()
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            stale = [e for e in all_ents if getattr(e, "created_at", 0) < cutoff]
            # The knowledge graph has no delete API, so nothing is removed here.
            return _safe_json({"removed_count": 0, "stale_count": len(stale), "older_than_days": older_than_days, "note": "Nothing was removed (the knowledge graph has no delete API); stale_count is informational"})

        @mcp.tool
        def graph_rebuild(scan_path: str = "core/") -> str:
            """Rebuild the code graph by scanning symbols from Python files."""
            import ast
            kg = _get_kg()
            base = ROOT.resolve()
            scan_dir = (base / scan_path).resolve()
            if not scan_dir.is_relative_to(base):
                return _safe_json({"error": "scan_path escapes the repo root"})
            count = 0
            for pyfile in scan_dir.rglob("*.py"):
                try:
                    pyfile = pyfile.resolve()
                    if not pyfile.is_relative_to(base):
                        continue  # symlink pointing outside the repo
                    tree = ast.parse(pyfile.read_text(encoding="utf-8", errors="replace"))
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            kg.add_entity(f"{pyfile.relative_to(base).as_posix()}::{node.name}", "symbol" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "class")
                            count += 1
                except Exception as e:
                    logger.warning("[VECTOR][mcp] graph_rebuild skipped {}: {}", pyfile, e)
            return _safe_json({"ok": True, "scanned": scan_path, "entities_added": count})

        @mcp.tool
        def graph_diff(branch_a: str = "HEAD~1", branch_b: str = "HEAD") -> str:
            """Show graph changes between two commits (entity diff). Read-only: never checks out a ref."""
            try:
                shas = []
                for ref in (branch_a, branch_b):
                    if not _REF_OK.fullmatch(ref or ""):
                        return _safe_json({"error": f"invalid git ref: {ref!r}"})
                    rp = _subprocess.run(["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
                    if rp.returncode != 0:
                        return _safe_json({"error": f"unknown git ref: {ref}", "stderr": rp.stderr[-300:]})
                    shas.append(rp.stdout.strip())
                names = _subprocess.run(["git", "diff", "--name-only", "-z", shas[0], shas[1], "--", "*.py"], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
                if names.returncode != 0:
                    return _safe_json({"error": f"git diff failed (exit {names.returncode})", "stderr": names.stderr[-300:]})
                count_a = count_b = 0
                for rel in [n for n in names.stdout.split("\0") if n]:
                    for sha, side in ((shas[0], "a"), (shas[1], "b")):
                        shown = _subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
                        n = _count_symbols(shown.stdout) if shown.returncode == 0 else 0  # file absent on that side
                        if side == "a":
                            count_a += n
                        else:
                            count_b += n
                return _safe_json({"branch_a": branch_a, "entity_count_a": count_a, "branch_b": branch_b, "entity_count_b": count_b, "diff": count_b - count_a, "note": "Counts are symbols (functions/classes) in the .py files that differ between the two commits; the working tree is not touched"})
            except Exception as e:
                logger.warning("[VECTOR][mcp] graph_diff failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        def graph_callers(entity: str) -> str:
            """Get all entities that reference (are callers of) a symbol."""
            kg = _get_kg()
            neighbors = kg.get_neighbors(entity) if hasattr(kg, "get_neighbors") else []
            callers = [{"source": getattr(r, "subject", ""), "via": getattr(r, "predicate", "")} for r in neighbors if getattr(r, "obj", "") == entity or getattr(r, "object", "") == entity]
            return _safe_json({"entity": entity, "callers": callers[:50], "count": len(callers)})

        @mcp.tool
        def graph_callees(entity: str) -> str:
            """Get all entities that a symbol references (callees)."""
            kg = _get_kg()
            neighbors = kg.get_neighbors(entity) if hasattr(kg, "get_neighbors") else []
            callees = [{"target": getattr(r, "obj", "") or getattr(r, "object", ""), "via": getattr(r, "predicate", "")} for r in neighbors if getattr(r, "subject", "") == entity]
            return _safe_json({"entity": entity, "callees": callees[:50], "count": len(callees)})

        @mcp.tool
        def graph_cycles() -> str:
            """Detect circular dependencies in the knowledge graph."""
            kg = _get_kg()
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            ent_names = [getattr(e, "name", str(e)) for e in all_ents]
            cycles = []
            for name in ent_names[:100]:
                visited = set()
                path = []
                def dfs(current, depth=0):
                    if depth > 10:
                        return
                    if current in visited:
                        cycle_start = path.index(current)
                        cycles.append(path[cycle_start:] + [current])
                        return
                    visited.add(current)
                    path.append(current)
                    for rel in (kg.get_neighbors(current) if hasattr(kg, "get_neighbors") else []):
                        nxt = getattr(rel, "obj", "") or getattr(rel, "object", "")
                        if nxt and nxt in ent_names:
                            dfs(nxt, depth + 1)
                    path.pop()
                    visited.discard(current)
                dfs(name)
                if len(cycles) >= 10:
                    break
            return _safe_json({"cycles_detected": len(cycles), "cycles": cycles[:10]})

        @mcp.tool
        def graph_merge(other_path: str = "") -> str:
            """Merge another knowledge graph's entities into this one."""
            import json
            kg = _get_kg()
            if other_path:
                try:
                    in_path, err = _resolve_memory_path(other_path, default_name="graph_export.json")
                    if err:
                        return _safe_json({"error": err})
                    with open(in_path, encoding="utf-8") as f:
                        data = json.load(f)
                    count = 0
                    for ent in data.get("entities", []):
                        kg.add_entity(ent.get("name", ""), ent.get("type", "concept"), ent.get("properties", {}))
                        count += 1
                    for rel in data.get("relations", []):
                        kg.add_relation(rel.get("subject", ""), rel.get("predicate", "related_to"), rel.get("object", ""), rel.get("confidence", 1.0))
                        count += 1
                    return _safe_json({"ok": True, "imported": count, "source": other_path})
                except Exception as e:
                    return _safe_json({"error": str(e)})
            return _safe_json({"status": "requires_input", "note": "Provide other_path to a knowledge graph JSON export to merge"})

        @mcp.tool
        def graph_compare(other_path: str = "") -> str:
            """Compare current graph with another (by path) or show stats."""
            kg = _get_kg()
            current_count = kg.entity_count() if hasattr(kg, "entity_count") else 0
            if other_path:
                try:
                    import json
                    in_path, err = _resolve_memory_path(other_path, default_name="graph_export.json")
                    if err:
                        return _safe_json({"error": err})
                    with open(in_path, encoding="utf-8") as f:
                        data = json.load(f)
                    other_count = len(data.get("entities", []))
                    return _safe_json({"current_entities": current_count, "other_entities": other_count, "diff": current_count - other_count})
                except Exception as e:
                    return _safe_json({"error": str(e)})
            return _safe_json({"current_entities": current_count, "note": "Provide other_path to compare with another export"})

        @mcp.tool
        def graph_highlight(entity: str) -> str:
            """Highlight a symbol's connections — show neighbors with relation types."""
            kg = _get_kg()
            neighbors = kg.get_neighbors(entity) if hasattr(kg, "get_neighbors") else []
            connections = []
            for rel in neighbors:
                s = getattr(rel, "subject", "")
                o = getattr(rel, "obj", "") or getattr(rel, "object", "")
                p = getattr(rel, "predicate", "related_to")
                if o == entity:
                    connections.append({"direction": "incoming", "from": s, "type": p})
                elif s == entity:
                    connections.append({"direction": "outgoing", "to": o, "type": p})
            return _safe_json({"entity": entity, "connections": connections, "count": len(connections)})

        @mcp.tool
        def graph_cluster() -> str:
            """Cluster related symbols by entity type."""
            kg = _get_kg()
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            clusters = {}
            for e in all_ents:
                etype = getattr(e, "entity_type", "") if hasattr(e, "entity_type") else "unknown"
                clusters.setdefault(etype, []).append(getattr(e, "name", str(e)))
            return _safe_json({"clusters": {k: {"count": len(v), "sample": v[:10]} for k, v in clusters.items()}})

        @mcp.tool
        def graph_centrality() -> str:
            """Compute symbol centrality score based on connection count."""
            kg = _get_kg()
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            scores = {}
            for e in all_ents:
                name = getattr(e, "name", str(e))
                neighbors = kg.get_neighbors(name) if hasattr(kg, "get_neighbors") else []
                scores[name] = len(neighbors)
            ranked = sorted(scores.items(), key=lambda x: -x[1])
            return _safe_json({"top_central": [{"entity": n, "connections": c} for n, c in ranked[:20]], "total_entities": len(ranked)})

        @mcp.tool
        def graph_rank(limit: int = 20) -> str:
            """Rank symbols by importance (neighbor count + entity type weight)."""
            kg = _get_kg()
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            scores = {}
            for e in all_ents:
                name = getattr(e, "name", str(e))
                etype = getattr(e, "entity_type", "") if hasattr(e, "entity_type") else ""
                base = 2 if "module" in etype else 1 if "class" in etype else 0
                if hasattr(kg, "get_neighbors"):
                    neighbors = kg.get_neighbors(name)
                    base += len(neighbors)
                scores[name] = base
            ranked = sorted(scores.items(), key=lambda x: -x[1])
            return _safe_json({"ranked": [{"entity": n, "score": s} for n, s in ranked[:limit]], "limit": limit})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] graph tools unavailable: {e}")
        for n, d in [("graph_index", "Index entity"), ("graph_query", "Query graph"), ("graph_dependents", "Get dependents"), ("graph_stats", "Graph stats"), ("graph_search", "Search graph"), ("graph_filter", "Filter graph"), ("graph_trace", "Trace path"), ("graph_annotate", "Annotate"), ("graph_path", "Find path"), ("graph_symbols", "List symbols"), ("graph_export", "Export graph"), ("graph_import", "Import graph"), ("graph_blast_radius", "Blast radius"), ("graph_distance", "Graph distance"), ("graph_report", "Graph report"), ("graph_visualize", "Visualize"), ("graph_clean", "Clean graph"), ("graph_rebuild", "Rebuild graph"), ("graph_diff", "Graph diff"), ("graph_callers", "Callers"), ("graph_callees", "Callees"), ("graph_cycles", "Cycles"), ("graph_merge", "Merge graphs"), ("graph_compare", "Compare graphs"), ("graph_highlight", "Highlight"), ("graph_cluster", "Cluster"), ("graph_centrality", "Centrality"), ("graph_rank", "Rank")]:
            _reg(mcp, n, d)
