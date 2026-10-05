from pathlib import Path

import pytest

from vectorcode.src.learning.distillation.execute.appliers.lora_stub import _edit_path


def test_lora_edit_path_accepts_direct_child(tmp_path: Path) -> None:
    assert _edit_path(tmp_path, "edit-1", suffix=".json") == (
        tmp_path / "edit-1.json"
    ).resolve()


@pytest.mark.parametrize("edit_id", ["../escape", "nested/escape"])
def test_lora_edit_path_rejects_traversal(tmp_path: Path, edit_id: str) -> None:
    with pytest.raises(ValueError, match="Unsafe edit id"):
        _edit_path(tmp_path, edit_id, suffix=".json")


def test_lora_edit_path_rejects_absolute_override(tmp_path: Path) -> None:
    absolute_id = str((tmp_path.parent / "outside").resolve())

    with pytest.raises(ValueError, match="Unsafe edit id"):
        _edit_path(tmp_path, absolute_id)
