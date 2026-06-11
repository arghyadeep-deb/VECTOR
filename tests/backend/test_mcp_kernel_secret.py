"""Task 03 — MCP kernel secret must be stable in production.

The stdio kernel falls back to an ephemeral per-process secret in dev; in
production a stable MCP_KERNEL_SECRET is required (fail closed), and strict
doctor reports it.
"""
from __future__ import annotations

import importlib

import pytest


# ── doctor production check ───────────────────────────────────────────────────

def test_doctor_requires_mcp_kernel_secret_in_production(monkeypatch):
    from core.runtime.doctor import run_dependency_doctor

    monkeypatch.setenv("VECTOR_ENV", "production")
    monkeypatch.delenv("MCP_KERNEL_SECRET", raising=False)
    payload = run_dependency_doctor(include_optional=False).to_dict()
    checks = {c["name"]: c for c in payload["checks"]}

    assert "env:MCP_KERNEL_SECRET" in checks
    assert checks["env:MCP_KERNEL_SECRET"]["required"] is True
    assert checks["env:MCP_KERNEL_SECRET"]["status"] == "fail"


def test_doctor_accepts_strong_mcp_kernel_secret(monkeypatch):
    from core.runtime.doctor import run_dependency_doctor

    monkeypatch.setenv("VECTOR_ENV", "production")
    monkeypatch.setenv("MCP_KERNEL_SECRET", "x" * 48)
    payload = run_dependency_doctor(include_optional=False).to_dict()
    checks = {c["name"]: c for c in payload["checks"]}

    assert checks["env:MCP_KERNEL_SECRET"]["status"] == "ok"


def test_doctor_mcp_secret_optional_in_dev(monkeypatch):
    from core.runtime.doctor import run_dependency_doctor

    monkeypatch.delenv("VECTOR_ENV", raising=False)
    monkeypatch.delenv("MCP_KERNEL_SECRET", raising=False)
    payload = run_dependency_doctor(include_optional=False).to_dict()
    checks = {c["name"]: c for c in payload["checks"]}

    # present but not a hard failure in development
    assert checks["env:MCP_KERNEL_SECRET"]["required"] is False


# ── stdio kernel fail-closed ──────────────────────────────────────────────────

def _reload_stdio(monkeypatch, env: str | None, secret: str | None):
    if env is None:
        monkeypatch.delenv("VECTOR_ENV", raising=False)
    else:
        monkeypatch.setenv("VECTOR_ENV", env)
    if secret is None:
        monkeypatch.delenv("MCP_KERNEL_SECRET", raising=False)
    else:
        monkeypatch.setenv("MCP_KERNEL_SECRET", secret)
    import core.mcp_server_stdio as stdio
    return importlib.reload(stdio)


def test_dev_imports_with_ephemeral_secret(monkeypatch):
    stdio = _reload_stdio(monkeypatch, env=None, secret=None)
    assert stdio.KERNEL_SECRET_EPHEMERAL is True
    # dev never fails closed
    stdio.ensure_production_secret()


def test_production_without_secret_fails_closed(monkeypatch):
    stdio = _reload_stdio(monkeypatch, env="production", secret=None)
    assert stdio.KERNEL_SECRET_EPHEMERAL is True
    with pytest.raises(RuntimeError):
        stdio.ensure_production_secret()


def test_production_with_weak_secret_fails_closed(monkeypatch):
    stdio = _reload_stdio(monkeypatch, env="production", secret="short")
    with pytest.raises(RuntimeError):
        stdio.ensure_production_secret()


def test_production_with_strong_secret_ok(monkeypatch):
    stdio = _reload_stdio(monkeypatch, env="production", secret="y" * 48)
    assert stdio.KERNEL_SECRET_EPHEMERAL is False
    stdio.ensure_production_secret()  # must not raise


def teardown_module(module):
    # leave the module in a clean default state for other tests
    import os
    import importlib
    os.environ.pop("VECTOR_ENV", None)
    os.environ.pop("MCP_KERNEL_SECRET", None)
    import core.mcp_server_stdio as stdio
    importlib.reload(stdio)
