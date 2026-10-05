"""Regression tests for MarkdownStoreTool (shared base for memory_manage.py /
user_profile_manage.py).

Pre-fix, ``_remove("")`` wiped the ENTIRE backing file: the list
comprehension ``[ln for ln in lines if entry not in ln]`` evaluates
``"" not in ln`` as False for every line (the empty string is a substring
of everything), producing an empty ``new_lines`` list that then got written
back as the new file content -- total data loss of the user's persistent
profile/memory store, reported back as a success. Pre-fix, ``_update("",
new)`` would similarly have inserted ``new`` at position 0 of the file
(``str.replace("", new, 1)``) instead of failing. Pre-fix, writes were also
non-atomic (plain ``write_text()``), risking truncation on a mid-write crash.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vectorcode.src.vc_tools._markdown_store import MarkdownStoreTool


class _DummyStore(MarkdownStoreTool):
    store_name = "dummy_store"
    subject = "dummy store"
    entry_subject = "dummy entry"
    missing_file_msg = "Dummy store does not exist."


def _make_store(tmp_path: Path, initial: str) -> tuple[_DummyStore, Path]:
    path = tmp_path / "store.md"
    path.write_text(initial, encoding="utf-8")
    return _DummyStore(path), path


def test_remove_empty_entry_does_not_wipe_file(tmp_path: Path) -> None:
    store, path = _make_store(tmp_path, "- alpha\n- beta\n- gamma\n")

    result = store.execute(action="remove", entry="")

    assert result.success is False
    assert path.read_text(encoding="utf-8") == "- alpha\n- beta\n- gamma\n"


def test_update_empty_old_is_rejected(tmp_path: Path) -> None:
    store, path = _make_store(tmp_path, "- alpha\n- beta\n")

    result = store.execute(action="update", entry="", new_entry="INJECTED")

    assert result.success is False
    assert "INJECTED" not in path.read_text(encoding="utf-8")


def test_remove_real_entry_still_works(tmp_path: Path) -> None:
    store, path = _make_store(tmp_path, "- alpha\n- beta\n- gamma\n")

    result = store.execute(action="remove", entry="beta")

    assert result.success is True
    content = path.read_text(encoding="utf-8")
    assert "beta" not in content
    assert "alpha" in content
    assert "gamma" in content


def test_add_then_read_round_trip(tmp_path: Path) -> None:
    store, path = _make_store(tmp_path, "")

    store.execute(action="add", entry="new fact")
    result = store.execute(action="read")

    assert "new fact" in result.content
