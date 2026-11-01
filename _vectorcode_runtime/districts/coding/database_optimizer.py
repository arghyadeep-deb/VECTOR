"""
Database Optimizer — tunes VECTOR's SQLite, Supabase, and Turso databases.

Analyzes slow queries, missing indexes, schema drift, WAL health,
and generates optimization recommendations.
"""

import asyncio
import datetime
import time
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.db_utils import configured_db_path
from core.memory.obsidian_sync import ObsidianSync
from core.inference.vectorcode_llm import chat

class DatabaseOptimizer(AgentBase):
    """Tunes VECTOR's databases — SQLite FTS5, WAL health, index analysis."""

    def __init__(self):
        super().__init__(agent_id="db_optimizer_001", name="DatabaseOptimizer", district="coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["schema", "benchmark", "full_audit"]
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        self._root = Path(__file__).parent.parent.parent.parent
        self._db_path = configured_db_path()
        logger.info("[VECTOR][db_optimizer] initialized — db={}", self._db_path)

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self):
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    def analyze_schema(self) -> dict:
        """Inspect all tables, row counts, and index coverage."""
        if not self._db_path.exists():
            return {"error": "vector_memory.db not found"}
        try:
            # RULE 7: go through the main DB's shared SQLCipher-aware
            # connection, not a plain sqlite3.connect() -- that would either
            # fail outright (can't read an encrypted file) or silently
            # bypass encryption if it happened to still work. This is the
            # shared singleton (same pattern as districts/content/
            # blog_publisher.py, districts/memory_curator/*) -- never close
            # it, closing it would take the rest of VECTOR's memory access
            # down with it.
            from core.memory.episodic import get_db_connection
            con = get_db_connection()
            cur = con.cursor()
            tables = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            schema = {}
            for (name,) in tables:
                row_count = cur.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
                cols = cur.execute(f"PRAGMA table_info([{name}])").fetchall()
                indexes = cur.execute(f"PRAGMA index_list([{name}])").fetchall()
                schema[name] = {
                    "rows": row_count,
                    "columns": [c[1] for c in cols],
                    "indexes": [idx[1] for idx in indexes],
                }
            # WAL mode check
            wal = cur.execute("PRAGMA journal_mode").fetchone()[0]
            # sqlcipher3's driver returns PRAGMA integers as str (unlike
            # stdlib sqlite3's int) -- this surfaced only after fixing the
            # connection above to actually reach the encrypted DB; the old
            # plain sqlite3.connect() never got far enough to hit it.
            page_size = int(cur.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(cur.execute("PRAGMA page_count").fetchone()[0])
            return {
                "tables": schema,
                "wal_mode": wal,
                "db_size_mb": round(page_size * page_count / 1024 / 1024, 2),
                "table_count": len(tables),
            }
        except Exception as e:
            logger.warning("[VECTOR][db_optimizer] schema analysis failed: {}", e)
            return {"error": str(e)}

    def benchmark_queries(self) -> dict:
        """Time key VECTOR queries to detect slow ones."""
        if not self._db_path.exists():
            return {"error": "db not found"}
        benchmarks = {}
        try:
            from core.memory.episodic import get_db_connection
            con = get_db_connection()
            cur = con.cursor()
            queries = {
                "recent_events": "SELECT * FROM episodic_memory ORDER BY timestamp DESC LIMIT 50",
                "fts_search": "SELECT * FROM episodic_memory WHERE content MATCH 'VECTOR' LIMIT 10",
                "count_events": "SELECT COUNT(*) FROM episodic_memory",
                "policy_lookup": "SELECT * FROM policy_memory LIMIT 20",
            }
            for name, sql in queries.items():
                try:
                    t0 = time.perf_counter()
                    cur.execute(sql)
                    cur.fetchall()
                    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                    benchmarks[name] = {"ms": elapsed_ms, "slow": elapsed_ms > 100}
                except Exception as qe:
                    benchmarks[name] = {"error": str(qe)[:60]}
        except Exception as e:
            return {"error": str(e)}
        return benchmarks

    def check_wal_health(self) -> dict:
        """Check WAL file size and suggest checkpoint if needed."""
        wal_file = self._db_path.with_suffix(".db-wal")
        shm_file = self._db_path.with_suffix(".db-shm")
        wal_mb = wal_file.stat().st_size / 1024 / 1024 if wal_file.exists() else 0
        issues = []
        if wal_mb > 100:
            issues.append(f"WAL file is {wal_mb:.1f}MB — run PRAGMA wal_checkpoint(TRUNCATE)")
        if not shm_file.exists():
            issues.append("SHM file missing — WAL may be inactive")
        return {
            "wal_size_mb": round(wal_mb, 2),
            "issues": issues,
            "healthy": len(issues) == 0,
        }

    async def generate_recommendations(self, schema: dict, benchmarks: dict) -> str:
        """LLM generates specific optimization recommendations."""
        slow = {k: v for k, v in benchmarks.items() if isinstance(v, dict) and v.get("slow")}
        tables_info = {name: {"rows": info["rows"], "indexes": info["indexes"]}
                       for name, info in schema.get("tables", {}).items()}
        prompt = (
            f"VECTOR AI system uses SQLite with these tables:\n{tables_info}\n\n"
            f"Slow queries detected: {slow}\n\n"
            f"Provide 3-5 specific SQLite optimization recommendations:\n"
            f"- Missing index suggestions (with CREATE INDEX SQL)\n"
            f"- FTS5 configuration improvements\n"
            f"- WAL checkpoint strategy\n"
            f"- Schema normalization if needed\n"
            f"Be concrete and include actual SQL statements."
        )
        try:
            return chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=30.0)
        except Exception as e:
            return f"Recommendation generation failed: {e}"

    async def answer_question(self, query: str) -> str:
        """Answer a free-text database/optimization question directly (no
        schema scan, no Obsidian write). Used by run() when a real chat
        query is present but no schema/benchmark/audit was explicitly
        requested — 2026-07-29 sweep, same bug class as #1/#14/#15/#21/#33
        (wrong hardcoded default action instead of the real question)."""
        try:
            sys_prompt = (
                "You are DatabaseOptimizer, VECTOR's SQLite/Supabase/Turso tuning "
                "agent. You analyze schemas, benchmark queries, check WAL health, "
                "and generate optimization recommendations. Answer the user's "
                "question directly and concisely."
            )
            answer = chat(model=self._model, messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": query},
            ], timeout=30.0)
            self.award_points(10, "db_qa_answered")
            return answer or "I don't have enough information to answer that right now."
        except Exception as e:
            logger.error("[VECTOR][db_optimizer] answer_question error: {}", e)
            return f"Error answering question: {e}"

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) if isinstance(task.get("params"), dict) else {}
        try:
            query = (
                p.get("query") or p.get("content") or task.get("query")
                or task.get("prompt") or ""
            )
            # 2026-07-29: default used to be "full_audit" for ANY unmatched
            # task_type — including real free-text chat questions with no
            # audit intent at all. full_audit is read-only but also writes a
            # report note to Obsidian on every call, which is the wrong
            # side effect for a stray chat message. Only audit when
            # explicitly requested or when there's no real question to answer.
            if task_type not in ("schema", "benchmark", "full_audit") and query.strip():
                answer = await self.answer_question(query)
                return {"status": "ok", "response": answer, "agent": self.name}

            if task_type == "schema":
                result = self.analyze_schema()
                self.award_points(20, "schema_analyzed")
                return {"status": "ok", "schema": result}

            elif task_type == "benchmark":
                result = self.benchmark_queries()
                slow_count = sum(1 for v in result.values() if isinstance(v, dict) and v.get("slow"))
                self.award_points(25, "queries_benchmarked")
                return {"status": "ok", "benchmarks": result, "slow_queries": slow_count}

            else:  # full_audit
                schema = self.analyze_schema()
                benchmarks = self.benchmark_queries()
                wal = self.check_wal_health()
                recs = await self.generate_recommendations(schema, benchmarks)

                # Store report in memory
                slow_count = sum(1 for v in benchmarks.values() if isinstance(v, dict) and v.get("slow"))
                self._get_memory().store(
                    event_type="db_optimization_audit",
                    content=f"DB audit: {schema.get('table_count',0)} tables, {slow_count} slow queries, WAL={wal['wal_size_mb']}MB",
                    tags=["coding", "database", "optimization"],
                    context={"slow_queries": slow_count, "wal_mb": wal["wal_size_mb"], "db_mb": schema.get("db_size_mb", 0)},
                    source="database_optimizer",
                )

                # Write to Obsidian
                try:
                    obs = self._get_obsidian()
                    content = (
                        f"# DB Optimization Report — {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
                        f"## Schema\n- Tables: {schema.get('table_count',0)}\n"
                        f"- DB size: {schema.get('db_size_mb',0)}MB\n"
                        f"- WAL: {wal['wal_size_mb']}MB ({'⚠️ large' if not wal['healthy'] else '✅ healthy'})\n\n"
                        f"## Slow Queries ({slow_count})\n"
                        + "\n".join(f"- {k}: {v.get('ms')}ms" for k, v in benchmarks.items() if isinstance(v, dict) and v.get("slow"))
                        + f"\n\n## Recommendations\n{recs}\n"
                    )
                    obs.write_note("Projects", "DB Optimization Report", content)
                except Exception as oe:
                    logger.debug("[VECTOR][db_optimizer] obsidian write failed: {}", oe)

                if slow_count == 0 and wal["healthy"]:
                    self.award_points(50, "db_healthy")
                else:
                    self.award_points(30, "db_audit_complete_issues_found")

                return {
                    "status": "ok",
                    "schema": schema,
                    "benchmarks": benchmarks,
                    "wal": wal,
                    "recommendations": recs[:500],
                    "slow_queries": slow_count,
                }

        except Exception as e:
            logger.error("[VECTOR][db_optimizer] {}", e)
            self.deduct_points(30, "db_audit_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = DatabaseOptimizer()
        schema = agent.analyze_schema()
        print(f"[OK] schema: {schema.get('table_count',0)} tables, {schema.get('db_size_mb',0)}MB")
        bench = agent.benchmark_queries()
        print(f"[OK] benchmarks: {list(bench.keys())}")
        wal = agent.check_wal_health()
        print(f"[OK] wal_health: {wal}")
        result = await agent.run({"type": "schema"})
        print(f"[OK] run: status={result['status']}")
        print("database_optimizer.py OK")

    asyncio.run(_smoke())
