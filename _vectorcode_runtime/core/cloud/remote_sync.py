"""RemoteSync — push/pull episodic memory records to/from Supabase."""
from __future__ import annotations

import time
from typing import Optional

from loguru import logger

try:
    import httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False


class RemoteSync:
    """Sync VECTOR's local episodic_memory to Supabase cloud storage.

    Gracefully degrades when Supabase credentials are absent — all methods
    return empty results and log a warning, never crashing the caller.

    Usage:
        sync = RemoteSync()
        pushed = await sync.push_episodic(records)
        pulled = await sync.pull_episodic(since=time.time() - 3600)
        await sync.sync_now()
    """

    def __init__(self) -> None:
        try:
            from core.config import CONFIG
            self._url = (CONFIG.get("supabase_url") or "").rstrip("/")
            self._key = CONFIG.get("supabase_key") or ""
        except Exception:
            self._url = ""
            self._key = ""

    def _available(self) -> bool:
        return bool(self._url and self._key and _HTTPX_OK)

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def push_episodic(self, records: list[dict]) -> int:
        """Upsert episodic_memory records to Supabase.

        Each record should have at minimum: id, event_type, content, timestamp.
        Returns the number of records successfully pushed (0 on failure).
        """
        if not records:
            return 0
        if not self._available():
            logger.warning("[VECTOR][remote_sync] Supabase not configured — push skipped")
            return 0

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._url}/rest/v1/episodic_memory",
                    headers={**self._headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
                    json=records,
                )
                resp.raise_for_status()
                pushed = len(resp.json()) if resp.text else len(records)
                logger.info("[VECTOR][remote_sync] pushed {} episodic records", pushed)
                return pushed
        except Exception as e:
            logger.error("[VECTOR][remote_sync] push failed: {}", e)
            return 0

    async def pull_episodic(self, since: Optional[float] = None) -> list[dict]:
        """Pull episodic_memory records from Supabase created after `since` (epoch seconds).

        Returns an empty list on failure or when not configured.
        """
        if not self._available():
            logger.warning("[VECTOR][remote_sync] Supabase not configured — pull skipped")
            return []

        since_ts = since or (time.time() - 86400)  # default: last 24h
        from datetime import datetime, timezone
        since_iso = datetime.fromtimestamp(since_ts, tz=timezone.utc).isoformat()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self._url}/rest/v1/episodic_memory",
                    headers=self._headers(),
                    params={"created_at": f"gte.{since_iso}", "order": "created_at.asc"},
                )
                resp.raise_for_status()
                records = resp.json()
                logger.info("[VECTOR][remote_sync] pulled {} episodic records since {}", len(records), since_iso)
                return records
        except Exception as e:
            logger.error("[VECTOR][remote_sync] pull failed: {}", e)
            return []

    async def sync_now(self) -> dict:
        """Push recent local records then pull remote records.

        Returns summary dict with pushed/pulled counts.
        """
        if not self._available():
            logger.warning("[VECTOR][remote_sync] Supabase not configured — sync skipped")
            return {"pushed": 0, "pulled": 0}

        try:
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            recent = mem.recall(limit=100, min_confidence=0.0)
            local_records = [
                {
                    "id": r.get("id"),
                    "event_type": r.get("event_type"),
                    "content": r.get("content"),
                    "tags": r.get("tags", []),
                    "source": r.get("source"),
                    "confidence": r.get("confidence", 1.0),
                }
                for r in recent
                if r.get("id")
            ]
        except Exception as e:
            logger.warning("[VECTOR][remote_sync] could not read local memory: {}", e)
            local_records = []

        pushed = await self.push_episodic(local_records)
        pulled = await self.pull_episodic(since=time.time() - 3600)
        return {"pushed": pushed, "pulled": len(pulled)}


if __name__ == "__main__":
    import asyncio
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    sync = RemoteSync()
    available = sync._available()
    result = asyncio.run(sync.sync_now())
    if available:
        print(f"OK remote_sync.py — pushed={result['pushed']} pulled={result['pulled']}")
    else:
        print("OK remote_sync.py — degraded (no Supabase creds configured)")
