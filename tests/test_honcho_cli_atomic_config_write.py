"""Regression for vectorcode/src/plugins/memory/honcho/cli.py's _write_config():

It wrote the Honcho config (which stores per-host apiKey/baseUrl credentials)
via a plain path.write_text() -- a crash mid-write truncates the file, and
_read_config()'s broad except silently swallows the resulting
JSONDecodeError and falls back to an empty config, which looks like the
user's Honcho setup (and API key) was simply lost. Fixed with a
tempfile + fsync + os.replace atomic write.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from plugins.memory.honcho import cli as honcho_cli  # noqa: E402


def test_write_config_is_atomic_and_leaves_no_tmp_file(tmp_path):
    target = tmp_path / "honcho.json"
    honcho_cli._write_config({"hosts": {"vector": {"apiKey": "sk-real-key"}}}, path=target)

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8"))["hosts"]["vector"]["apiKey"] == "sk-real-key"

    leftover_tmp_files = list(tmp_path.glob(".*.tmp"))
    assert leftover_tmp_files == [], f"atomic write left temp files behind: {leftover_tmp_files}"


def test_write_config_overwrite_preserves_old_content_on_mkstemp_failure(tmp_path, monkeypatch):
    target = tmp_path / "honcho.json"
    honcho_cli._write_config({"hosts": {"vector": {"apiKey": "original-key"}}}, path=target)
    original_bytes = target.read_bytes()

    def _boom(*_args, **_kwargs):
        raise OSError("simulated disk failure mid-write")

    monkeypatch.setattr(honcho_cli.tempfile, "mkstemp", _boom)

    try:
        honcho_cli._write_config({"hosts": {"vector": {"apiKey": "new-key"}}}, path=target)
    except OSError:
        pass

    # The original, valid config must still be intact -- never truncated.
    assert target.read_bytes() == original_bytes
    assert json.loads(target.read_text(encoding="utf-8"))["hosts"]["vector"]["apiKey"] == "original-key"
