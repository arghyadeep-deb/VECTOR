"""Regression for vectorcode/src/plugins/memory/{mem0,honcho}/__init__.py's
save_config(): both wrote their provider config (which stores api_key /
per-host apiKey) via a plain path.write_text() with no explicit encoding.
A crash mid-write truncates the file, and the provider's own read path
swallows the resulting parse error and silently falls back to an empty
config -- looking like the stored API key was simply lost. Fixed with a
tempfile + fsync + os.replace atomic write, matching the sibling fix
already applied to memory/honcho/cli.py's _write_config().
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from plugins.memory.mem0 import Mem0MemoryProvider  # noqa: E402
from plugins.memory.honcho import HonchoMemoryProvider  # noqa: E402


def test_mem0_save_config_is_atomic(tmp_path):
    provider = Mem0MemoryProvider()
    provider.save_config({"api_key": "mem0-real-key"}, str(tmp_path))

    config_path = tmp_path / "mem0.json"
    assert json.loads(config_path.read_text(encoding="utf-8"))["api_key"] == "mem0-real-key"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_mem0_save_config_preserves_old_content_on_write_failure(tmp_path, monkeypatch):
    provider = Mem0MemoryProvider()
    provider.save_config({"api_key": "original-key"}, str(tmp_path))
    config_path = tmp_path / "mem0.json"
    original_bytes = config_path.read_bytes()

    import tempfile as real_tempfile

    def _boom(*_args, **_kwargs):
        raise OSError("simulated disk failure mid-write")

    monkeypatch.setattr(real_tempfile, "mkstemp", _boom)
    try:
        provider.save_config({"api_key": "new-key"}, str(tmp_path))
    except OSError:
        pass

    assert config_path.read_bytes() == original_bytes


def test_honcho_save_config_is_atomic(tmp_path):
    provider = HonchoMemoryProvider()
    provider.save_config({"apiKey": "honcho-real-key"}, str(tmp_path))

    config_path = tmp_path / "honcho.json"
    assert json.loads(config_path.read_text(encoding="utf-8"))["apiKey"] == "honcho-real-key"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_honcho_save_config_preserves_old_content_on_write_failure(tmp_path, monkeypatch):
    provider = HonchoMemoryProvider()
    provider.save_config({"apiKey": "original-key"}, str(tmp_path))
    config_path = tmp_path / "honcho.json"
    original_bytes = config_path.read_bytes()

    import tempfile as real_tempfile

    def _boom(*_args, **_kwargs):
        raise OSError("simulated disk failure mid-write")

    monkeypatch.setattr(real_tempfile, "mkstemp", _boom)
    try:
        provider.save_config({"apiKey": "new-key"}, str(tmp_path))
    except OSError:
        pass

    assert config_path.read_bytes() == original_bytes
