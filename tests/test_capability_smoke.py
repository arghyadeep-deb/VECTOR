"""Tests for scripts/capability_smoke.py — specifically the temp-DB isolation
from Task 0.5c (plans/wire-absorbed-repos-autonomy.md). Phase 0 found that
--live capability probes deterministically fail when a real VECTOR process
already holds the shared SQLCipher DB file; this locks in the fix.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import capability_smoke  # noqa: E402


def test_use_isolated_db_sets_env_var(monkeypatch):
    monkeypatch.delenv("VECTOR_DB_PATH", raising=False)
    capability_smoke._use_isolated_db()
    assert "VECTOR_DB_PATH" in __import__("os").environ


def test_use_isolated_db_points_outside_repo(monkeypatch):
    monkeypatch.delenv("VECTOR_DB_PATH", raising=False)
    capability_smoke._use_isolated_db()
    import os
    path = Path(os.environ["VECTOR_DB_PATH"])
    assert ROOT not in path.parents, "isolated DB must not live inside the real repo's DB location"


def test_use_isolated_db_each_call_gets_a_fresh_path(monkeypatch):
    monkeypatch.delenv("VECTOR_DB_PATH", raising=False)
    import os
    capability_smoke._use_isolated_db()
    first = os.environ["VECTOR_DB_PATH"]
    capability_smoke._use_isolated_db()
    second = os.environ["VECTOR_DB_PATH"]
    assert first != second


def test_configured_db_path_honors_the_override(monkeypatch, tmp_path):
    """The actual seam capability_smoke.py relies on — confirms episodic.py's
    DB-path resolution genuinely respects VECTOR_DB_PATH end to end."""
    target = tmp_path / "isolated.db"
    monkeypatch.setenv("VECTOR_DB_PATH", str(target))
    from core.memory.db_utils import configured_db_path
    assert configured_db_path() == target


if __name__ == "__main__":
    print("✅ test_capability_smoke.py module loads")
