"""Regression test for core/city/meta_cognition.py's silent-swallow placeholder
logging bug, found by a Claude self-fork's deep-verify pass on core/city/
(Phase 3 whole-repo audit, Claude/Codex 50/50 split, 2026-09-30).

Same bug class already fixed in core/brain/ (commit bd5f842da) and core/loop/
(commit 6426954e4): an earlier automated pass left the literal placeholder
`logger.warning("[VECTOR] silent swallow")` in an except block with zero
exception info, hiding whatever actually failed. MetaCognition.close() was
the one recurrence found in core/city/.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.meta_cognition import MetaCognition


def test_close_failure_logs_real_exception(monkeypatch, caplog):
    db_path = Path(tempfile.mkdtemp()) / "test_meta_cognition.db"
    mc = MetaCognition(db_path=str(db_path))

    broken_conn = MagicMock()
    broken_conn.close.side_effect = RuntimeError("disk gone")
    mc._conn = broken_conn

    logged = []
    from loguru import logger
    handler_id = logger.add(lambda msg: logged.append(str(msg)), level="WARNING")
    try:
        mc.close()  # must not raise
    finally:
        logger.remove(handler_id)

    assert any("disk gone" in line for line in logged), (
        "close() failure must log the real exception, not a placeholder string"
    )
    assert not any("silent swallow" in line for line in logged)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
