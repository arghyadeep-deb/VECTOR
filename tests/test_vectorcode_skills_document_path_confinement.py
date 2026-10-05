"""Path-confinement regressions for document helper scripts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parents[1]


def _load(relative_path: str, module_name: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_powerpoint_source_cannot_escape_slides_directory(tmp_path):
    module = _load(
        "vectorcode/src/skills/productivity/powerpoint/scripts/add_slide.py",
        "vectorcode_add_slide",
    )
    slides = tmp_path / "ppt" / "slides"
    slides.mkdir(parents=True)
    outside = tmp_path / "secret.xml"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="direct child"):
        module.duplicate_slide(tmp_path, "../../secret.xml")


def test_powerpoint_absolute_layout_path_is_rejected(tmp_path):
    module = _load(
        "vectorcode/src/skills/productivity/powerpoint/scripts/add_slide.py",
        "vectorcode_add_slide_absolute",
    )
    layouts = tmp_path / "ppt" / "slideLayouts"
    layouts.mkdir(parents=True)
    outside = tmp_path / "outside.xml"
    outside.write_text("layout", encoding="utf-8")

    with pytest.raises(ValueError, match="direct child"):
        module.create_slide_from_layout(tmp_path, str(outside.resolve()))


def test_marker_image_name_cannot_escape_output_directory(tmp_path):
    module = _load(
        "vectorcode/src/skills/productivity/ocr-and-documents/scripts/extract_marker.py",
        "vectorcode_extract_marker",
    )
    output = tmp_path / "images"

    with pytest.raises(ValueError, match="Unsafe rendered image name"):
        module._save_rendered_images({"../escaped.png": b"secret"}, output)

    assert not (tmp_path / "escaped.png").exists()


def test_marker_saves_bytes_and_image_objects(tmp_path):
    module = _load(
        "vectorcode/src/skills/productivity/ocr-and-documents/scripts/extract_marker.py",
        "vectorcode_extract_marker_values",
    )

    class FakeImage:
        def save(self, path):
            Path(path).write_bytes(b"pil-image")

    output = tmp_path / "images"
    module._save_rendered_images(
        {"raw.bin": b"raw", "nested/image.png": FakeImage()}, output
    )

    assert (output / "raw.bin").read_bytes() == b"raw"
    assert (output / "nested/image.png").read_bytes() == b"pil-image"
