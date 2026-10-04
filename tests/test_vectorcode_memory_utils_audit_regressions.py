"""Regression tests for audited memory and usage persistence bugs."""

from __future__ import annotations

from pathlib import Path

import pytest

from vectorcode.src.memory import swarm_db
from vectorcode.src.utils import usage_pricing


def test_swarm_id_cannot_escape_database_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(swarm_db, "_DB_ROOT", tmp_path)
    with pytest.raises(ValueError):
        swarm_db.SwarmDatabase("../../outside")
    assert list(tmp_path.rglob("*.db")) == []


def test_bounded_usage_summary_includes_new_record(tmp_path: Path, monkeypatch) -> None:
    usage_file = tmp_path / "usage.json"
    monkeypatch.setattr(usage_pricing, "_USAGE_FILE", usage_file)
    usage_pricing.record_usage("model", 10, 5, 0.25)
    assert usage_pricing.get_usage_summary(days=1) == {
        "total_cost": 0.25,
        "total_tokens": 15,
        "session_count": 1,
    }


def test_corrupt_usage_file_is_preserved(tmp_path: Path, monkeypatch) -> None:
    usage_file = tmp_path / "usage.json"
    corrupt = b"{not-json"
    usage_file.write_bytes(corrupt)
    monkeypatch.setattr(usage_pricing, "_USAGE_FILE", usage_file)
    with pytest.raises(ValueError):
        usage_pricing.record_usage("model", 1, 1, 0.0)
    assert usage_file.read_bytes() == corrupt


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
