"""Per-district load smoke as a pytest gate (roadmap #9).

Wraps scripts/district_smoke.py so CI fails if any first-class district agent
module breaks at import time (the most common "district is broken" failure).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SMOKE = Path(__file__).resolve().parents[2] / "scripts" / "district_smoke.py"


def _load_smoke():
    spec = importlib.util.spec_from_file_location("district_smoke", _SMOKE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _districts():
    smoke = _load_smoke()
    return smoke, sorted(
        p.name for p in smoke.DISTRICTS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("__")
    )


_SMOKE_MOD, _DISTRICT_NAMES = _districts()


@pytest.mark.parametrize("district", _DISTRICT_NAMES)
def test_district_agents_import_clean(district):
    result = _SMOKE_MOD.smoke_district(district)
    assert result["pass"] > 0, f"{district}: no modules imported"
    assert not result["fail"], (
        f"{district} has broken agent modules: "
        + "; ".join(f"{m}: {tb}" for m, tb in result["fail"])
    )
