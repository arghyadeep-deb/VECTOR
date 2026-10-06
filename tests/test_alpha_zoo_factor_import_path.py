"""Regression for districts/investment/alpha_zoo/: every vendored factor file
imported its sibling helper module as `from src.factors.X import ...`, the
upstream package's own internal path, which was never rewritten when the
package was vendored into districts/investment/alpha_zoo/factors/. Since
AlphaZooLoader.load_factor() execs each factor file standalone via
importlib.util.spec_from_file_location (no package context, so even a
relative import wouldn't have resolved), every factor except the handful
with no src.factors import raised ModuleNotFoundError: No module named
'src.factors' the moment stock_analyst.py's "alpha_zoo" integration tried to
load it -- found by the core/+districts/ real-import smoke sweep, which
discovered 420+ of alpha_zoo's 465 files failing this exact way.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from districts.investment.alpha_zoo import AlphaZooLoader

_ALPHA_ZOO_DIR = Path(__file__).resolve().parent.parent / "districts" / "investment" / "alpha_zoo"


@pytest.mark.parametrize(
    "factor_name",
    ["carhart_mom", "hml", "cma", "rmw", "alpha_001", "beta10", "vma20", "vstd10"],
)
def test_alpha_zoo_factor_loads(factor_name: str) -> None:
    loader = AlphaZooLoader()
    mod = loader.load_factor(factor_name)
    assert mod is not None


def test_no_remaining_stale_src_factors_import() -> None:
    """Guard against the bug being reintroduced by a future vendor refresh."""
    offenders = []
    pattern = re.compile(r"\bsrc\.factors\b")
    for f in _ALPHA_ZOO_DIR.rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        if pattern.search(f.read_text(encoding="utf-8")):
            offenders.append(str(f.relative_to(_ALPHA_ZOO_DIR)))
    assert offenders == [], f"stale src.factors import(s) found: {offenders}"
