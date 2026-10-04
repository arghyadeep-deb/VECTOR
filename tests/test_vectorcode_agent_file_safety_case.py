"""Regression tests for case-insensitive sensitive-path confinement."""

from __future__ import annotations

import os
import sys
from pathlib import Path


AGENT_SRC = Path("vectorcode/src").resolve()
if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

from agent import file_safety


def test_sensitive_path_case_cannot_bypass_denylist(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "UserHome"
    home.mkdir()
    monkeypatch.setattr(file_safety.os.path, "expanduser", lambda value: str(home) if value == "~" else value)

    target = home / ".SSH" / "ID_RSA"
    expected = os.name == "nt"
    assert file_safety.is_write_denied(str(target)) is expected


def test_safe_root_uses_platform_case_semantics(monkeypatch, tmp_path: Path) -> None:
    safe_root = tmp_path / "Allowed"
    monkeypatch.setenv("VECTOR_WRITE_SAFE_ROOT", str(safe_root))
    differently_cased_child = Path(str(safe_root).swapcase()) / "result.txt"

    expected = os.name != "nt"
    assert file_safety.is_write_denied(str(differently_cased_child)) is expected
