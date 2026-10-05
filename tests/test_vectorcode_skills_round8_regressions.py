"""Regression coverage for the round-8 skills audit."""

from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(relative_path: str, module_name: str):
    path = ROOT / relative_path
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_godmode_loader_restores_argv_when_loaded_script_raises(tmp_path, monkeypatch):
    scripts = tmp_path / "skills" / "red-teaming" / "godmode" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "parseltongue.py").write_text(
        "raise RuntimeError('broken skill')\n", encoding="utf-8"
    )
    monkeypatch.setenv("VECTOR_HOME", str(tmp_path))
    original = ["vector", "original"]
    monkeypatch.setattr(sys, "argv", original)

    with pytest.raises(RuntimeError, match="broken skill"):
        runpy.run_path(
            str(
                ROOT
                / "vectorcode/src/skills/red-teaming/godmode/scripts/load_godmode.py"
            )
        )

    assert sys.argv is original

