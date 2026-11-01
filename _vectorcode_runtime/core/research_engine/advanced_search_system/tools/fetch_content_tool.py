from typing import Any

from loguru import logger

from .base_tool import BaseTool


class FetchContentTool(BaseTool):
    """Tool for fetching web page content."""

    def __init__(self, timeout: int = 30, max_length: int = 10_000):
        super().__init__(
            name="fetch_content",
            description="Download and read the full text content from a URL",
        )
        self.timeout = timeout
        self.max_length = max_length
        self.parameters = {
            "url": {
                "type": "str",
                "description": "The URL to fetch content from",
                "required": True,
            },
        }

    def execute(self, **kwargs: Any) -> Any:
        from core.research_engine.content_fetcher import ContentFetcher

        url = kwargs.get("url", "")
        if not url:
            return "Error: url parameter is required"

        self._log_execution(**kwargs)
        try:
            with ContentFetcher(timeout=self.timeout) as fetcher:
                result = fetcher.fetch(url, max_length=self.max_length)
                if result.get("status") == "success":
                    title = result.get("title", "")
                    content = result.get("content", "")
                    output = f"Title: {title}\nURL: {url}\n\n{content}"
                    self._log_result(f"{len(content)} chars from {url}")
                    return output
                err = result.get("error", "unknown error")
                logger.warning("Failed to fetch {}: {}", url, err)
                return f"Failed to fetch {url}: {err}"
        except Exception as exc:
            logger.exception("FetchContentTool error fetching {}", url)
            return f"Error fetching {url}: {exc}"


__all__ = ["FetchContentTool"]
