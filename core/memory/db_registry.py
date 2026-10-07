"""
core/memory/db_registry.py
Central registry of every SQLite database in VECTOR.

Problem: SQLite files were created ad-hoc across districts with no
tracking, no schema versioning, and no migration path.

Solution: register every DB here with owner, path template, schema version,
and purpose. Use get_district_db() as a factory for district connections so
the registry stays current automatically.

Adding a new DB:
    REGISTRY["my_district.feature"] = DBEntry(
        path_template="data/{name}.db",
        schema_version=1,
        owner="districts/my_district/feature.py",
        purpose="one-line description",
    )
"""
from __future__ import annotations

from core.memory.db_utils import apply_pragmas, configured_db_path
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

# path_template value used by the three registry entries that alias the
# main SQLCipher-encrypted memory DB (core.episodic / core.collections /
# core.causal_graph) rather than a genuinely separate district file.
_MAIN_DB_TEMPLATE = "vector_memory.db"


@dataclass
class DBEntry:
    path_template: str        # relative to project root; {name} → entry key
    schema_version: int
    owner: str                # file responsible for CREATE TABLE
    purpose: str
    migrations: list[str] = field(default_factory=list)  # SQL DDL strings in order


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict[str, DBEntry] = {
    # Core memory (all consolidated in vector_memory.db via get_db_connection())
    "core.episodic": DBEntry(
        path_template="vector_memory.db",
        schema_version=5,
        owner="core/memory/episodic.py",
        purpose="Episodic memory, semantic facts, policy, reasoning chains, agent history",
    ),
    "core.collections": DBEntry(
        path_template="vector_memory.db",
        schema_version=1,
        owner="core/collections/store.py",
        purpose="Dynamic PocketBase-style collections (_collections + col_* tables)",
    ),
    "core.causal_graph": DBEntry(
        path_template="vector_memory.db",
        schema_version=1,
        owner="core/memory/causal_graph.py",
        purpose="Causal nodes and edges for Gap 6 reasoning",
    ),

    # District-specific DBs (separate files, own connection)
    "districts.health.metrics": DBEntry(
        path_template="data/health/{name}.db",
        schema_version=1,
        owner="districts/health/metrics_store.py",
        purpose="Wearable + sensor metrics time-series",
    ),
    "districts.content.video_pipeline": DBEntry(
        path_template="data/{name}.db",
        schema_version=1,
        owner="districts/content/video_pipeline.py",
        purpose="Video generation job tracking",
    ),
    "districts.content.post_job": DBEntry(
        path_template="data/{name}.db",
        schema_version=1,
        owner="districts/content/post_job.py",
        purpose="Blog/social post publish state machine",
    ),
    "districts.coding.database_optimizer": DBEntry(
        path_template="data/{name}.db",
        schema_version=1,
        owner="districts/coding/database_optimizer.py",
        purpose="SQLite schema analysis cache",
    ),
    "districts.emergency.log": DBEntry(
        path_template="data/emergency_log.db",
        schema_version=1,
        owner="districts/emergency/log.py",
        purpose="Emergency event log",
    ),
    "districts.data_analytics": DBEntry(
        path_template="data/analytics.db",
        schema_version=1,
        owner="districts/data_analytics/__init__.py",
        purpose="ETL pipeline metadata and analytics results",
    ),
    "core.telemetry": DBEntry(
        path_template="data/telemetry.db",
        schema_version=1,
        owner="core/inference/ollama_safe.py",
        purpose="Inference telemetry and energy tracking",
    ),

    # Data directory standalone DBs
    "data.contacts": DBEntry(
        path_template="data/contacts.db",
        schema_version=1,
        owner="districts/relationships/contact_manager.py",
        purpose="Contact graph and interaction history",
    ),
    "data.learning_courses": DBEntry(
        path_template="data/learning_courses.db",
        schema_version=1,
        owner="districts/learning/course_tracker.py",
        purpose="Course progress tracking",
    ),
    "data.suggestion_queue": DBEntry(
        path_template="data/suggestion_queue.db",
        schema_version=1,
        owner="core/brain/hypothesis_engine.py",
        purpose="Pending proactive suggestions queue",
    ),
    "data.counterfactual": DBEntry(
        path_template="data/counterfactual.db",
        schema_version=0,
        owner="core/brain/counterfactual.py",
        purpose="Counterfactual reasoning store (Year 2 — deferred)",
    ),
    "data.epistemic": DBEntry(
        path_template="data/epistemic.db",
        schema_version=0,
        owner="core/brain/epistemic_tracker.py",
        purpose="Belief confidence tracking (Year 2 — deferred)",
    ),
    "data.meta_cognition": DBEntry(
        path_template="data/meta_cognition.db",
        schema_version=0,
        owner="core/brain/meta_cognition.py",
        purpose="Bias detection store (Year 2 — deferred)",
    ),
    "data.person_models": DBEntry(
        path_template="data/person_models.db",
        schema_version=0,
        owner="core/brain/person_model.py",
        purpose="Theory of mind per person (Year 2 — deferred)",
    ),
}


# ── Factory ───────────────────────────────────────────────────────────────────

def _project_root() -> Path:
    return Path(__file__).parent.parent.parent


def _row_class(conn) -> type:
    """sqlite3.Row rejects sqlcipher cursors — pick the driver's own Row.

    Same trap documented in districts/emergency/log.py:_row_class() and
    core/memory/shared_facts.py:_row_class(): sqlite3.Row raises
    "Row() argument 1 must be sqlite3.Cursor, not sqlcipher3.dbapi2.Cursor"
    when handed a cursor from the sqlcipher3/pysqlcipher3 driver. The Row
    class must always come from the same driver module as the connection.
    """
    mod = type(conn).__module__
    if mod.startswith("sqlcipher3"):
        from sqlcipher3 import dbapi2
        return dbapi2.Row
    if mod.startswith("pysqlcipher3"):
        from pysqlcipher3 import dbapi2
        return dbapi2.Row
    return sqlite3.Row


def get_district_db(key: str, check_same_thread: bool = False) -> sqlite3.Connection:
    """Open a registered district DB by registry key.

    Usage:
        conn = get_district_db("districts.health.metrics")
        conn.execute("SELECT ...")

    "core.episodic" / "core.collections" / "core.causal_graph" all point
    their path_template at "vector_memory.db" — that is the main
    SQLCipher-encrypted memory DB (already owned by core.memory.episodic),
    not a genuinely separate district file. Opening it with plain
    sqlite3.connect() (the old behavior here) raises
    "file is not a database" the moment SQLCipher is active — this was a
    latent landmine (2026-08-05 memory-persistence audit, Finding #4):
    unreachable in production because nothing called get_district_db() with
    those keys, but it would have hit the exact same failure mode already
    fixed for core/memory/shared_facts.py and
    districts/data_analytics/data_engineer.py (see those files' 2026-08-05/06
    fix comments) the moment a future caller followed this module's own
    documented usage pattern with one of the three core.* keys.

    Every OTHER registry entry (data/{name}.db, data/emergency_log.db,
    data/health/{name}.db, ...) is a genuinely separate, unencrypted file —
    those keep opening with plain sqlite3.connect() exactly as before.
    """
    entry = REGISTRY.get(key)
    if entry is None:
        raise KeyError(f"DB '{key}' not in registry. Register it in core/memory/db_registry.py first.")

    if key == "data.contacts":
        rel_path = entry.path_template
        abs_path = _project_root() / rel_path
        from core.relationships.schema import get_connection as get_contacts_connection

        conn = get_contacts_connection(abs_path)
    elif entry.path_template == _MAIN_DB_TEMPLATE:
        # Alias of the main encrypted DB — resolve through the same source
        # of truth core.memory.episodic uses (configured_db_path(), which
        # honors VECTOR_DB_PATH for tests/repair) rather than re-deriving
        # "<project_root>/vector_memory.db" independently, so this never
        # drifts from the file get_db_connection() actually opens.
        abs_path = configured_db_path()
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        rel_path = _MAIN_DB_TEMPLATE

        conn = None
        try:
            from core.memory import episodic
            if getattr(episodic, "_USE_SQLCIPHER", False):
                conn = episodic._open_sqlcipher_connection(str(abs_path))
        except Exception as e:
            logger.warning(
                "[VECTOR][db_registry] SQLCipher open failed for '{}', falling back to plain sqlite: {}",
                key, e,
            )
            conn = None
        if conn is None:
            conn = sqlite3.connect(str(abs_path), check_same_thread=check_same_thread)
            apply_pragmas(conn, foreign_keys=True)
        conn.row_factory = _row_class(conn)
    else:
        name = key.split(".")[-1]
        rel_path = entry.path_template.replace("{name}", name)
        abs_path = _project_root() / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(abs_path), check_same_thread=check_same_thread)
        apply_pragmas(conn, foreign_keys=True)
        conn.row_factory = _row_class(conn)

    logger.debug("[VECTOR][db_registry] opened '{}' (v{}) at {}", key, entry.schema_version, rel_path)
    return conn


def list_all() -> list[dict]:
    """Return all registered DBs with their status (exists / missing / deferred)."""
    root = _project_root()
    result = []
    for key, entry in REGISTRY.items():
        name = key.split(".")[-1]
        rel_path = entry.path_template.replace("{name}", name)
        abs_path = root / rel_path
        status = "deferred" if entry.schema_version == 0 else ("exists" if abs_path.exists() else "missing")
        result.append({
            "key": key,
            "path": rel_path,
            "schema_version": entry.schema_version,
            "owner": entry.owner,
            "purpose": entry.purpose,
            "status": status,
        })
    return result


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    dbs = list_all()
    print(f"VECTOR DB Registry — {len(dbs)} entries\n")
    for db in dbs:
        flag = "OK" if db["status"] == "exists" else ("--" if db["status"] == "deferred" else "?")
        print(f"  [{flag}] {db['key']:45s} v{db['schema_version']}  {db['status']}")
    print()
    print("OK db_registry.py")
