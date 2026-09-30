from core.memory.db_utils import apply_pragmas
import asyncio
import datetime
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.db_utils import configured_db_path
from core.inference.vectorcode_llm import chat

class DataEngineer(AgentBase):
    """
    ETL/ELT pipeline manager for VECTOR's own data using Bronze/Silver/Gold
    lakehouse pattern.
    - Bronze: raw VECTOR SQLite tables (episodic_memory, policy_memory, etc.)
    - Silver: cleaned and normalized semantic/skill memory
    - Gold: insights and aggregates (produced by AnalyticsReporter)
    RULE 11: local models only — never Claude API at runtime.
    """

    BRONZE_TABLES = [
        "episodic_memory",
        "policy_memory",
        "reasoning_chains",
        "agent_history",
    ]

    SILVER_TABLES = [
        "semantic_memory",
        "skill_memory",
    ]

    # Path to VECTOR's primary SQLite DB (same as CONFIG['db_path'])
    VECTOR_DB_PATH: Path = configured_db_path()

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="DataEngineer",
            district="data_analytics",
            generation=generation,
        )
        self.capabilities = ["INT", "bronze_to_silver", "contract", "data_analytics", "etl", "health", "id", "pipeline", "profile"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("coder", "vector-coder")
        self._db_lock = threading.RLock()
        logger.info(f"[VECTOR][data_engineer] initialized gen={generation} db={self.VECTOR_DB_PATH}")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _open_db(self) -> sqlite3.Connection | None:
        """Open a read connection to VECTOR_DB_PATH. Returns None if DB not found."""
        if not self.VECTOR_DB_PATH.exists():
            logger.warning(f"[VECTOR][data_engineer] DB not found at {self.VECTOR_DB_PATH}")
            return None
        try:
            # 2026-08-05: this used plain sqlite3.connect() against the main DB,
            # which is SQLCipher-encrypted — so every call failed with
            # "file is not a database". It was failing silently-ish in a loop:
            # 612 such errors in a single live run's log, meaning every
            # data_engineer pipeline check has been a no-op.
            #
            # Callers of _open_db() close the connection they get (see the
            # conn.close() calls below), so the shared singleton from
            # get_db_connection() must NOT be handed out here — closing it
            # would take the rest of VECTOR's memory access down with it.
            # An own keyed connection is the right shape, matching the existing
            # precedent in districts/emergency/log.py:_open_conn().
            conn = None
            row_factory = sqlite3.Row
            try:
                from core.memory import episodic
                if getattr(episodic, "_USE_SQLCIPHER", False):
                    conn = episodic._open_sqlcipher_connection(str(self.VECTOR_DB_PATH))
                    # The Row class must come from the SAME driver as the
                    # connection: sqlite3.Row raises
                    # "Row() argument 1 must be sqlite3.Cursor, not
                    # sqlcipher3.dbapi2.Cursor" on a sqlcipher cursor. Same
                    # reason districts/emergency/log.py carries a _row_factory().
                    from sqlcipher3 import dbapi2 as _sqlcipher_dbapi
                    row_factory = _sqlcipher_dbapi.Row
            except Exception as e:
                logger.warning(f"[VECTOR][data_engineer] SQLCipher open failed, trying plain sqlite: {e}")
                conn = None
                row_factory = sqlite3.Row
            if conn is None:
                conn = sqlite3.connect(str(self.VECTOR_DB_PATH), check_same_thread=False)
            apply_pragmas(conn)
            conn.row_factory = row_factory
            return conn
        except Exception as e:
            logger.error(f"[VECTOR][data_engineer] DB open failed: {e}")
            return None

    # ── Core pipeline methods ─────────────────────────────────────────────────

    def inspect_pipeline_health(self) -> dict:
        """
        Checks DB existence, counts rows in each table, checks NULL-heavy columns,
        WAL mode status.
        Returns {tables: {name: {rows, nulls_pct, last_updated}}, health_score, wal_mode}.
        """
        db_exists = self.VECTOR_DB_PATH.exists()
        table_stats: dict[str, dict] = {}
        health_score = 100
        wal_mode = False

        if not db_exists:
            logger.warning(f"[VECTOR][data_engineer] DB missing at {self.VECTOR_DB_PATH}")
            return {
                "db_exists": False,
                "db_path": str(self.VECTOR_DB_PATH),
                "tables": {},
                "health_score": 0,
                "wal_mode": False,
                "issues": ["Database file does not exist"],
            }

        conn = self._open_db()
        if conn is None:
            return {
                "db_exists": True,
                "db_path": str(self.VECTOR_DB_PATH),
                "tables": {},
                "health_score": 0,
                "wal_mode": False,
                "issues": ["Cannot open database"],
            }

        issues: list[str] = []
        with self._db_lock:
            try:
                # Check WAL mode
                row = conn.execute("PRAGMA journal_mode").fetchone()
                wal_mode = row and row[0].lower() == "wal"

                all_tables = self.BRONZE_TABLES + self.SILVER_TABLES
                existing_tables = {
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }

                for table in all_tables:
                    if table not in existing_tables:
                        table_stats[table] = {
                            "rows": 0,
                            "nulls_pct": 0.0,
                            "last_updated": None,
                            "exists": False,
                        }
                        health_score -= 10
                        issues.append(f"Table '{table}' does not exist")
                        continue

                    try:
                        count_row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
                        row_count = count_row[0] if count_row else 0

                        # Detect NULL-heavy columns (>50% nulls = warning)
                        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]  # noqa: S608
                        nulls_pct = 0.0
                        if row_count > 0 and cols:
                            null_fractions = []
                            for col in cols:
                                try:
                                    null_count_row = conn.execute(
                                        f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL"  # noqa: S608
                                    ).fetchone()
                                    null_count = null_count_row[0] if null_count_row else 0
                                    null_fractions.append(null_count / row_count)
                                except Exception:
                                    logger.debug("[VECTOR] suppressed exception", exc_info=True)
                            if null_fractions:
                                nulls_pct = round(sum(null_fractions) / len(null_fractions) * 100, 1)
                            if nulls_pct > 50:
                                health_score -= 5
                                issues.append(f"Table '{table}' has {nulls_pct}% NULL values (high)")

                        # Last updated
                        last_updated = None
                        ts_cols = [c for c in cols if "timestamp" in c.lower() or "updated" in c.lower()]
                        if ts_cols and row_count > 0:
                            try:
                                lu_row = conn.execute(
                                    f"SELECT MAX({ts_cols[0]}) FROM {table}"  # noqa: S608
                                ).fetchone()
                                last_updated = lu_row[0] if lu_row else None
                            except Exception:
                                logger.debug("[VECTOR] suppressed exception", exc_info=True)

                        table_stats[table] = {
                            "rows": row_count,
                            "nulls_pct": nulls_pct,
                            "last_updated": last_updated,
                            "exists": True,
                            "columns": len(cols),
                        }

                        if row_count == 0 and table in self.BRONZE_TABLES:
                            health_score -= 5
                            issues.append(f"Bronze table '{table}' is empty")

                    except Exception as e:
                        table_stats[table] = {"rows": -1, "nulls_pct": 0.0, "last_updated": None, "error": str(e)}
                        health_score -= 5

            finally:
                conn.close()

        health_score = max(0, min(100, health_score))
        logger.info(f"[VECTOR][data_engineer] pipeline health: score={health_score} tables={len(table_stats)}")
        return {
            "db_exists": True,
            "db_path": str(self.VECTOR_DB_PATH),
            "tables": table_stats,
            "health_score": health_score,
            "wal_mode": wal_mode,
            "issues": issues,
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def run_bronze_to_silver(self, table: str, transformations: list[str]) -> dict:
        """
        Applies string transformations to Bronze table data and writes to Silver.
        Supported transformations: "strip_whitespace", "deduplicate", "normalize_timestamps".
        Returns {processed, errors, duration_ms}.
        """
        start_ms = time.time() * 1000
        errors: list[str] = []
        processed = 0

        if table not in self.BRONZE_TABLES:
            return {
                "error": f"'{table}' is not a Bronze table. Bronze tables: {self.BRONZE_TABLES}",
                "processed": 0,
                "errors": [],
                "duration_ms": 0,
            }

        conn = self._open_db()
        if conn is None:
            return {"error": "DB unavailable", "processed": 0, "errors": [], "duration_ms": 0}

        with self._db_lock:
            try:
                cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]  # noqa: S608
                text_cols = [
                    c for c in cols
                    if c.lower() not in ("id", "reward", "sample_count", "confidence",
                                         "is_training_data", "avg_reward")
                ]

                rows = conn.execute(f"SELECT rowid, * FROM {table} LIMIT 10000").fetchall()  # noqa: S608
                conn.close()
                conn = None

            except Exception as e:
                errors.append(str(e))
                logger.error(f"[VECTOR][data_engineer] bronze_to_silver error: {e}")
                if conn:
                    conn.close()
                conn = None
                rows = []
                cols = []
                text_cols = []

        result_rows: list[dict] = []
        seen_contents: set[str] = set()

        for row in rows:
            row_dict = dict(zip(["rowid"] + cols, row))
            skip = False

            for col in text_cols:
                val = row_dict.get(col)
                if val is None or not isinstance(val, str):
                    continue

                if "strip_whitespace" in transformations:
                    val = val.strip()

                if "normalize_timestamps" in transformations:
                    import re as _re
                    ts_match = _re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", val)
                    if ts_match:
                        val = ts_match.group(1) + "Z"

                row_dict[col] = val

            if "deduplicate" in transformations:
                content_key = row_dict.get("content", str(row_dict))
                if content_key in seen_contents:
                    skip = True
                else:
                    seen_contents.add(content_key)

            if not skip:
                result_rows.append(row_dict)
                processed += 1

        if not errors:
            logger.info(
                f"[VECTOR][data_engineer] bronze→silver '{table}': "
                f"input={len(rows)} output={processed} "
                f"transformations={transformations}"
            )

        duration_ms = round(time.time() * 1000 - start_ms, 1)
        return {
            "table": table,
            "transformations": transformations,
            "processed": processed,
            "errors": errors,
            "duration_ms": duration_ms,
        }

    def generate_data_contract(self, table: str) -> dict:
        """
        Reads table schema from SQLite PRAGMA, generates a data contract.
        Returns {columns, types, nullable, constraints, example_queries}.
        """
        conn = self._open_db()
        if conn is None:
            return {
                "table": table,
                "error": "DB unavailable — returning known schema",
                "columns": [],
                "example_queries": [],
            }

        with self._db_lock:
            try:
                pragma_rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608
                if not pragma_rows:
                    conn.close()
                    return {"table": table, "error": f"Table '{table}' not found in DB", "columns": []}

                columns: list[dict] = []
                for row in pragma_rows:
                    columns.append({
                        "name": row[1],
                        "type": row[2] or "TEXT",
                        "nullable": row[3] == 0,
                        "default": row[4],
                        "primary_key": row[5] == 1,
                    })

                conn.close()
            except Exception as e:
                logger.error(f"[VECTOR][data_engineer] generate_contract error: {e}")
                if conn:
                    conn.close()
                return {"table": table, "error": str(e), "columns": []}

        example_queries = [
            f"SELECT * FROM {table} LIMIT 10;",
            f"SELECT COUNT(*) FROM {table};",
        ]
        pk_cols = [c["name"] for c in columns if c["primary_key"]]
        if pk_cols:
            example_queries.append(f"SELECT * FROM {table} WHERE {pk_cols[0]} = '<value>';")

        ts_cols = [c["name"] for c in columns if "timestamp" in c["name"].lower() or "updated" in c["name"].lower()]
        if ts_cols:
            example_queries.append(
                f"SELECT * FROM {table} WHERE {ts_cols[0]} >= datetime('now','-7 days') ORDER BY {ts_cols[0]} DESC;"
            )

        logger.info(f"[VECTOR][data_engineer] contract generated for '{table}': {len(columns)} columns")
        return {
            "table": table,
            "columns": columns,
            "primary_keys": pk_cols,
            "nullable_columns": [c["name"] for c in columns if c["nullable"]],
            "example_queries": example_queries,
            "contract_version": "1.0",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def profile_dataset(self, table: str, limit: int = 1000) -> dict:
        """
        Statistical profile: row count, null%, unique%, min/max/avg for numerics,
        top-5 values for text columns.
        Returns a structured profile dict.
        """
        conn = self._open_db()
        if conn is None:
            return {"table": table, "error": "DB unavailable", "profile": {}}

        with self._db_lock:
            try:
                total_rows_row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
                total_rows = total_rows_row[0] if total_rows_row else 0

                pragma_rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608
                cols = [(row[1], row[2] or "TEXT") for row in pragma_rows]

                if total_rows == 0:
                    conn.close()
                    return {
                        "table": table,
                        "total_rows": 0,
                        "sampled_rows": 0,
                        "profile": {},
                        "note": "Table is empty",
                    }

                rows = conn.execute(f"SELECT * FROM {table} LIMIT {limit}").fetchall()  # noqa: S608
                conn.close()
                sampled = len(rows)

                profile: dict[str, dict] = {}
                for i, (col_name, col_type) in enumerate(cols):
                    col_values = [row[i] for row in rows]
                    non_null = [v for v in col_values if v is not None]
                    null_count = sampled - len(non_null)
                    null_pct = round(null_count / sampled * 100, 1) if sampled > 0 else 0.0
                    unique_count = len(set(str(v) for v in non_null))
                    unique_pct = round(unique_count / sampled * 100, 1) if sampled > 0 else 0.0

                    col_profile: dict = {
                        "null_pct": null_pct,
                        "unique_pct": unique_pct,
                        "unique_count": unique_count,
                    }

                    is_numeric = any(t in col_type.upper() for t in ("INT", "REAL", "FLOAT", "DOUBLE", "NUM"))
                    if is_numeric and non_null:
                        try:
                            numeric_vals = [float(v) for v in non_null]
                            col_profile["min"] = min(numeric_vals)
                            col_profile["max"] = max(numeric_vals)
                            col_profile["avg"] = round(sum(numeric_vals) / len(numeric_vals), 4)
                        except (ValueError, TypeError):
                            logger.debug("[VECTOR] suppressed exception", exc_info=True)
                    elif non_null:
                        from collections import Counter
                        top_vals = Counter(str(v) for v in non_null).most_common(5)
                        col_profile["top_values"] = [{"value": v, "count": c} for v, c in top_vals]

                    profile[col_name] = col_profile

            except Exception as e:
                logger.error(f"[VECTOR][data_engineer] profile error: {e}")
                if conn:
                    conn.close()
                return {"table": table, "error": str(e), "profile": {}}

        logger.info(f"[VECTOR][data_engineer] profiled '{table}': {total_rows} rows, {len(cols)} cols")
        return {
            "table": table,
            "total_rows": total_rows,
            "sampled_rows": sampled,
            "columns_count": len(cols),
            "profile": profile,
            "profiled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    # ── run dispatch ──────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        # 2026-09-30 (Codex third independent review, same cycle): capture
        # task_type from the UNMERGED task first -- if a nested params dict
        # happens to carry its own "type" key (a real field name for some
        # capabilities, not just VECTOR's own dispatch key), merging params
        # over task before reading task_type would let params["type"]
        # silently hijack routing. See districts/communications/email_agent.py's
        # identical fix for the full evidence.
        task_type = task.get("type", "health")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "health":
                result = self.inspect_pipeline_health()
                self._get_memory().store(
                    event_type="pipeline_health_check",
                    content=f"Pipeline health: score={result['health_score']} wal={result['wal_mode']}",
                    tags=["data_analytics", "pipeline", "health"],
                    source="data_engineer",
                )
                self.award_points(30, "health_check_done")
                return {"status": "ok", "result": result}

            elif task_type == "bronze_to_silver":
                table = task.get("table", "")
                transformations = task.get("transformations", ["strip_whitespace"])
                if not table:
                    return {"status": "error", "error": "task.table is required"}
                result = self.run_bronze_to_silver(table, transformations)
                self.award_points(40, "etl_done")
                return {"status": "ok", "result": result}

            elif task_type == "contract":
                table = task.get("table", "")
                if not table:
                    return {"status": "error", "error": "task.table is required"}
                result = self.generate_data_contract(table)
                self.award_points(20, "contract_generated")
                return {"status": "ok", "result": result}

            elif task_type == "profile":
                table = task.get("table", "")
                limit = int(task.get("limit", 1000))
                if not table:
                    return {"status": "error", "error": "task.table is required"}
                result = self.profile_dataset(table, limit)
                self.award_points(25, "profile_done")
                return {"status": "ok", "result": result}

            else:
                # Default: health check
                result = self.inspect_pipeline_health()
                self.award_points(30, "health_check_done")
                return {"status": "ok", "result": result}

        except Exception as e:
            logger.error("[VECTOR][data_engineer] {}", e)
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = DataEngineer()
        assert agent.health_points == 500

        # Verify constants
        assert "episodic_memory" in DataEngineer.BRONZE_TABLES
        assert "policy_memory" in DataEngineer.BRONZE_TABLES
        assert "reasoning_chains" in DataEngineer.BRONZE_TABLES
        assert "agent_history" in DataEngineer.BRONZE_TABLES
        assert "semantic_memory" in DataEngineer.SILVER_TABLES
        assert "skill_memory" in DataEngineer.SILVER_TABLES
        print(f"  constants: BRONZE={DataEngineer.BRONZE_TABLES} SILVER={DataEngineer.SILVER_TABLES}")

        # Test inspect_pipeline_health (works whether DB exists or not)
        health = agent.inspect_pipeline_health()
        assert "health_score" in health and "tables" in health and "wal_mode" in health
        assert 0 <= health["health_score"] <= 100
        print(f"  pipeline_health: score={health['health_score']} db_exists={health['db_exists']}")

        # Test run_bronze_to_silver (invalid table → graceful error)
        bad_result = agent.run_bronze_to_silver("nonexistent_table", ["strip_whitespace"])
        assert "error" in bad_result
        print(f"  bronze_to_silver (bad table): error returned correctly")

        # Test run_bronze_to_silver (valid Bronze table)
        result = agent.run_bronze_to_silver("episodic_memory", ["strip_whitespace", "deduplicate"])
        assert "processed" in result and "duration_ms" in result
        print(f"  bronze_to_silver: processed={result['processed']} duration={result['duration_ms']}ms")

        # Test generate_data_contract
        contract = agent.generate_data_contract("episodic_memory")
        assert "table" in contract and "columns" in contract
        print(f"  data_contract: {len(contract['columns'])} columns found")

        # Test profile_dataset
        profile = agent.profile_dataset("episodic_memory", limit=500)
        assert "table" in profile and "profile" in profile
        print(f"  profile_dataset: total_rows={profile['total_rows']} cols={profile['columns_count']}")

        # Test run dispatch
        result = await agent.run({"type": "health"})
        assert result["status"] == "ok"
        print(f"[OK] status={result['status']}")
        print("data_engineer.py OK")

    asyncio.run(_smoke())
