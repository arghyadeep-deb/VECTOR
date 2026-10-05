"""Regression tests for crash-safe PowerPoint/Office helper writes."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parents[1]


def _load(relative_path: str, name: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


@pytest.mark.parametrize(
    ("relative_path", "name"),
    [
        (
            "vectorcode/src/skills/productivity/powerpoint/scripts/office/helpers/merge_runs.py",
            "merge_runs_atomic",
        ),
        (
            "vectorcode/src/skills/productivity/powerpoint/scripts/office/helpers/simplify_redlines.py",
            "simplify_redlines_atomic",
        ),
    ],
)
def test_xml_atomic_write_preserves_original_when_replace_fails(
    tmp_path, monkeypatch, relative_path, name
):
    module = _load(relative_path, name)
    target = tmp_path / "document.xml"
    target.write_bytes(b"original")
    monkeypatch.setattr(module.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("crash")))

    with pytest.raises(OSError, match="crash"):
        module._atomic_write_bytes(target, b"replacement")

    assert target.read_bytes() == b"original"
    assert list(tmp_path.glob("*.tmp")) == []


def test_pack_preserves_existing_archive_when_zip_creation_fails(tmp_path, monkeypatch):
    validators = types.ModuleType("validators")
    validators.DOCXSchemaValidator = object
    validators.PPTXSchemaValidator = object
    validators.RedliningValidator = object
    monkeypatch.setitem(sys.modules, "validators", validators)
    module = _load(
        "vectorcode/src/skills/productivity/powerpoint/scripts/office/pack.py",
        "pack_atomic",
    )
    source = tmp_path / "unpacked"
    source.mkdir()
    (source / "content.txt").write_text("content", encoding="utf-8")
    output = tmp_path / "document.pptx"
    output.write_bytes(b"original archive")

    class BrokenZipFile:
        def __init__(self, *args, **kwargs):
            raise OSError("archive write failed")

    monkeypatch.setattr(module.zipfile, "ZipFile", BrokenZipFile)

    with pytest.raises(OSError, match="archive write failed"):
        module.pack(str(source), str(output), validate=False)

    assert output.read_bytes() == b"original archive"
