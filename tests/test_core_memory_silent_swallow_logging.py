"""Regression test for core/memory/'s silent-swallow placeholder logging bug
(2026-09-30, Phase 3 whole-repo audit, Claude/Codex 50/50 split) -- the same
bug class already fixed in core/brain/ (bd5f842da), core/loop/ (6426954e4),
and core/city/ (2639aaabb): a leftover literal
`logger.warning("[VECTOR] silent swallow")` (or `.exception(...)` for
db_guardian.py) with no real exception info, from an earlier automated pass.

5 sites across 3 files: core/memory/counterfactual.py (CounterfactualMemory.
close), core/memory/episodic.py (close_db_connection, x2 more sub-blocks),
core/memory/db_guardian.py (_alert_owner's notify_owner failure path).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_placeholder_string_never_reappears_in_core_memory():
    """Golden test: the literal '[VECTOR] silent swallow' string must never
    reappear anywhere in core/memory/ -- guards against the same bug class
    being reintroduced."""
    memory_dir = Path(__file__).parent.parent / "core" / "memory"
    hits = []
    for f in memory_dir.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        if "silent swallow" in text:
            hits.append(f.name)
    assert hits == [], f"placeholder silent-swallow log(s) still present in: {hits}"


def test_counterfactual_close_logs_real_exception():
    import loguru
    from core.memory.counterfactual import CounterfactualMemory

    class _BoomConn:
        def close(self):
            raise RuntimeError("boom: connection already closed")

    messages: list[str] = []
    handler_id = loguru.logger.add(lambda m: messages.append(str(m)), level="WARNING")
    try:
        with tempfile.TemporaryDirectory() as td:
            mem = CounterfactualMemory(db_path=str(Path(td) / "cf.db"))
            real_conn = mem._conn
            mem._conn = _BoomConn()  # force a real close() failure
            try:
                mem.close()  # must not raise, must log the real failure
            finally:
                real_conn.close()  # release the file handle for Windows temp-dir cleanup
    finally:
        loguru.logger.remove(handler_id)

    assert any("close failed" in m and "boom" in m for m in messages)


def test_episodic_close_db_connection_logs_real_exception(monkeypatch):
    import loguru
    import core.memory.episodic as episodic

    class _BoomConn:
        def close(self):
            raise RuntimeError("boom: connection already closed")

    monkeypatch.setattr(episodic, "_db_connection", _BoomConn())
    monkeypatch.setattr(episodic, "_DB_KEY", "irrelevant")

    messages: list[str] = []
    handler_id = loguru.logger.add(lambda m: messages.append(str(m)), level="WARNING")
    try:
        episodic.close_db_connection()  # must not raise
    finally:
        loguru.logger.remove(handler_id)

    assert any("singleton close failed" in m and "boom" in m for m in messages)


def test_db_guardian_alert_owner_logs_real_exception():
    import asyncio
    import loguru
    from core.memory.db_guardian import _alert_owner

    async def _boom(*a, **k):
        raise RuntimeError("boom: notify channel down")

    messages: list[str] = []
    handler_id = loguru.logger.add(lambda m: messages.append(str(m)), level="WARNING")
    try:
        with patch("core.cloud.notify.notify_owner", _boom):
            asyncio.run(_alert_owner("test alert"))  # must not raise
    finally:
        loguru.logger.remove(handler_id)

    assert any("notify_owner failed" in m for m in messages)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
