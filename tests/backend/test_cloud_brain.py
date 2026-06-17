"""Phase 3 — Fly cloud brain reads the cloud DB (Supabase) so remote endpoints
return real data instead of erroring on a missing local file."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def _load_brain_module(name: str):
    cloud_dir = ROOT / "cloud" / "brain_server"
    sys.path.insert(0, str(cloud_dir))
    try:
        spec = importlib.util.spec_from_file_location(name, cloud_dir / "main.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        try:
            sys.path.remove(str(cloud_dir))
        except ValueError:
            pass


def test_supabase_reader_graceful_without_creds(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    mod = _load_brain_module("brain_supabase_nocreds")
    assert mod._supabase_creds() == (None, None)
    assert asyncio.run(mod._supabase_episodic(limit=5)) is None  # → endpoints fall back


def test_memory_endpoint_reports_source(monkeypatch):
    """Without Supabase creds, /memory/recent falls back to local and tags the source."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("VECTOR_API_KEY", raising=False)
    monkeypatch.setenv("VECTOR_ENV", "development")
    mod = _load_brain_module("brain_mem_source")
    client = TestClient(mod.app)
    r = client.get("/memory/recent?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body and "source" in body  # source: supabase|local


def test_agents_endpoint_has_source(monkeypatch):
    monkeypatch.delenv("VECTOR_API_KEY", raising=False)
    monkeypatch.setenv("VECTOR_ENV", "development")
    mod = _load_brain_module("brain_agents_source")
    client = TestClient(mod.app)
    r = client.get("/agents")
    assert r.status_code == 200
    assert "source" in r.json()


def test_status_still_public(monkeypatch):
    monkeypatch.setenv("VECTOR_ENV", "development")
    mod = _load_brain_module("brain_status_pub")
    client = TestClient(mod.app)
    assert client.get("/status").status_code == 200
