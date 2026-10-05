"""Regression tests for round-8 fixed-repository source resolvers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(relative_path: str, module_name: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("relative_path", "class_name", "url_name"),
    [
        (
            "vectorcode/src/skills/sources/openclaw.py",
            "OpenClawResolver",
            "OPENCLAW_REPO_URL",
        ),
        (
            "vectorcode/src/skills/sources/vector_source.py",
            "VectorSkillResolver",
            "VECTOR_SKILL_REPO_URL",
        ),
    ],
)
def test_fixed_source_clone_terminates_git_options(
    relative_path, class_name, url_name, tmp_path, monkeypatch
):
    module = _load(relative_path, f"round8_{class_name}")
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda argv, **kwargs: calls.append(argv))
    cache_root = tmp_path / "--upload-pack=payload"

    getattr(module, class_name)(cache_root=cache_root).sync()

    assert calls == [
        ["git", "clone", "--", getattr(module, url_name), str(cache_root)]
    ]

