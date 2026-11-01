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
        # Quarantine kill-switch: names of cloud backends temporarily severed
        # from VECTOR (manual or auto-on-threat). Writes/pulls skip them. Local
        # SQLite cannot be quarantined — it is the always-on fallback.
        self._quarantined: set[str] = set()
        self._quarantine_reasons: dict[str, str] = {}
        logger.info("[VECTOR][multi_db] initialized")

    # ─── Quarantine kill-switch ─────────────────────────────────────────────────

    _QUARANTINABLE = frozenset({"supabase", "turso", "d1"})

    def quarantine(self, backend: str, reason: str = "manual") -> bool:
        """Sever a cloud backend from VECTOR. Writes/pulls skip it until reenable().

        'local' cannot be quarantined (it is the always-available store).
        Returns True if the backend was quarantined.
        """
        backend = backend.lower().strip()
        if backend not in self._QUARANTINABLE:
            logger.error(f"[VECTOR][multi_db] cannot quarantine '{backend}' "
                         f"(must be one of {sorted(self._QUARANTINABLE)})")
            return False
        self._quarantined.add(backend)
        self._quarantine_reasons[backend] = reason
        logger.warning(f"[VECTOR][multi_db] QUARANTINED {backend} — reason: {reason}")
        return True

    def reenable(self, backend: str) -> bool:
        """Reconnect a previously quarantined backend."""
        backend = backend.lower().strip()
        existed = backend in self._quarantined
        self._quarantined.discard(backend)
        self._quarantine_reasons.pop(backend, None)
        if existed:
            logger.info(f"[VECTOR][multi_db] reenabled {backend}")
        return existed

    def is_quarantined(self, backend: str) -> bool:
        return backend.lower().strip() in self._quarantined

    def backend_status(self) -> dict:
        """Per-backend enabled/quarantined view for db_status / HUD."""
        return {
            b: {
                "quarantined": b in self._quarantined,
                "reason": self._quarantine_reasons.get(b, ""),
            }
            for b in sorted(self._QUARANTINABLE)
        }

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

    # Per-table sync descriptor: primary-key column(s), the last-write-wins
    # timestamp column, and the full column list to upsert. Drives the generic
    # 6-table pull/merge below. (Column names are trusted constants, never user
    # input — safe to interpolate.)
    _TABLE_SPEC = {
        "episodic_memory": {
            "pk": ["id"], "ts": "timestamp",
            "cols": ["id", "event_type", "content", "tags",
                     "context_snapshot", "timestamp", "source"],
        },
        "semantic_memory": {
            "pk": ["key"], "ts": "updated_at",
            "cols": ["key", "value", "category", "confidence", "updated_at"],
        },
        "policy_memory": {
            "pk": ["action_type", "situation_hash"], "ts": "last_updated",
            "cols": ["action_type", "situation_hash", "avg_reward",
                     "sample_count", "last_updated"],
        },
        "reasoning_chains": {
            "pk": ["chain_id"], "ts": "timestamp",
            "cols": ["chain_id", "situation", "goal_ids", "steps",
                     "action_taken", "outcome", "reward",
                     "is_training_data", "timestamp"],
        },
        "skill_memory": {
            "pk": ["skill_name"], "ts": "last_practiced",
            "cols": ["skill_name", "confidence", "last_practiced",
                     "evidence", "related_skills"],
        },
        "agent_history": {
            "pk": ["agent_id", "generation"], "ts": "died_at",
            "cols": ["agent_id", "agent_name", "district", "generation",
                     "final_hp", "ghost_memory", "died_at"],
        },
    }

    def _merge_rows(self, table: str, rows: list[dict]) -> int:
        """Last-write-wins upsert of cloud rows into local SQLite.

        Keeps a local row when it is newer than the incoming one (compared on the
        table's timestamp column), otherwise INSERT OR REPLACE. Handles composite
        primary keys. Returns rows merged.
        """
        spec = self._TABLE_SPEC.get(table)
        if not spec or not rows:
            return 0
        pk, ts, cols = spec["pk"], spec["ts"], spec["cols"]
        where = " AND ".join(f"{c}=?" for c in pk)
        placeholders = ", ".join("?" for _ in cols)
        conn = self._get_local().conn
        merged = 0
        for row in rows:
            try:
                existing = conn.execute(
                    f"SELECT {ts} FROM {table} WHERE {where}",  # noqa: S608 - trusted cols
                    [row.get(c) for c in pk],
                ).fetchone()
                if existing is None or (row.get(ts) or "") > (existing[0] or ""):
                    conn.execute(
                        f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) "  # noqa: S608
                        f"VALUES ({placeholders})",
                        [row.get(c) for c in cols],
                    )
                    merged += 1
            except Exception as e:
                logger.debug(f"[VECTOR][multi_db] merge skip {table}: {e}")
        conn.commit()
        return merged

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

    async def write_cloud(
        self,
        table: str,
        record: dict,
        *,
        queue_on_failure: bool = True,
    ) -> dict:
        """Write to cloud DBs. Falls back to queue on failure."""
        results = {"supabase": False, "turso": False, "d1": False}

        # Try Supabase first (unless quarantined)
        if "supabase" not in self._quarantined and await self._write_supabase(table, record):
            results["supabase"] = True
            return results

        # Fall back to Turso (unless quarantined)
        if "turso" not in self._quarantined and await self._write_turso(table, record):
            results["turso"] = True
            return results

        # Queue for later
        if queue_on_failure:
            self.queue_sync({"table": table, "record": record, "attempt": 0})
            logger.warning("[VECTOR][multi_db] Cloud write failed — queued for retry")
        return results

    async def write_all(self, table: str, record: dict, tier: str | None = None) -> dict:
        """Write to local + cloud simultaneously.

        ``tier`` ("critical"|"bulk") is auto-classified from the record when not
        given (see core.memory.tiering). Critical data is protected from local
        forgetting; bulk is a local cache the forgetting pass may prune after sync.
        Cloud is the durable source of truth for both.
        """
        # Transaction id for dedup/audit — returned to caller, NOT stored as a
        # column (the tables have no _txn_id column; injecting it broke every
        # write_all local+cloud write).
        txn_id = record.get('id') or str(uuid.uuid4())

        if tier is None:
            try:
                from core.memory import tiering
                tier = tiering.classify(table, record)
            except Exception:
                tier = "bulk"

        # Local write is synchronous
        local_ok = self.write_local(table, record)

        # Cloud writes are async
        cloud = await self.write_cloud(table, record)

        return {"local": local_ok, **cloud, "txn_id": txn_id, "tier": tier}

    # â”€â”€â”€ Sync Operations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _push_local_to_cloud(self, since_ts: str) -> int | None:
        """Bulk-push local SQLite rows newer than since_ts to Supabase + Turso.

        Reads each of the 6 allowed tables from the encrypted local DB, filters
        rows whose timestamp column is greater than since_ts (ISO-8601 string
        comparison works because all timestamps are UTC ISO format), then batch-
        upserts them to any non-quarantined cloud backend.  Returns total rows sent.
        """
        if not httpx:
            return None

        total = 0
        conn = self._get_local().conn

        supabase_url = self._get_config("supabase_url")
        supabase_key = self._get_config("supabase_key")
        turso_url = self._get_config("turso_url")
        turso_token = self._get_config("turso_token")

        supabase_ok = bool(supabase_url and supabase_key and "supabase" not in self._quarantined)
        turso_ok = bool(turso_url and turso_token and "turso" not in self._quarantined)

        if not supabase_ok and not turso_ok:
            return None

        all_succeeded = True

        for table, spec in self._TABLE_SPEC.items():
            ts_col = spec["ts"]
            cols = spec["cols"]
            try:
                rows_raw = conn.execute(
                    f"SELECT {', '.join(cols)} FROM {table} WHERE {ts_col} > ?",  # noqa: S608
                    (since_ts,),
                ).fetchall()
            except Exception as e:
                logger.debug(f"[VECTOR][multi_db] push read {table}: {e}")
                continue

            if not rows_raw:
                continue

            records = [dict(zip(cols, row)) for row in rows_raw]

            # Supabase batch upsert — merge-duplicates resolves PK conflicts
            if supabase_ok:
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.post(
                            f"{supabase_url}/rest/v1/{table}",
                            headers={
                                "apikey": supabase_key,
                                "Authorization": f"Bearer {supabase_key}",
                                "Content-Type": "application/json",
                                "Prefer": "resolution=merge-duplicates",
                            },
                            json=records,
                        )
                        if resp.status_code in (200, 201):
                            total += len(records)
                            logger.debug(f"[VECTOR][multi_db] push Supabase {table}: {len(records)} rows")
                        else:
                            all_succeeded = False
                except Exception as e:
                    all_succeeded = False
                    logger.debug(f"[VECTOR][multi_db] push Supabase {table} failed: {e}")

            # Turso batch upsert — INSERT OR REPLACE per row
            if turso_ok:
                try:
                    placeholders = ", ".join("?" for _ in cols)
                    statements = [
                        f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"  # noqa: S608
                        for _ in records
                    ]
                    params = [list(r.get(c) for c in cols) for r in records]
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.post(
                            f"{turso_url}/v1/pipeline",
                            headers={
                                "Authorization": f"Bearer {turso_token}",
                                "Content-Type": "application/json",
                            },
                            json={"statements": statements, "params": params},
                        )
                        if resp.status_code in (200, 201):
                            logger.debug(f"[VECTOR][multi_db] push Turso {table}: {len(records)} rows")
                        else:
                            all_succeeded = False
                except Exception as e:
                    all_succeeded = False
                    logger.debug(f"[VECTOR][multi_db] push Turso {table} failed: {e}")

        return total if all_succeeded else None

    async def sync_all(self) -> dict:
        """Full 24h sync: push new local rows → drain retry queue → pull from cloud.

        Order matters: push first so the pull's LWW merge sees our latest data,
        not an older cloud snapshot that would overwrite fresh local writes.
        """
        results = {"queued": 0, "pushed": 0, "pushed_local": 0, "pulled": 0, "conflicts": 0}

        # 0. Bulk-push local rows written since last sync (district agents write
        #    directly to SQLite via episodic.py, bypassing write_all — this closes
        #    that gap so every row eventually reaches cloud).
        since = self._last_sync.get("local") or "1970-01-01T00:00:00+00:00"
        local_push_completed = False
        try:
            pushed_local = await self._push_local_to_cloud(since)
            if pushed_local is not None:
                local_push_completed = True
                results["pushed_local"] = pushed_local
        except Exception as e:
            logger.warning(f"[VECTOR][multi_db] bulk push skipped: {e}")

        # 1. Process queued syncs (previously-failed individual writes)
        queued = len(self._sync_queue)
        results["queued"] = queued

        # Process only the snapshot present at entry. Failed items stay queued
        # for the next scheduler tick instead of feeding this same loop forever.
        for _ in range(queued):
            item = self._sync_queue.popleft()
            attempt = item.get("attempt", 0)
            if attempt >= 3:
                logger.warning(f"[VECTOR][multi_db] Dropping item after 3 failed attempts: {item}")
                continue

            item["attempt"] = attempt + 1
            table = item["table"]
            record = item["record"]

            cloud = await self.write_cloud(table, record, queue_on_failure=False)
            if cloud.get("supabase") or cloud.get("turso"):
                results["pushed"] += 1
            else:
                self._sync_queue.append(item)

        # 2. Pull latest from cloud DBs
        supabase_pulled = False
        try:
            supabase_pulled = await self._pull_supabase()
            if supabase_pulled:
                results["pulled"] += 1
        except Exception as e:
            logger.warning(f"[VECTOR][multi_db] Supabase pull failed: {e}")

        turso_pulled = False
        try:
            turso_pulled = await self._pull_turso()
            if turso_pulled:
                results["pulled"] += 1
        except Exception as e:
            logger.warning(f"[VECTOR][multi_db] Turso pull failed: {e}")

        # 3. Update sync timestamps
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._last_sync = {
            "local": now if local_push_completed else self._last_sync["local"],
            "supabase": now if supabase_pulled else self._last_sync["supabase"],
            "turso": now if turso_pulled else self._last_sync["turso"],
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

        # Cloudflare D1 — reached through the deployed Worker, not a direct DB URL.
        # cf_worker_url (full /health endpoint) is the canonical probe target;
        # d1_url kept as an explicit override.
        d1_url = self._get_config("d1_url") or self._get_config("cf_worker_url")
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

    async def _pull_supabase(self) -> bool:
        """Pull all 6 memory tables from Supabase and merge (last-write-wins)."""
        url = self._get_config("supabase_url")
        key = self._get_config("supabase_key")
        if not url or not key or not httpx:
            return False
        if "supabase" in self._quarantined:
            logger.info("[VECTOR][multi_db] Supabase quarantined — pull skipped")
            return False
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        total = 0
        request_succeeded = False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for table, spec in self._TABLE_SPEC.items():
                    try:
                        resp = await client.get(
                            f"{url}/rest/v1/{table}",
                            headers=headers,
                            params={"select": ",".join(spec["cols"]),
                                    "order": f"{spec['ts']}.desc", "limit": "500"},
                        )
                        if resp.status_code != 200:
                            continue
                        request_succeeded = True
                        merged = self._merge_rows(table, resp.json())
                        total += merged
                    except Exception as e:
                        logger.debug(f"[VECTOR][multi_db] Supabase pull {table}: {e}")
            logger.info(f"[VECTOR][multi_db] Supabase pull: {total} rows merged across 6 tables")
        except Exception as e:
            logger.warning(f"[VECTOR][multi_db] Supabase pull failed: {e}")
            return False
        return request_succeeded

    async def _pull_turso(self) -> bool:
        """Pull all 6 memory tables from Turso and merge (last-write-wins)."""
        url = self._get_config("turso_url")
        token = self._get_config("turso_token")
        if not url or not token or not httpx:
            return False
        if "turso" in self._quarantined:
            logger.info("[VECTOR][multi_db] Turso quarantined — pull skipped")
            return False
        total = 0
        request_succeeded = False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for table, spec in self._TABLE_SPEC.items():
                    try:
                        resp = await client.post(
                            f"{url}/v1/pipeline",
                            headers={"Authorization": f"Bearer {token}",
                                     "Content-Type": "application/json"},
                            json={"statements": [
                                f"SELECT {', '.join(spec['cols'])} FROM {table} "
                                f"ORDER BY {spec['ts']} DESC LIMIT 500"
                            ]},
                        )
                        if resp.status_code != 200:
                            continue
                        request_succeeded = True
                        results = resp.json().get("results", [{}])[0]
                        cols = [c["name"] for c in results.get("columns", [])]
                        rows = [dict(zip(cols, vals)) for vals in results.get("rows", [])]
                        total += self._merge_rows(table, rows)
                    except Exception as e:
                        logger.debug(f"[VECTOR][multi_db] Turso pull {table}: {e}")
            logger.info(f"[VECTOR][multi_db] Turso pull: {total} rows merged across 6 tables")
        except Exception as e:
            logger.warning(f"[VECTOR][multi_db] Turso pull failed: {e}")
            return False
        return request_succeeded

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

        from core.memory.db_utils import configured_db_path
        db_path = configured_db_path()
        if not db_path.exists():
            raise FileNotFoundError(f"Local SQLite not found: {db_path}")

        conn = sqlite3.connect(str(db_path), timeout=10, check_same_thread=False)
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
        logger.info(f"[VECTOR][backup] {total_rows} rows → {backup_path}")
        return backup_path

    def restore(self, backup_path: str, overwrite: bool = False) -> dict:
        """
        Restore the local SQLite database from a JSON backup file.

        If overwrite=False (default), only inserts rows that don't already exist
        (safe merge). If overwrite=True, drops and recreates all tables first.

        Returns {"tables_restored": int, "rows_restored": int}.

        SECURITY: backup_path is confined to the VECTOR repo root (the same
        tree backup()'s own default path writes into) to prevent restoring
        from an arbitrary file the process can read. table/column names come
        from the backup JSON's own keys, not a fixed schema, so each is
        validated against the TARGET DATABASE's real, live schema (queried
        fresh via sqlite_master / PRAGMA table_info, not the file's own
        claims) before ever being interpolated into SQL -- a crafted backup
        file cannot inject arbitrary table/column names into DELETE/INSERT
        this way. Unknown tables/columns in the file are skipped, not errored,
        so a normal backup-then-restore round trip is unaffected.
        """
        import sqlite3
        from pathlib import Path as _Path

        _repo_root = _Path(__file__).resolve().parent.parent.parent
        bp = _Path(backup_path).resolve()
        if bp != _repo_root and not bp.is_relative_to(_repo_root):
            raise ValueError(f"backup_path '{backup_path}' is outside the VECTOR repo root — refused.")
        if not bp.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        with open(bp, "r", encoding="utf-8") as f:
            dump = json.load(f)

        if dump.get("version") != 1:
            raise ValueError(f"Unsupported backup version: {dump.get('version')}")

        from core.memory.db_utils import configured_db_path
        db_path = configured_db_path()
        conn = sqlite3.connect(str(db_path), timeout=10, check_same_thread=False)
        try:
            real_tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            tables_restored = 0
            rows_restored = 0
            for table, rows in dump["tables"].items():
                if not rows:
                    continue
                if table not in real_tables or not _SAFE_IDENTIFIER.match(table):
                    logger.warning(f"[VECTOR][restore] skip unknown/unsafe table {table!r}")
                    continue
                if overwrite:
                    conn.execute(f"DELETE FROM {table}")  # table validated against real schema above
                real_cols = {
                    r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()  # table validated above
                }
                cols = [c for c in rows[0].keys() if c in real_cols and _SAFE_IDENTIFIER.match(c)]
                if not cols:
                    logger.warning(f"[VECTOR][restore] skip {table!r}: no recognized columns in backup")
                    continue
                placeholders = ", ".join("?" * len(cols))
                col_names = ", ".join(cols)
                for row in rows:
                    try:
                        conn.execute(
                            f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})",  # cols/table validated above
                            [row.get(c) for c in cols],
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

        print(f"✅ multi_db_manager OK — local_write={ok}, health={health['overall']}, queue={stats['queue_size']}")

    asyncio.run(_smoke())
