"""Regression tests for sensitive context-reference path blocking."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


VECTORCODE_SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(VECTORCODE_SRC) not in sys.path:
    sys.path.insert(0, str(VECTORCODE_SRC))


@pytest.mark.parametrize("relative", [Path(".SSH/ID_RSA"), Path(".AWS/credentials")])
def test_sensitive_home_paths_are_blocked_case_insensitively(tmp_path, monkeypatch, relative):
    module = importlib.import_module("agent.context_references")
    constants = importlib.import_module("vector_constants")
    home = tmp_path / "UserHome"
    vector_home = tmp_path / "VectorHome"
    monkeypatch.setattr(module.os.path, "expanduser", lambda _value: str(home))
    monkeypatch.setattr(constants, "get_vector_home", lambda: vector_home)

    with pytest.raises(ValueError, match="sensitive credential"):
        module._ensure_reference_path_allowed(home / relative)


def test_vector_env_is_blocked_case_insensitively(tmp_path, monkeypatch):
    module = importlib.import_module("agent.context_references")
    constants = importlib.import_module("vector_constants")
    home = tmp_path / "UserHome"
    vector_home = tmp_path / "VectorHome"
    monkeypatch.setattr(module.os.path, "expanduser", lambda _value: str(home))
    monkeypatch.setattr(constants, "get_vector_home", lambda: vector_home)

    with pytest.raises(ValueError, match="sensitive credential"):
        module._ensure_reference_path_allowed(vector_home / ".ENV")
