"""Re-export from the real vc_tools implementation."""
try:
    from vectorcode.src.vc_tools.knowledge_sql import KnowledgeSQLTool
except Exception:
    class KnowledgeSQLTool:  # type: ignore[no-redef]
        def run(self, sql: str) -> list:
            return []

__all__ = ["KnowledgeSQLTool"]
