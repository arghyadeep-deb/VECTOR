"""Regression for vectorcode/src/server/connectors_router.py:

- The module imported loguru then immediately shadowed it with
  logging.getLogger(__name__), silently breaking every %-style call
  under loguru's {}-formatter (fixed, plus converted all placeholders).
- connect_connector()'s auto-ingest and trigger_sync()'s background sync
  both used raw threading.Thread (CLAUDE.md: asyncio only). Converted to
  asyncio.create_task(asyncio.to_thread(...)) with a strong-reference set
  (a bare create_task() result can be GC'd mid-run otherwise) and updated
  the "already running?" check from Thread.is_alive() to
  not Task.done().

This test drives the real /connectors/{id}/sync endpoints end-to-end
through FastAPI's TestClient against a fake connector + registry, proving
the async conversion still provides the same "don't double-start a sync"
and "status reflects background completion" behavior as before.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.connectors_router as connectors_router_module
from server.connectors_router import create_connectors_router


class _FakeSyncStatus:
    def __init__(self):
        self.state = "idle"
        self.items_synced = 0
        self.items_total = 0
        self.last_sync = None
        self.error = None


class _FakeConnector:
    display_name = "Fake"
    auth_type = "none"

    def __init__(self):
        self._connected = True

    def is_connected(self):
        return self._connected

    def sync_status(self):
        return _FakeSyncStatus()

    def mcp_tools(self):
        return []

    def auth_url(self):
        raise NotImplementedError


class _FakeKnowledgeStore:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None


class _FakeIngestionPipeline:
    def __init__(self, *_a, **_k):
        pass


class _FakeSyncEngine:
    def __init__(self, *_a, **_k):
        pass

    def sync(self, _connector):
        time.sleep(0.3)  # simulate background work, long enough for a
        # same-process double-trigger test to reliably observe "still running"
        return 0


def _make_client(monkeypatch):
    class _FakeRegistry:
        _entry = {"fake": _FakeConnector}

        @classmethod
        def keys(cls):
            return list(cls._entry.keys())

        @classmethod
        def contains(cls, key):
            return key in cls._entry

        @classmethod
        def get(cls, key):
            return cls._entry[key]

    monkeypatch.setattr(connectors_router_module, "_instances", {})

    import vectorcode.src.vc_core.registry as registry_module

    monkeypatch.setattr(registry_module, "ConnectorRegistry", _FakeRegistry)

    def _fake_ensure():
        pass

    monkeypatch.setattr(connectors_router_module, "_ensure_connectors_registered", _fake_ensure)

    import vectorcode.src.connectors.pipeline as pipeline_module
    import vectorcode.src.connectors.store as store_module
    import vectorcode.src.connectors.sync_engine as sync_engine_module

    monkeypatch.setattr(store_module, "KnowledgeStore", _FakeKnowledgeStore)
    monkeypatch.setattr(pipeline_module, "IngestionPipeline", _FakeIngestionPipeline)
    monkeypatch.setattr(sync_engine_module, "SyncEngine", _FakeSyncEngine)

    app = FastAPI()
    app.include_router(create_connectors_router())
    return TestClient(app)


def test_module_does_not_shadow_loguru_with_stdlib_logging():
    import inspect

    src = inspect.getsource(connectors_router_module)
    assert "logging.getLogger" not in src
    assert "%s" not in src


def test_module_tracks_background_tasks_with_strong_refs():
    import inspect

    src = inspect.getsource(connectors_router_module)
    assert "threading.Thread" not in src
    assert ".is_alive()" not in src
    assert "_background_tasks" in src


def test_trigger_sync_and_status_round_trip(monkeypatch):
    client = _make_client(monkeypatch)

    resp = client.post("/v1/connectors/fake/sync")
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"

    # Give the asyncio.to_thread background task a moment to complete.
    for _ in range(50):
        status = client.get("/v1/connectors/fake/sync").json()
        if status["state"] == "complete":
            break
        time.sleep(0.05)

    assert status["state"] == "complete"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
