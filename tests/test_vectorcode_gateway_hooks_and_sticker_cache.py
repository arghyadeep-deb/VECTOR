"""Regression tests for gateway hook logging and sticker-cache persistence."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import sys

import pytest


def _load_sticker_cache_module():
    path = Path("vectorcode/src/gateway/sticker_cache.py")
    source_root = str(path.parent.parent)
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    spec = importlib.util.spec_from_file_location("audited_sticker_cache", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hooks_production_code_does_not_call_print() -> None:
    path = Path("vectorcode/src/gateway/hooks.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]
    assert calls == []


def test_corrupt_sticker_cache_fails_open_instead_of_crashing_handler(tmp_path: Path) -> None:
    # Unlike the vault/webhook stores, this is a cheaply-regenerable
    # performance cache with exactly one caller (telegram.py's sticker
    # handler) that does NOT wrap the lookup in a try/except. A corrupt
    # cache file must therefore fail open (treated as empty, logged as a
    # warning) rather than raise -- raising here would crash sticker
    # handling for every message, not just cost one extra vision call.
    module = _load_sticker_cache_module()
    cache_path = tmp_path / "sticker_cache.json"
    corrupt_content = '{"existing": '
    cache_path.write_text(corrupt_content, encoding="utf-8")
    module.CACHE_PATH = cache_path

    assert module.get_cached_description("new-id") is None

    module.cache_sticker_description("new-id", "new description")

    saved = json.loads(cache_path.read_text(encoding="utf-8"))
    assert saved["new-id"]["description"] == "new description"
