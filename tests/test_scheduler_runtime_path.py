"""Regression tests for scheduler runtime-data isolation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def test_scheduler_jobs_router_uses_active_runtime_data_root(tmp_path, monkeypatch):
    data_root = tmp_path / "vector-data"
    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(data_root))

    observed = {}

    class Store:
        def __init__(self, db_path):
            observed["path"] = Path(db_path)

        def list_tasks(self, status=None):
            return []

    import core.scheduler.store as store_module
    monkeypatch.setattr(store_module, "SchedulerStore", Store)

    from core.api.routers.scheduler import scheduler_jobs

    result = asyncio.run(scheduler_jobs())

    assert result.total == 0
    assert observed["path"] == (data_root / "scheduler.db").resolve()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
