"""VECTOR Financial Intelligence"""
import sys as _sys
from pathlib import Path as _Path

# 2026-07-29: the vendored Fincept analytics suite under this package (1,400+
# scripts) uses absolute imports written for its own standalone layout
# (e.g. `from corporateFinance.valuation.trading_comps import ...`,
# `from corporateFinance.deal_database.database_schema import ...`) that
# assume THIS directory (Analytics/) is itself on sys.path, not nested
# under districts.investment.vector_finagent. Several of this package's own
# __init__.py files (e.g. corporateFinance/valuation/__init__.py) already
# compute an `analytics_path = Path(__file__).parent.parent.parent` for
# exactly this purpose but never actually add it to sys.path — an
# incomplete migration, not a design choice to work around per-file.
# Completing it once here (Analytics/__init__.py always runs before any
# submodule import, per normal Python package init order) makes the
# vendor's own absolute-import convention resolve correctly everywhere in
# this tree, without touching hundreds of individual vendored files. Found
# via finagent_agent.py's DCF endpoint failing with "No module named
# 'corporateFinance'" (KNOWN_ISSUES.md, 2026-07-29).
_analytics_root = str(_Path(__file__).parent)
if _analytics_root not in _sys.path:
    _sys.path.insert(0, _analytics_root)
