"""Regression for 2 bugs found in core/science/ during the Phase 3
whole-repo audit (2026-10-02):

1. physics_engine.py's PhysicsEngine._disconnect() used the bare
   "[VECTOR] silent swallow" placeholder (no exc_info, no real message at
   all) on a PyBullet disconnect failure -- same systemic bug fixed 50+
   times this cycle.

2. chemistry_engine.py's _heuristic_analyze() (the RDKit-unavailable
   fallback) computed ring_count as smiles.count("1") + smiles.count("2")
   -- but a SMILES ring-closure digit appears exactly twice (open + close
   of the same ring bond), so this doubled every real ring count (e.g.
   "c1ccccc1" has 1 ring but 2 "1"s).
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.science.physics_engine import PhysicsEngine
from core.science.chemistry_engine import ChemistryEngine


def test_physics_disconnect_logs_real_exception_not_placeholder():
    eng = PhysicsEngine.__new__(PhysicsEngine)
    eng._pybullet = MagicMock()
    eng._pybullet.disconnect.side_effect = RuntimeError("boom")
    eng._physics_client = 1

    with patch("core.science.physics_engine.logger") as mock_logger:
        eng._disconnect()

    assert mock_logger.warning.called
    args = mock_logger.warning.call_args[0]
    assert "silent swallow" not in args[0]
    assert "boom" in str(mock_logger.warning.call_args)


def test_chemistry_heuristic_ring_count_not_doubled():
    eng = ChemistryEngine()
    # Benzene: 1 real ring, SMILES uses digit "1" twice (open + close).
    result = eng._heuristic_analyze("c1ccccc1")
    assert result["ring_count"] == 1

    # Two separate rings using digits 1 and 2 (naphthalene-style numbering
    # reuse aside, this still exercises the //2 math on a 2-digit case).
    result2 = eng._heuristic_analyze("c1ccc2ccccc2c1")
    assert result2["ring_count"] == 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
