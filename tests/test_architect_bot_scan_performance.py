"""architect_bot.scan_codebase used an O(n^2) all-pairs substring scan (90-216s on this repo),
parsed every file twice, walked vendor dirs, and blocked the event loop from an async run().
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from districts.coding.architect_bot import ArchitectBot, _iter_python_files


def _bot() -> ArchitectBot:
    return ArchitectBot()


def test_skips_vendor_and_junk_directories(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    for junk in ("node_modules", ".git", "test_tmp", "_cleanup_trash_2026-07-28"):
        (tmp_path / junk).mkdir()
        (tmp_path / junk / "b.py").write_text("y = 2\n")
    found = {p.name for p in _iter_python_files(tmp_path)}
    assert found == {"a.py"}


def test_detects_mutual_imports_and_ignores_one_way(tmp_path):
    (tmp_path / "alpha.py").write_text("import beta\n")
    (tmp_path / "beta.py").write_text("import alpha\n")
    (tmp_path / "gamma.py").write_text("import alpha\n")
    result = _bot().scan_codebase(str(tmp_path))
    circ = [i for i in result["issues"] if "Potential circular import" in i]
    assert len(circ) == 1 and "alpha.py" in circ[0] and "beta.py" in circ[0]
    assert result["files"] == 3


def test_counts_classes_and_functions_with_a_single_parse(tmp_path):
    (tmp_path / "m.py").write_text("class A:\n    def f(self): pass\nasync def g(): pass\n")
    result = _bot().scan_codebase(str(tmp_path))
    assert (result["classes"], result["functions"]) == (1, 2)


def test_scan_scales_roughly_linearly(tmp_path):
    for i in range(1500):
        (tmp_path / f"mod{i}.py").write_text(f"import mod{(i + 1) % 1500}\n")
    t = time.perf_counter()
    result = _bot().scan_codebase(str(tmp_path))
    assert result["files"] == 1500
    assert time.perf_counter() - t < 20  # the old all-pairs scan needed minutes at this size


@pytest.mark.asyncio
async def test_run_does_not_block_the_event_loop(tmp_path):
    import asyncio

    for i in range(300):
        (tmp_path / f"m{i}.py").write_text("x = 1\n")
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        result = await _bot().run({"type": "scan", "root": str(tmp_path)})
    finally:
        task.cancel()
    assert result["status"] == "ok"
    assert ticks >= 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
