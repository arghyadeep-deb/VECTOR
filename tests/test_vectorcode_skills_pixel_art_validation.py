"""Regression tests for pixel-art argument and small-image handling."""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest
from PIL import Image


SCRIPTS = Path(__file__).parents[1] / "vectorcode/src/skills/creative/pixel-art/scripts"


def _load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_pixel_art_rejects_zero_block_before_resizing(tmp_path):
    module = _load("pixel_art.py", "vectorcode_pixel_art")
    source = tmp_path / "source.png"
    Image.new("RGB", (2, 2)).save(source)

    with pytest.raises(ValueError, match="block must be a positive integer"):
        module.pixel_art(source, tmp_path / "out.png", block=0)


def test_animation_initializers_support_tiny_images():
    module = _load("pixel_art_video.py", "vectorcode_pixel_art_video_tiny")
    rng = random.Random(1)

    for initializer in (module.init_fireflies, module.init_dust_motes, module.init_bubbles):
        assert initializer(rng, 1, 1)


@pytest.mark.parametrize(("field", "value"), [("fps", 0), ("duration", 0)])
def test_video_rejects_non_positive_timing_before_ffmpeg_lookup(tmp_path, field, value):
    module = _load("pixel_art_video.py", f"vectorcode_pixel_art_video_{field}")
    kwargs = {field: value}

    with pytest.raises(ValueError, match=field):
        module.pixel_art_video(tmp_path / "missing.png", tmp_path / "out.mp4", **kwargs)
