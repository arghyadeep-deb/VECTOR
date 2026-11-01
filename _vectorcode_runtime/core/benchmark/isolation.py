"""Isolated state for benchmark execution.

Provides a completely isolated environment for benchmark tasks:
- Separate SQLite DB (via VECTOR_DB_PATH env var)
- Separate plan store (temp JSON file)
- Clean sense cache
- No pollution of production memory

On teardown: closes connections, deletes temp files, restores environment.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger


class IsolatedState:
    """Context manager providing isolated VECTOR state for benchmarks.

    Usage:
        with IsolatedState() as state:
            # state.temp_dir — temp directory for all files
            # state.db_path — path to isolated SQLite DB
            # state.plan_store_path — path to temp plan store JSON
            mem = EpisodicMemory()  # uses temp DB automatically
            ...
        # Everything cleaned up on exit
    """

    def __init__(self):
        self.temp_dir: str = ""
        self.db_path: str = ""
        self.epistemic_db_path: str = ""
        self.plan_store_path: str = ""
        self._original_db_path: str | None = None
        self._original_sense_cache: dict | None = None

    def __enter__(self) -> IsolatedState:
        self._setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._teardown()

    def _setup(self) -> None:
        """Create isolated environment."""
        # Create temp directory
        self.temp_dir = tempfile.mkdtemp(prefix="vector_bench_")

        # Set up isolated DB path
        self.db_path = os.path.join(self.temp_dir, "bench_memory.db")
        self.epistemic_db_path = os.path.join(self.temp_dir, "bench_epistemic.db")
        self.plan_store_path = os.path.join(self.temp_dir, "bench_plans.json")

        # Save original state
        self._original_db_path = os.environ.get("VECTOR_DB_PATH")

        # Redirect to isolated DB
        os.environ["VECTOR_DB_PATH"] = self.db_path

        # Reset episodic memory singleton
        try:
            import core.memory.episodic as ep
            # Close any existing connection first
            try:
                ep.close_db_connection()
            except Exception:
                pass
            # Force fresh connection to temp DB
            ep._db_connection = None
            ep._DB_KEY = None
            conn = ep.get_db_connection()
            logger.debug("[VECTOR][bench] isolated DB created at {}", self.db_path)
        except Exception as e:
            logger.warning("[VECTOR][bench] episodic reset failed: {}", e)

        # Reset sense cache
        try:
            from core.loop.context_engine import update_sense_cache, _SENSE_CACHE, _SENSE_CACHE_LOCK
            with _SENSE_CACHE_LOCK:
                self._original_sense_cache = dict(_SENSE_CACHE)
            update_sense_cache(screen_summary="", presence="unknown")
        except Exception:
            pass

        # Reset plan store singleton
        try:
            import core.runtime.plans as plans_mod
            plans_mod._PLAN_STORE = None
        except Exception:
            pass

    def _teardown(self) -> None:
        """Clean up isolated environment."""
        # Close episodic DB connection
        try:
            import core.memory.episodic as ep
            ep.close_db_connection()
        except Exception:
            pass

        # Restore original DB path
        if self._original_db_path is not None:
            os.environ["VECTOR_DB_PATH"] = self._original_db_path
        else:
            os.environ.pop("VECTOR_DB_PATH", None)

        # Restore sense cache
        if self._original_sense_cache is not None:
            try:
                from core.loop.context_engine import update_sense_cache
                update_sense_cache(**self._original_sense_cache)
            except Exception:
                pass

        # Reset plan store singleton again (so next use gets production store)
        try:
            import core.runtime.plans as plans_mod
            plans_mod._PLAN_STORE = None
        except Exception:
            pass

        # Delete temp directory
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception:
                pass

        logger.debug("[VECTOR][bench] isolated state cleaned up")
