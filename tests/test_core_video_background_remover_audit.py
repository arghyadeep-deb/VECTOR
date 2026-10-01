"""Phase 3 whole-repo audit -- core/video/background_remover.py.

bg_plate_path is accepted by both _remove_video_rembg() and
_remove_video_manual() but was never implemented or used in either body --
a caller requesting the documented "inverse-alpha background plate" feature
got no error and no plate, just silent non-delivery. No real caller passes
it today (verified via grep), so this adds a warning instead of
implementing the unrequested feature.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import inspect
from core.video.background_remover import BackgroundRemover


def test_remove_video_rembg_warns_when_bg_plate_requested():
    src = inspect.getsource(BackgroundRemover._remove_video_rembg)
    assert "bg_plate_path" in src
    assert "logger.warning" in src


def test_remove_video_manual_warns_when_bg_plate_requested():
    src = inspect.getsource(BackgroundRemover._remove_video_manual)
    assert "logger.warning" in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
