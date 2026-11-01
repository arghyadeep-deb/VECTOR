"""
VECTOR × code-review-graph adapter.

Wraps the code-review-graph Python API for use by ArchitectBot and CodeReviewer.
Provides: build_graph(), query_impact(), find_large_functions(), search_code()

Repo: C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/tirth8205_code-review-graph/repo
Install: pip install code-review-graph  (or use local repo path)
"""
from pathlib import Path

_CRG_REPO = Path(__file__).parent.parent.parent.parent.parent / \
    "GitHub/code-review-graph-main"

from loguru import logger

_VECTOR_ROOT = str(Path(__file__).parent.parent.parent.parent)


def _get_graph(repo_path: str = _VECTOR_ROOT):
    """Get or build the code graph for a repo. Returns graph object or None."""
    try:
        from code_review_graph.graph import CodeGraph
        db_path = Path(repo_path) / ".code_review_graph.db"
        return CodeGraph(str(db_path))
    except ImportError:
        logger.warning("[CRG] code-review-graph not installed: pip install code-review-graph")
        return None
    except Exception as e:
        logger.warning(f"[CRG] graph init failed: {e}")
        return None


def build_graph(repo_path: str = _VECTOR_ROOT) -> dict:
    """Build/update the code knowledge graph for a repo."""
    try:
        from code_review_graph.tools.build import build_or_update_graph
        result = build_or_update_graph(repo_path=repo_path)
        logger.info(f"[CRG] Graph built for {repo_path}: {result}")
        return {"status": "ok", "result": str(result)}
    except ImportError:
        logger.warning("[CRG] code-review-graph not installed")
        return {"status": "not_installed"}
    except Exception as e:
        logger.warning(f"[CRG] build_graph failed: {e}")
        return {"status": "error", "error": str(e)}


def query_impact(symbol: str, repo_path: str = _VECTOR_ROOT, depth: int = 3) -> dict:
    """
    Find all code impacted by changing a symbol (function/class/file).
    Returns blast radius — what breaks if you change this.
    """
    try:
        graph = _get_graph(repo_path)
        if graph is None:
            return {"status": "not_available"}
        nodes = graph.get_impact_radius(symbol, max_depth=depth)
        return {
            "status": "ok",
            "symbol": symbol,
            "impacted_nodes": [n.qualified_name for n in nodes],
            "count": len(nodes),
        }
    except Exception as e:
        logger.warning(f"[CRG] query_impact failed: {e}")
        return {"status": "error", "error": str(e)}


def find_large_functions(repo_path: str = _VECTOR_ROOT, min_lines: int = 50) -> list[dict]:
    """Find functions that are too large and should be refactored."""
    try:
        from code_review_graph.tools.analysis_tools import find_large_functions as _find
        results = _find(repo_path=repo_path, min_lines=min_lines)
        return results if isinstance(results, list) else []
    except Exception as e:
        logger.warning(f"[CRG] find_large_functions failed: {e}")
        return []


def search_code(query: str, repo_path: str = _VECTOR_ROOT, limit: int = 10) -> list[dict]:
    """Semantic + BM25 hybrid search over the codebase graph."""
    try:
        from code_review_graph.search import search_graph
        results = search_graph(query=query, repo_path=repo_path, limit=limit)
        return results if isinstance(results, list) else []
    except Exception as e:
        logger.warning(f"[CRG] search_code failed: {e}")
        return []


def review_changes(changed_files: list[str], repo_path: str = _VECTOR_ROOT) -> dict:
    """
    Graph-aware code review: given changed files, find all impacted code
    and return a structured review with blast radius analysis.
    """
    try:
        from code_review_graph.tools.review import review_changes as _review
        result = _review(changed_files=changed_files, repo_path=repo_path)
        return {"status": "ok", "review": result}
    except Exception as e:
        logger.warning(f"[CRG] review_changes failed: {e}")
        # Fallback: just return impact for each file
        impacts = {}
        for f in changed_files:
            impacts[f] = query_impact(f, repo_path)
        return {"status": "partial", "impacts": impacts}
