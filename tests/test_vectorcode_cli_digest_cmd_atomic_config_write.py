"""Regression for vectorcode/src/cli/digest_cmd.py's _save_digest_schedule():

It wrote the main config.toml (not just the [digest] section -- the whole
file) directly via write_text(), non-atomically. A crash mid-write would
truncate/corrupt the entire VECTOR config file, not just the digest
settings. Fixed with tempfile + fsync + os.replace.
"""
from __future__ import annotations

import os

from vectorcode.src.cli.digest_cmd import _save_digest_schedule


def test_save_digest_schedule_preserves_existing_content_on_replace_failure(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.toml"
    original = '[other]\nkey = "value"\n'
    config_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(
        "vectorcode.src.cli.digest_cmd.DEFAULT_CONFIG_PATH", config_path
    )

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    try:
        _save_digest_schedule(enabled=True, cron="0 6 * * *")
    except OSError:
        pass

    assert config_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".config.toml.*.tmp")) == []


def test_save_digest_schedule_writes_new_section_atomically(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(
        "vectorcode.src.cli.digest_cmd.DEFAULT_CONFIG_PATH", config_path
    )

    _save_digest_schedule(enabled=True, cron="0 6 * * *")

    content = config_path.read_text(encoding="utf-8")
    assert "[digest]" in content
    assert "enabled = true" in content
    assert 'schedule = "0 6 * * *"' in content
    assert list(tmp_path.glob(".config.toml.*.tmp")) == []
