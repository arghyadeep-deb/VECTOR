"""Code graph MCP tool registration."""

from __future__ import annotations


def _resolve_repo(repo_path: str):
    """Resolve repo_path to a directory inside the VECTOR repo, else None (CWE-22)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    candidate = Path(repo_path or ".")
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    return resolved if resolved.is_relative_to(root) else None


def add_code_graph_tools(mcp) -> None:
    """Register code-review-graph MCP tools."""

    @mcp.tool
    async def code_graph_build(repo_path: str = ".") -> str:
        """Build/update the code knowledge graph for the VECTOR codebase."""
        try:
            from districts.coding.code_review_graph import build_graph

            repo = _resolve_repo(repo_path)
            if repo is None:
                return f"Error: repo_path '{repo_path}' is outside the VECTOR codebase"
            result = build_graph(str(repo))
            return str(result)
        except Exception as exc:
            return f"Error: {exc}"

    @mcp.tool
    async def code_graph_impact(symbol: str, depth: int = 3) -> str:
        """Find all code impacted by changing a symbol."""
        try:
            from districts.coding.code_review_graph import query_impact

            result = query_impact(symbol, depth=depth)
            return str(result)
        except Exception as exc:
            return f"Error: {exc}"

    @mcp.tool
    async def code_graph_review(changed_files: str) -> str:
        """Graph-aware code review for comma-separated changed files."""
        try:
            from districts.coding.code_review_graph import review_changes

            files = [file_path.strip() for file_path in changed_files.split(",") if file_path.strip()]
            result = review_changes(files)
            return str(result)
        except Exception as exc:
            return f"Error: {exc}"


__all__ = ["add_code_graph_tools"]
