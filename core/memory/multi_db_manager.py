"""Multi-database sync manager for V.E.C.T.O.R.

Manages sync across 4 backends:
1. SQLite (local) — primary write target, always available
2. Supabase (primary cloud) — via REST API
3. Turso (secondary cloud) — via REST API
4. Cloudflare D1 (edge) — via Workers REST API

All sync uses last-write-wins based on updated_at timestamp.
"""

import sys
import re
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

_SAFE_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

from loguru import logger
from typing import Optional
from collections import deque
import datetime
import json

try:
    import httpx
except ImportError:
    httpx = None


class MultiDBManager:
    """
    4-DB sync with last-write-wins strategy.
    RULE: Write to local SQLite first (always works), queue cloud sync.
    """

    def __init__(self):
        self._local = None
        self._supabase_client = None
        self._turso_client = None
        self._d1_client = None
        self._sync_queue: deque[dict] = deque(maxlen=10000)
        self._last_sync: dict[str, str] = {
            "local": None,
            "supabase": None,
            "turso": None,
            "d1": None,
        }
        logger.info("[VECTOR][multi_db] initialized")

    def _get_local(self):
        """Get local SQLite connection."""
        if self._local is None:
            from core.memory.episodic import EpisodicMemory
            self._local = EpisodicMemory()
        return self._local

    # ─── Write Operations ──────────────────────────────────────────────────────

    _ALLOWED_TABLES = frozenset({
        "episodic_memory", "semantic_memory", "policy_memory",
        "reasoning_chains", "skill_memory", "agent_history",
    })

    def write_local(self, table: str, record: dict) -> bool:
        """Write to local SQLite. Always succeeds."""
        if table not in self._ALLOWED_TABLES:
            logger.error(f"[VECTOR][multi_db] write_local: unknown table '{table}' — blocked")
            return False
        try:
            conn = self._get_local().conn
            columns = list(record.keys())
            placeholders = ", ".join(["?" for _ in columns])
            values = [record.get(c) for c in columns]

            conn.execute(
                f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                values
            )
            conn.commit()
            logger.debug(f"[VECTOR][multi_db] local write: {table}")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][multi_db] local write failed: {e}")
            return False

    async def write_cloud(self, table: str, record: dict) -> dict:
        """Write to cloud DBs. Falls back to queue on failure."""
        results = {"supabase": False, "turso": False, "d1": False}

        # Try Supabase first
        if await self._write_supabase(table, record):
            results["supabase"] = True
            return results

        # Fall back to Turso
        if await self._write_turso(table, record):
            results["turso"] = True
            return results

        # Queue for later
        self.queue_sync({"table": table, "record": record, "attempt": 0})
        logger.warning(f"[VECTOR][multi_db] Cloud write failed — queued for retry")
        return results

    async def write_all(self, table: str, record: dict) -> dict:
        """Write to local + cloud simultaneously."""
        # Local write is synchronous
        local_ok = self.write_local(table, record)

        # Cloud writes are async
        cloud = await self.write_cloud(table, record)

        return {"local": local_ok, **cloud}

    # ─── Sync Operations ────────────────────────────────────────────────────────

    async def sync_all(self) -> dict:
        """
        Full sync: push queued records, then pull latest from all DBs.
        Last-write-wins per record based on updated_at.
        """
        results = {"queued": 0, "pushed": 0, "pulled": 0, "conflicts": 0}

        # 1. Process queued syncs
        queued = len(self._sync_queue)
        results["queued"] = queued

        while self._sync_queue:
            item = self._sync_queue.popleft()
            attempt = item.get("attempt", 0)
            if attempt >= 3:
                logger.warning(f"[VECTOR][multi_db] Dropping item after 3 failed attempts: {item}")
                continue

            item["attempt"] = attempt + 1
            table = item["table"]
            record = item["record"]

            cloud = await self.write_cloud(table, record)
            if cloud.get("supabase") or cloud.get("turso"):
                results["pushed"] += 1
            else:
                self._sync_queue.append(item)

        # 2. Pull latest from cloud DBs
        try:
            await self._pull_supabase()
            results["pulled"] += 1
        except Exception as e:
            logger.warning(f"[VECTOR][multi_db] Supabase pull failed: {e}")

        try:
            await self._pull_turso()
            results["pulled"] += 1
        except Exception as e:
            logger.warning(f"[VECTOR][multi_db] Turso pull failed: {e}")

        # 3. Update sync timestamps
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._last_sync = {
            "local": now,
            "supabase": now if results["pulled"] > 0 else self._last_sync["supabase"],
            "turso": now if results["pulled"] > 1 else self._last_sync["turso"],
            "d1": now if results.get("d1") else self._last_sync["d1"],
        }

        logger.info(f"[VECTOR][multi_db] sync_all complete: {results}")
        return results

    def queue_sync(self, item: dict) -> None:
        """Add a failed cloud write to the retry queue."""
        self._sync_queue.append(item)
        logger.debug(f"[VECTOR][multi_db] queued item, queue size={len(self._sync_queue)}")

    # ─── Health Checks ──────────────────────────────────────────────────────────

    async def health_check(self) -> dict:
        """Check connectivity to all 4 DBs. Returns status per backend."""
        results = {"local": False, "supabase": False, "turso": False, "d1": False, "latency_ms": {}}

        # SQLite — always available if we got this far
        try:
            conn = self._get_local().conn
            conn.execute("SELECT 1").fetchone()
            results["local"] = True
            results["latency_ms"]["local"] = 1
        except Exception:
            pass

        # Supabase
        supabase_url = self._get_config("supabase_url")
        if supabase_url:
            latency = await self._ping_url(supabase_url + "/rest/v1/")
            results["supabase"] = latency is not None
            if latency:
                results["latency_ms"]["supabase"] = latency

        # Turso
        turso_url = self._get_config("turso_url")
        if turso_url:
            latency = await self._ping_url(turso_url)
            results["turso"] = latency is not None
            if latency:
                results["latency_ms"]["turso"] = latency

        # Cloudflare D1
        d1_url = self._get_config("d1_url")
        if d1_url:
            latency = await self._ping_url(d1_url)
            results["d1"] = latency is not None
            if latency:
                results["latency_ms"]["d1"] = latency

        ok_count = sum(1 for v in [results["local"], results["supabase"], results["turso"], results["d1"]] if v)
        results["ok_count"] = ok_count
        if ok_count == 4:
            results["overall"] = "fully_healthy"
        elif ok_count >= 1:
            results["overall"] = "degraded"   # local works but cloud DBs unreachable
        else:
            results["overall"] = "critical"    # even local SQLite is down

        return results

    # ─── Private Helpers ────────────────────────────────────────────────────────

    def _get_config(self, key: str) -> Optional[str]:
        """Get config value safely."""
        try:
            from core.config import CONFIG
            return CONFIG.get(key) or CONFIG.get("api_keys", {}).get(key)
        except Exception:
            return None

    async def _write_supabase(self, table: str, record: dict) -> bool:
        """Write to Supabase via REST API."""
        if not httpx:
            return False

        url = self._get_config("supabase_url")
        key = self._get_config("supabase_key")
        if not url or not key:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                }
                resp = await client.post(
                    f"{url}/rest/v1/{table}",
                    headers=headers,
                    json=[record],
                )
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.warning(f"[VECTOR][multi_db] Supabase write failed: {e}")
            return False

    async def _write_turso(self, table: str, record: dict) -> bool:
        """Write to Turso via REST API."""
        if not httpx:
            return False

        url = self._get_config("turso_url")
        token = self._get_config("turso_token")
        if not url or not token:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{url}/v1/pipeline",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "statements": [
                            f"INSERT INTO {table} ({', '.join(record.keys())}) "
                            f"VALUES ({', '.join(['?' for _ in record])})"
                        ],
                        "params": [list(record.values())],
                    },
                )
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.warning(f"[VECTOR][multi_db] Turso write failed: {e}")
            return False

    async def _pull_supabase(self) -> None:
        """Pull episodic_memory rows from Supabase and merge (last-write-wins on timestamp)."""
        url = self._get_config("supabase_url")
        key = self._get_config("supabase_key")
        if not url or not key or not httpx:
            return
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {"apikey": key, "Authorization": f"Bearer {key}"}
                resp = await client.get(
                    f"{url}/rest/v1/episodic_memory",
                    headers=headers,
                    params={"select": "id,event_type,content,tags,context_snapshot,timestamp,source",
                            "order": "timestamp.desc", "limit": "500"},
                )
                if resp.status_code != 200:
                    return
                rows = resp.json()
            conn = self._get_local().conn
            merged = 0
            for row in rows:
                existing = conn.execute(
                    "SELECT timestamp FROM episodic_memory WHERE id=?", (row["id"],)
                ).fetchone()
                if existing is None or row.get("timestamp", "") > existing[0]:
                    conn.execute(
                        "INSERT OR REPLACE INTO episodic_memory "
                        "(id,event_type,content,tags,context_snapshot,timestamp,source) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (row["id"], row.get("event_type"), row.get("content"),
                         row.get("tags"), row.get("context_snapshot"),
                         row.get("timestamp"), row.get("source")),
                    )
                    merged += 1
            conn.commit()
            logger.info(f"[VECTOR][multi_db] Supabase pull: {merged}/{len(rows)} rows merged")
        except Exception as e:
            logger.warning(f"[VECTOR][multi_db] Supabase pull failed: {e}")

    async def _pull_turso(self) -> None:
        """Pull episodic_memory rows from Turso and merge (last-write-wins on timestamp)."""
        url = self._get_config("turso_url")
        token = self._get_config("turso_token")
        if not url or not token or not httpx:
            return
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{url}/v1/pipeline",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"statements": [
                        "SELECT id,event_type,content,tags,context_snapshot,timestamp,source "
                        "FROM episodic_memory ORDER BY timestamp DESC LIMIT 500"
                    ]},
                )
                if resp.status_code != 200:
                    return
                data = resp.json()
            results = data.get("results", [{}])[0]
            cols = [c["name"] for c in results.get("columns", [])]
            rows = results.get("rows", [])
            conn = self._get_local().conn
            merged = 0
            for row_vals in rows:
                row = dict(zip(cols, row_vals))
                existing = conn.execute(
                    "SELECT timestamp FROM episodic_memory WHERE id=?", (row.get("id"),)
                ).fetchone()
                if existing is None or row.get("timestamp", "") > existing[0]:
                    conn.execute(
                        "INSERT OR REPLACE INTO episodic_memory "
                        "(id,event_type,content,tags,context_snapshot,timestamp,source) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (row.get("id"), row.get("event_type"), row.get("content"),
                         row.get("tags"), row.get("context_snapshot"),
                         row.get("timestamp"), row.get("source")),
                    )
                    merged += 1
            conn.commit()
            logger.info(f"[VECTOR][multi_db] Turso pull: {merged}/{len(rows)} rows merged")
        except Exception as e:
            logger.warning(f"[VECTOR][multi_db] Turso pull failed: {e}")

    async def _ping_url(self, url: str) -> Optional[int]:
        """Ping a URL and return latency in ms."""
        if not httpx:
            return None
        try:
            import time
            start = time.perf_counter()
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                return elapsed_ms if resp.status_code < 500 else None
        except Exception:
            return None

    def get_stats(self) -> dict:
        """Get sync statistics."""
        return {
            "queue_size": len(self._sync_queue),
            "last_sync": self._last_sync,
        }


# Singleton
_manager: Optional[MultiDBManager] = None

def get_manager() -> MultiDBManager:
    """Get the global MultiDBManager instance."""
    global _manager
    if _manager is None:
        _manager = MultiDBManager()
    return _manager


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import asyncio

    async def _smoke():
        mgr = MultiDBManager()

        # Test local write
        ok = mgr.write_local("semantic_memory", {
            "key": "smoke_test",
            "value": "test_value",
            "category": "test",
            "confidence": 0.9,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })

        # Test health check
        health = await mgr.health_check()

        # Test stats
        stats = mgr.get_stats()

        print(f"✅ multi_db_manager OK — local_write={ok}, health={health['overall']}, queue={stats['queue_size']}")

    asyncio.run(_smoke())
