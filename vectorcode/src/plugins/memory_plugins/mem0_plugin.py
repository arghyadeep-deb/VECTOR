"""Mem0 memory plugin — LLM fact extraction via Mem0 Platform API."""

from loguru import logger
import os
from typing import Any, Optional


try:
    from mem0 import Memory
    _MEM0 = True
except ImportError:
    _MEM0 = False


class Mem0Plugin:
    def __init__(self):
        self._client = None
        self._user_id = os.environ.get("MEM0_USER_ID", "vector-user")

    async def initialize(self):
        if not _MEM0:
            logger.warning("mem0 not installed. Run: pip install mem0ai")
            return
        api_key = os.environ.get("MEM0_API_KEY", "")
        if api_key:
            self._client = Memory(api_key=api_key)

    async def add(self, messages: list[dict]) -> dict:
        if not self._client: return {"error": "mem0 not initialized"}
        try:
            result = self._client.add(messages, user_id=self._user_id)
            return {"status": "stored", "result": result}
        except Exception as e:
            return {"error": str(e)}

    async def search(self, query: str, limit: int = 5) -> list:
        if not self._client: return []
        try:
            results = self._client.search(query, user_id=self._user_id, limit=limit)
            return results
        except Exception as e:
            logger.warning(f"mem0 search failed: {e}")
            return []

    async def get_history(self) -> list:
        if not self._client: return []
        return self._client.get_history(user_id=self._user_id)
