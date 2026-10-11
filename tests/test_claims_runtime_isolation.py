"""Regression tests for claims storage isolation."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_default_claim_repository_uses_runtime_data_root(tmp_path, monkeypatch):
    data_root = tmp_path / "vector-data"
    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(data_root))
    monkeypatch.delenv("VECTOR_DATA_DIR", raising=False)

    from vectorcode.src.claims import ClaimRepository

    repository = ClaimRepository()

    assert repository.db_path == (data_root / "claims.db").resolve()
    assert repository.db_path.exists()
    assert repository.db_path != (Path.home() / ".vector" / "claims.db").resolve()


def test_swarm_assignment_does_not_read_stale_user_claims(tmp_path, monkeypatch):
    data_root = tmp_path / "vector-data"
    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(data_root))
    monkeypatch.delenv("VECTOR_DATA_DIR", raising=False)

    from types import SimpleNamespace

    from vectorcode.src.swarm import AgentState

    state = AgentState(SimpleNamespace(id="isolated-agent", name="Isolated Agent", hp=500))

    assert state.start_task("write isolated tests") is True
    assert state.status == "busy"
    assert state.current_task == "write isolated tests"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
