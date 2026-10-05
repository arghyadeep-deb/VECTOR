"""Regression tests for safe godmode configuration persistence."""

import importlib.util
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "vectorcode/src/skills/red-teaming/godmode/scripts/auto_jailbreak.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("auto_jailbreak_persistence", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_write_config_preserves_corrupt_existing_file(tmp_path):
    module = _load_module()
    config = tmp_path / "config.yaml"
    original = "agent: [unterminated"
    config.write_text(original, encoding="utf-8")
    module.CONFIG_PATH = config

    with pytest.raises(ValueError, match="invalid config"):
        module._write_config(system_prompt="replacement")

    assert config.read_text(encoding="utf-8") == original


def test_undo_keeps_prefill_when_config_cannot_be_updated(tmp_path):
    module = _load_module()
    config = tmp_path / "config.yaml"
    prefill = tmp_path / "prefill.json"
    config.write_text("agent: [unterminated", encoding="utf-8")
    prefill.write_text('[{"role": "assistant"}]', encoding="utf-8")
    module.CONFIG_PATH = config
    module.PREFILL_PATH = prefill

    assert module.undo_jailbreak(verbose=False) is False
    assert prefill.exists()


def test_atomic_write_preserves_destination_when_replace_fails(tmp_path, monkeypatch):
    module = _load_module()
    destination = tmp_path / "config.yaml"
    destination.write_text("original", encoding="utf-8")

    def fail_replace(_source, _destination):
        raise OSError("simulated crash")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated crash"):
        module._atomic_write(destination, "replacement")

    assert destination.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.iterdir()) == [destination]
