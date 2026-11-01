"""MCP knowledge graph tools."""

from pathlib import Path

from loguru import logger

from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.security import mcp_secure_call as _mcp_secure_call


def add_knowledge_tools(mcp) -> None:
    """Expose the VECTOR knowledge layer (Understand-Anything absorption) to MCP clients.
    3 tools: knowledge_scan_domain, knowledge_parse_wiki, knowledge_merge_wiki."""
    try:
        from core.knowledge.domain_extractor import DomainExtractor as _DomainExtractor
        from core.knowledge.wiki_parser import WikiParser as _WikiParser
        from core.knowledge.wiki_merger import WikiMerger as _WikiMerger
    except Exception as e:
        logger.warning(f"[VECTOR][mcp] knowledge tools unavailable: {e}")
        return

    @mcp.tool
    def knowledge_scan_domain(project_path: str = "", output_filename: str = "") -> str:
        """Scan a project directory and extract domain context (entry points, file signatures, metadata).
        project_path: absolute path to project root (defaults to VECTOR codebase).
        output_filename: optional filename to write JSON output (e.g. 'my-project.json').
        Returns JSON with projectRoot, fileCount, entryPoints, fileSignatures, metadata."""
        if not _mcp_secure_call("knowledge_scan_domain", "knowledge", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            from pathlib import Path as _Path
            from core.config import CONFIG as _CONFIG
            root = _Path(project_path).resolve() if project_path else _Path(__file__).resolve().parents[2]
            if not root.is_dir():
                return _safe_json({"error": f"Not a directory: {root}"})
            output_path = None
            if output_filename:
                out_dir = _Path(_CONFIG["knowledge"]["output_dir"])
                out_dir.mkdir(parents=True, exist_ok=True)
                output_path = out_dir / _Path(output_filename).name
            extractor = _DomainExtractor()
            ctx = extractor.scan(root, output_path=output_path)
            result = ctx.to_dict()
            result["_outputPath"] = str(output_path) if output_path else None
            return _safe_json(result)
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def knowledge_parse_wiki(wiki_root: str = "") -> str:
        """Parse a Karpathy-format markdown wiki into a scan manifest (nodes, edges, categories).
        wiki_root: path to wiki directory (defaults to Obsidian brain vault).
        Writes scan-manifest.json to <wiki_root>/.understand-anything/intermediate/.
        Returns node_count, edge_count, category_count, and manifest_path."""
        if not _mcp_secure_call("knowledge_parse_wiki", "knowledge", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            import json as _json
            from pathlib import Path as _Path
            from core.config import CONFIG as _CONFIG
            root = _Path(wiki_root).resolve() if wiki_root else _Path(_CONFIG["knowledge"]["wiki_root"])
            if not root.is_dir():
                return _safe_json({"error": f"Wiki root not found: {root}"})
            parser = _WikiParser()
            out_path = parser.parse_to_file(root)
            manifest = _json.loads(out_path.read_text(encoding="utf-8"))
            return _safe_json({
                "wiki_root": str(root),
                "manifest_path": str(out_path),
                "node_count": len(manifest.get("nodes", [])),
                "edge_count": len(manifest.get("edges", [])),
                "category_count": len(manifest.get("categories", [])),
            })
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def knowledge_merge_wiki(wiki_root: str = "") -> str:
        """Merge a parsed wiki's scan manifest with any LLM analysis batches into an assembled graph.
        wiki_root: path to wiki directory (defaults to Obsidian brain vault).
        Requires parse_wiki to have run first. Writes assembled-graph.json.
        Returns node_count, edge_count, layer_count, tour_steps, graph_path."""
        if not _mcp_secure_call("knowledge_merge_wiki", "knowledge", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            from pathlib import Path as _Path
            from core.config import CONFIG as _CONFIG
            root = _Path(wiki_root).resolve() if wiki_root else _Path(_CONFIG["knowledge"]["wiki_root"])
            if not root.is_dir():
                return _safe_json({"error": f"Wiki root not found: {root}"})
            merger = _WikiMerger()
            graph = merger.merge_from_disk(root)
            out_path = merger.write(root, graph)
            return _safe_json({
                "wiki_root": str(root),
                "graph_path": str(out_path),
                "node_count": len(graph["nodes"]),
                "edge_count": len(graph["edges"]),
                "layer_count": len(graph["layers"]),
                "tour_steps": len(graph["tour"]),
                "project": graph.get("project", {}),
            })
        except FileNotFoundError as e:
            return _safe_json({"error": f"scan-manifest.json not found — run knowledge_parse_wiki first. {e}"})
        except Exception as e:
            return _safe_json({"error": str(e)})
