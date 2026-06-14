"""Code graph MCP tool registration."""

from __future__ import annotations


def add_code_graph_tools(mcp) -> None:
    """Register code-review-graph MCP tools."""

    @mcp.tool
    async def code_graph_build(repo_path: str = ".") -> str:
        """Build/update the code knowledge graph for the VECTOR codebase."""
        try:
            from districts.coding.code_review_graph import build_graph

            result = build_graph(repo_path)
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
