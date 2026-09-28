"""ArchitectBot's optional 'ask ResearchHub for best practices' request must not hold up the scan (fixed 2026-09-26).

It used to be awaited. That was harmless only while DeepResearcher rejected the 'deep_research' task type instantly; once the
advertised type became real (a 1-3 minute web research call) every scan/read_code stalled behind it.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from districts.coding.architect_bot import ArchitectBot


@pytest.mark.asyncio
async def test_scan_returns_without_waiting_for_the_research_help(isolated_vector_db, monkeypatch, tmp_path):
    (tmp_path / "m.py").write_text("class A:\n    def f(self):\n        return 1\n", encoding="utf-8")
    bot = ArchitectBot()
    started, finished = [], []

    async def slow_help(name, task):
        started.append(name)
        await asyncio.sleep(3)
        finished.append(name)
        return {"status": "ok"}

    monkeypatch.setattr(bot, "request_agent_help", slow_help)
    monkeypatch.setattr(bot, "scan_codebase", lambda root: {"files": 1, "lines": 3, "tech_stack": ["python"], "issues": []})
    t0 = time.monotonic()
    out = await bot.run({"type": "scan", "params": {"root": str(tmp_path), "use_graph": False}})
    elapsed = time.monotonic() - t0
    assert out["status"] == "ok"
    assert elapsed < 1.5, f"scan waited {elapsed:.1f}s for the optional research help"
    await asyncio.sleep(0.1)
    assert started == ["ResearchHub"] and not finished, "the help request should be running in the background"


@pytest.mark.asyncio
async def test_a_failing_help_request_never_breaks_the_scan(isolated_vector_db, monkeypatch, tmp_path):
    bot = ArchitectBot()

    async def boom(name, task):
        raise RuntimeError("hub down")

    monkeypatch.setattr(bot, "request_agent_help", boom)
    monkeypatch.setattr(bot, "scan_codebase", lambda root: {"files": 1, "lines": 3, "tech_stack": ["python"], "issues": []})
    out = await bot.run({"type": "scan", "params": {"root": str(tmp_path), "use_graph": False}})
    await asyncio.sleep(0.1)
    assert out["status"] == "ok"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
