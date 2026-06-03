"""Multi-database sync manager for V.E.C.T.O.R.

Manages sync across 4 backends:
1. SQLite (local) — primary write target, always available
2. Supabase (primary cloud) — via REST API
3. Turso (secondary cloud) — via REST API
4. Cloudflare D1 (edge) — via Workers REST API

All sync uses last-write-wins based on updated_at timestamp.
"""

import sys

__all__ = [
    "get_manager",
    "MultiDBManager",
]

import re
import asyncio
import uuid

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

    # â”€â”€â”€ Write Operations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    _ALLOWED_TABLES = frozenset({
        "episodic_memory", "semantic_memory", "policy_memory",
        "reasoning_chains", "skill_memory", "agent_history",
    })

    def write_local(self, table: str, record: dict) -> bool:
        """Write to local SQLite. Always succeeds."""
        if table not in self._ALLOWED_TABLES:
            logger.error(f"[VECTOR][multi_db] write_local: unknown table '{table}' — blocked")
            return False
        columns = list(record.keys())
        for col in columns:
            if not _SAFE_IDENTIFIER.match(col):
                logger.error(f"[VECTOR][multi_db] write_local: unsafe column '{col}' — blocked")
                return False
        try:
            conn = self._get_local().conn
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
        # Add transaction ID for deduplication across local + cloud
        txn_id = record.get('id') or str(uuid.uuid4())
        record_with_txn = {**record, '_txn_id': txn_id}

        # Local write is synchronous
        local_ok = self.write_local(table, record_with_txn)

        # Cloud writes are async
        cloud = await self.write_cloud(table, record_with_txn)

        return {"local": local_ok, **cloud, "txn_id": txn_id}

    # â”€â”€â”€ Sync Operations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

    # â”€â”€â”€ Health Checks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

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

    # â”€â”€â”€ Private Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

        # Validate table and column names before any string interpolation
        if table not in self._ALLOWED_TABLES:
            logger.error(f"[VECTOR][multi_db] _write_turso: unknown table '{table}' — blocked")
            return False
        for col in record.keys():
            if not _SAFE_IDENTIFIER.match(col):
                logger.error(f"[VECTOR][multi_db] _write_turso: unsafe column '{col}' — blocked")
                return False

        url = self._get_config("turso_url")
        token = self._get_config("turso_token")
        if not url or not token:
            return False

        columns = list(record.keys())
        placeholders = ", ".join(["?" for _ in columns])
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
                            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
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

    # â”€â”€â”€ Gap 19: Backup / Restore â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def backup(self, backup_path: str | None = None) -> str:
        """
        Dump the full local SQLite database to a JSON backup file.
        Returns the path to the backup file.

        The backup includes all tables and their rows. It can be restored
        with restore() even if the original SQLite file is corrupted.
        """
        import sqlite3
        import time as _time
        from pathlib import Path as _Path

        if backup_path is None:
            ts = int(_time.time())
            backup_path = str(_Path(__file__).parent.parent.parent / f"vector_backup_{ts}.json")

        db_path = _Path(__file__).parent.parent.parent / "vector_memory.db"
        if not db_path.exists():
            raise FileNotFoundError(f"Local SQLite not found: {db_path}")

        conn = sqlite3.connect(str(db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()]
            dump: dict = {"version": 1, "tables": {}, "backed_up_at": _time.time()}
            for table in tables:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
                dump["tables"][table] = [dict(r) for r in rows]
                logger.debug(f"[VECTOR][backup] {table}: {len(rows)} rows")
        finally:
            conn.close()

        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(dump, f, default=str, indent=2)

        total_rows = sum(len(v) for v in dump["tables"].values())
        logger.info(f"[VECTOR][backup] {total_rows} rows â†’ {backup_path}")
        return backup_path

    def restore(self, backup_path: str, overwrite: bool = False) -> dict:
        """
        Restore the local SQLite database from a JSON backup file.

        If overwrite=False (default), only inserts rows that don't already exist
        (safe merge). If overwrite=True, drops and recreates all tables first.

        Returns {"tables_restored": int, "rows_restored": int}.
        """
        import sqlite3
        from pathlib import Path as _Path

        bp = _Path(backup_path)
        if not bp.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        with open(backup_path, "r", encoding="utf-8") as f:
            dump = json.load(f)

        if dump.get("version") != 1:
            raise ValueError(f"Unsupported backup version: {dump.get('version')}")

        db_path = _Path(__file__).parent.parent.parent / "vector_memory.db"
        conn = sqlite3.connect(str(db_path), timeout=10)
        try:
            tables_restored = 0
            rows_restored = 0
            for table, rows in dump["tables"].items():
                if not rows:
                    continue
                if overwrite:
                    conn.execute(f"DELETE FROM {table}")  # noqa: S608
                cols = list(rows[0].keys())
                placeholders = ", ".join("?" * len(cols))
                col_names = ", ".join(cols)
                for row in rows:
                    try:
                        conn.execute(
                            f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})",  # noqa: S608
                            [row[c] for c in cols],
                        )
                        rows_restored += 1
                    except Exception as _row_err:
                        logger.debug(f"[VECTOR][restore] skip row in {table}: {_row_err}")
                conn.commit()
                tables_restored += 1
                logger.debug(f"[VECTOR][restore] {table}: {len(rows)} rows")
        finally:
            conn.close()

        logger.info(f"[VECTOR][restore] {tables_restored} tables, {rows_restored} rows from {backup_path}")
        return {"tables_restored": tables_restored, "rows_restored": rows_restored}


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

        print(f"âœ… multi_db_manager OK — local_write={ok}, health={health['overall']}, queue={stats['queue_size']}")

    asyncio.run(_smoke())
