"""Sub-project E (docs/superpowers/specs/2026-09-24-test-suite-isolation-design.md):
each pytest session runs against a fresh temp DB/data dir and refuses to run against live state.
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIVE_DATA = ROOT / "data"

_STORES = {
    "epistemic": ("core.brain.epistemic_tracker", "_DEFAULT_DB", "epistemic.db"),
    "suggestion_queue": ("core.brain.suggestion_queue", "_DEFAULT_DB", "suggestion_queue.db"),
    "inference_observability": ("core.metering.inference_observability", "_DB_PATH", "telemetry.db"),
}


def _prod_env() -> dict:
    return {k: v for k, v in os.environ.items()
            if k not in ("VECTOR_TEST_DATA_DIR", "VECTOR_DATA_DIR", "VECTOR_DB_PATH")}


@pytest.mark.parametrize("name", sorted(_STORES))
def test_production_path_is_unchanged_repo_data_dir(name):
    mod, attr, fname = _STORES[name]
    out = subprocess.check_output(
        [sys.executable, "-c", f"from {mod} import {attr} as p; print(p.resolve())"],
        cwd=ROOT, env=_prod_env(), text=True,
    ).strip().splitlines()[-1]
    assert Path(out) == (LIVE_DATA / fname).resolve()


@pytest.mark.parametrize("name", sorted(_STORES))
def test_store_default_path_follows_session_data_dir_not_live(name):
    mod, attr, fname = _STORES[name]
    path = Path(getattr(importlib.import_module(mod), attr)).resolve()
    assert path.name == fname
    assert LIVE_DATA.resolve() not in path.parents
    assert path.parent == Path(os.environ["VECTOR_TEST_DATA_DIR"]).resolve()


def test_session_db_and_data_dir_are_temp_not_live():
    from core.memory.db_utils import configured_db_path
    from core.runtime_paths import data_path

    db = configured_db_path().resolve()
    assert db != (ROOT / "vector_memory.db").resolve()
    assert db.parent == Path(os.environ["VECTOR_TEST_DATA_DIR"]).resolve().parent
    assert LIVE_DATA.resolve() not in data_path("x").resolve().parents


def test_guard_recognises_live_paths_and_aborts(monkeypatch):
    conftest = next(m for n, m in sys.modules.items()
                    if n.endswith("conftest") and hasattr(m, "_is_live_path"))
    assert conftest._is_live_path(str(ROOT / "vector_memory.db"))
    assert conftest._is_live_path(str(LIVE_DATA / "epistemic.db"))
    from core.memory.db_utils import configured_db_path
    assert not conftest._is_live_path(str(configured_db_path()))

    monkeypatch.setattr("core.memory.db_utils.configured_db_path", lambda: ROOT / "vector_memory.db")
    with pytest.raises(pytest.exit.Exception):
        conftest._assert_not_live("test")


def test_dedup_state_does_not_leak_between_sessions():
    """The 2026-09-24 regression: a mocked Dev.to publish recorded a 24h dedup row in the live DB,
    so the next run's identical test failed. Two back-to-back sessions must both pass."""
    cmd = [sys.executable, "-m", "pytest", "tests/test_postiz_absorption.py", "-k", "DevTo",
           "-q", "-p", "no:cacheprovider", "-o", "addopts=--tb=short -q"]
    for _ in range(2):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout[-800:] + r.stderr[-400:]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
