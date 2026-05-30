"""VECTOR knowledge router — /knowledge/* endpoints for the knowledge layer.

Exposes DomainExtractor, WikiParser, and WikiMerger to the API so VECTOR agents
can trigger codebase domain scans, wiki knowledge-graph builds, and graph merges
via HTTP. Used by karpathy_lab, research, and code_intel districts.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()


def _safe_path(value: str) -> Path:
    """Resolve path and reject anything outside VECTOR's home tree."""
    from core.config import CONFIG
    p = Path(value).resolve()
    allowed_roots = [
        _PROJECT_ROOT,
        Path(CONFIG["knowledge"]["wiki_root"]).resolve(),
        Path(CONFIG["knowledge"]["output_dir"]).resolve(),
    ]
    if not any(str(p).startswith(str(r)) for r in allowed_roots):
        raise ValueError(f"Path '{value}' is outside allowed directories.")
    return p


# ── Request models ─────────────────────────────────────────────────────────

class ScanDomainReq(BaseModel):
    project_path: str = ""        # defaults to VECTOR codebase root
    output_filename: str = ""     # e.g. "my-project.json"; empty = domain-context.json


class ParseWikiReq(BaseModel):
    wiki_root: str = ""           # defaults to CONFIG["knowledge"]["wiki_root"]


class MergeWikiReq(BaseModel):
    wiki_root: str = ""           # defaults to CONFIG["knowledge"]["wiki_root"]


class MergeGraphReq(BaseModel):
    batches_json: str = "[]"      # JSON array of batch dicts


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/scan-domain")
async def scan_domain(body: ScanDomainReq):
    """
    Run DomainExtractor on a project directory.

    Returns the domain context (entry points, file signatures, metadata)
    as a JSON-serializable dict. Optionally writes the output to the
    knowledge output directory if output_filename is provided.
    """
    from core.knowledge.domain_extractor import DomainExtractor
    from core.config import CONFIG

    try:
        root = _safe_path(body.project_path) if body.project_path else _PROJECT_ROOT
        if not root.is_dir():
            raise HTTPException(status_code=400, detail=f"Not a directory: {root}")

        output_path = None
        if body.output_filename:
            out_dir = Path(CONFIG["knowledge"]["output_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            # Prevent path traversal in filename
            filename = Path(body.output_filename).name
            output_path = out_dir / filename

        extractor = DomainExtractor()
        ctx = extractor.scan(root, output_path=output_path)
        result = ctx.to_dict()
        result["_outputPath"] = str(output_path) if output_path else None
        logger.info("[VECTOR][knowledge] scan-domain: {} files, {} entry points",
                    ctx.file_count, len(ctx.entry_points))
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[VECTOR][knowledge] scan-domain failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse-wiki")
async def parse_wiki(body: ParseWikiReq):
    """
    Run WikiParser on a Karpathy-format wiki directory.

    Writes scan-manifest.json to <wiki_root>/.understand-anything/intermediate/
    and returns the manifest dict (nodes, edges, categories).
    Defaults to the Obsidian brain vault configured in CONFIG["knowledge"]["wiki_root"].
    """
    from core.knowledge.wiki_parser import WikiParser
    from core.config import CONFIG

    try:
        wiki_root_str = body.wiki_root or CONFIG["knowledge"]["wiki_root"]
        wiki_root = Path(wiki_root_str).resolve()
        if not wiki_root.is_dir():
            raise HTTPException(status_code=400, detail=f"Wiki root not found: {wiki_root}")

        parser = WikiParser()
        out_path = parser.parse_to_file(wiki_root)
        manifest = __import__("json").loads(out_path.read_text(encoding="utf-8"))

        logger.info("[VECTOR][knowledge] parse-wiki: {} nodes, {} edges written to {}",
                    len(manifest.get("nodes", [])), len(manifest.get("edges", [])), out_path)
        return {
            "wiki_root": str(wiki_root),
            "manifest_path": str(out_path),
            "node_count": len(manifest.get("nodes", [])),
            "edge_count": len(manifest.get("edges", [])),
            "category_count": len(manifest.get("categories", [])),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[VECTOR][knowledge] parse-wiki failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/merge-wiki")
async def merge_wiki(body: MergeWikiReq):
    """
    Run WikiMerger on an already-parsed wiki directory.

    Loads scan-manifest.json + any analysis-batch-*.json files from
    .understand-anything/intermediate/ and writes assembled-graph.json.
    Returns summary stats (node/edge/layer/tour counts).
    """
    from core.knowledge.wiki_merger import WikiMerger
    from core.config import CONFIG

    try:
        wiki_root_str = body.wiki_root or CONFIG["knowledge"]["wiki_root"]
        wiki_root = Path(wiki_root_str).resolve()
        if not wiki_root.is_dir():
            raise HTTPException(status_code=400, detail=f"Wiki root not found: {wiki_root}")

        merger = WikiMerger()
        graph = merger.merge_from_disk(wiki_root)
        out_path = merger.write(wiki_root, graph)

        logger.info("[VECTOR][knowledge] merge-wiki: {} nodes, {} edges, {} layers",
                    len(graph["nodes"]), len(graph["edges"]), len(graph["layers"]))
        return {
            "wiki_root": str(wiki_root),
            "graph_path": str(out_path),
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "layer_count": len(graph["layers"]),
            "tour_steps": len(graph["tour"]),
            "project": graph.get("project", {}),
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[VECTOR][knowledge] merge-wiki failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/merge-graph")
async def merge_graph(body: MergeGraphReq):
    """
    Run GraphMerger on a JSON array of LLM batch analysis results.

    batches_json: JSON array of batch dicts, each with 'nodes' and 'edges'.
    Returns assembled graph (nodes, edges) with normalization report.
    """
    import json as _json
    from core.knowledge.graph_merger import GraphMerger

    try:
        batches = _json.loads(body.batches_json)
        if not isinstance(batches, list):
            raise HTTPException(status_code=400, detail="batches_json must be a JSON array")

        merger = GraphMerger()
        assembled, report = merger.merge(batches)
        logger.info("[VECTOR][knowledge] merge-graph: {} nodes, {} edges from {} batches",
                    len(assembled["nodes"]), len(assembled["edges"]), len(batches))
        return {
            "node_count": len(assembled["nodes"]),
            "edge_count": len(assembled["edges"]),
            "report": report,
            "nodes": assembled["nodes"],
            "edges": assembled["edges"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[VECTOR][knowledge] merge-graph failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def knowledge_status():
    """Return knowledge layer status — config paths and module availability."""
    from core.config import CONFIG
    wiki_root = Path(CONFIG["knowledge"]["wiki_root"])
    output_dir = Path(CONFIG["knowledge"]["output_dir"])
    manifest_exists = (wiki_root / ".understand-anything" / "intermediate" / "scan-manifest.json").exists()
    graph_exists = (wiki_root / ".understand-anything" / "intermediate" / "assembled-graph.json").exists()
    return {
        "wiki_root": str(wiki_root),
        "wiki_root_exists": wiki_root.is_dir(),
        "output_dir": str(output_dir),
        "scan_manifest_exists": manifest_exists,
        "assembled_graph_exists": graph_exists,
        "max_output_bytes": CONFIG["knowledge"]["max_output_bytes"],
        "modules": ["DomainExtractor", "WikiParser", "WikiMerger", "GraphMerger", "SubgraphMerger"],
    }
