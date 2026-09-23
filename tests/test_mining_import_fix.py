"""Regression test for the 2026-09-24 external review's Phase 1 finding:
core/mining/__init__.py and core/mining/discovery.py imported
core.mining.stubs, which never existed -- MiningCapabilities actually
lives in core.mining._abc. Any core.mining.* import failed, breaking
core/api/routers/mining.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_core_mining_package_imports():
    import core.mining
    assert core.mining.MiningCapabilities is not None
    assert callable(core.mining.detect_for_engine_model)
    assert callable(core.mining.check_docker_available)


def test_mining_router_imports():
    from core.api.routers.mining import router
    assert router is not None


def test_mining_capabilities_is_the_real_abc_class():
    from core.mining import MiningCapabilities
    from core.mining._abc import MiningCapabilities as RealMiningCapabilities
    assert MiningCapabilities is RealMiningCapabilities


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
