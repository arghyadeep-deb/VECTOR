"""Tests for the canonical agent/district inventory."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_inventory_matches_loaded_source_of_truth():
    from core.city.declarative_manifest import ManifestLoader

    inventory = ManifestLoader().inventory()

    assert inventory["agent_count"] == 274
    assert inventory["district_count"] == 41
    assert inventory["empty_districts"] == []
    assert inventory["duplicate_agent_names"] == []


def test_readiness_report_contains_manifest_inventory_evidence():
    from core.runtime.readiness_check import run_readiness_check

    report = run_readiness_check()
    check = next(item for item in report["checks"] if item["name"] == "agent_manifest")

    assert check["status"] == "ok"
    assert check["evidence"]["agent_count"] == 274
    assert check["evidence"]["district_count"] == 41


def test_manifest_readiness_does_not_import_optional_agent_runtime_backends():
    env = dict(os.environ)
    env.update(
        {
            "VECTOR_API_RUN_LOOP": "0",
            "VECTOR_SIDECARS": "0",
            "VECTOR_DISABLE_FILE_LOGGING": "1",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from core.runtime.readiness_check import _check_agent_manifest; print(_check_agent_manifest().to_dict())",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "faiss_backend" not in result.stderr
    assert "colbert_backend" not in result.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
