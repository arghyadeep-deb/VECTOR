"""Regression test for a real bug an independent review found:
`write_note_personal`/`overwrite_note_personal` (core/loop/
permission_gateway.py) built the note's write path as
`pathlib.Path(vault) / f"{title}.md"` with zero sanitisation of `title`/
`note` (both action.params-supplied). Two real ways that goes wrong:
(1) `../`-style traversal escapes the vault directory; (2) if the name
LOOKS like an absolute path, pathlib's `/` operator silently DISCARDS the
vault prefix entirely (`Path("/vault") / "/etc/passwd" == Path("/etc/
passwd")`) -- a real arbitrary-file-write, not merely a constrained
traversal.

Per .claude/rules/testing.md, `permission_gateway.py` is never mocked --
this test drives the real `execute()`/`_execute_action()`/
`safe_vault_note_path()` implementation directly, writing into a real
temp-directory vault (tmp_path), never a mock filesystem.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.loop.permission_gateway import Action, PermissionGateway, safe_vault_note_path


def test_traversal_title_is_refused(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    outside_target = tmp_path / "outside.md"

    from core.config import CONFIG
    monkeypatch.setitem(CONFIG, "obsidian_vault_path", str(vault))

    gw = PermissionGateway()
    action = Action(
        action_type="write_note_personal",
        params={"title": "../outside", "content": "attacker content"},
        proposed_by="test",
    )
    import asyncio
    result = asyncio.run(gw._execute_action(action))

    assert result["status"] == "error"
    assert "escapes the configured vault" in result["error"]
    assert not outside_target.exists(), (
        "the traversal write must never actually land outside the vault"
    )


def test_absolute_path_title_is_refused(tmp_path, monkeypatch):
    """The specific, worse variant: pathlib's own `/` operator discards the
    vault prefix entirely when the right-hand side looks absolute."""
    vault = tmp_path / "vault"
    vault.mkdir()
    absolute_target = tmp_path / "pwned.md"

    from core.config import CONFIG
    monkeypatch.setitem(CONFIG, "obsidian_vault_path", str(vault))

    gw = PermissionGateway()
    action = Action(
        action_type="write_note_personal",
        params={"title": str(absolute_target)[:-3], "content": "attacker content"},
        proposed_by="test",
    )
    import asyncio
    result = asyncio.run(gw._execute_action(action))

    assert result["status"] == "error"
    assert not absolute_target.exists(), (
        "an absolute-path-shaped title must never let pathlib's '/' "
        "operator silently discard the vault prefix"
    )


def test_legitimate_title_still_writes_inside_vault(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()

    from core.config import CONFIG
    monkeypatch.setitem(CONFIG, "obsidian_vault_path", str(vault))

    gw = PermissionGateway()
    action = Action(
        action_type="write_note_personal",
        params={"title": "My Real Note", "content": "real content"},
        proposed_by="test",
    )
    import asyncio
    result = asyncio.run(gw._execute_action(action))

    assert result["status"] == "ok"
    written = vault / "My Real Note.md"
    assert written.exists()
    assert written.read_text(encoding="utf-8") == "real content"


def test_safe_vault_note_path_helper_directly():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        assert safe_vault_note_path(d, "normal") is not None
        assert safe_vault_note_path(d, "../escape") is None
        assert safe_vault_note_path(d, "") is None
        assert safe_vault_note_path("", "normal") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
