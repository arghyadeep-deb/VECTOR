"""Sub-project A: vendored trees must be importable through VECTOR's own wrappers.

2026-09-24 finding: core/research_engine/api/__init__.py imported the (never vendored) `benchmarks`
package and the news scheduler at module load, so `districts/research/research_api.py` -- used by
deep_researcher and the MCP research tools -- silently failed every call ("Research failed: ...").
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

# (name, module, attribute) -- each is VECTOR's own entry point into a vendored tree
_ENTRY_POINTS = [
    ("finagent", "districts.investment.finagent_agent", None),
    ("backtest", "districts.investment.backtest_agent", None),
    ("mlops", "districts.coding.mlops_agent", None),
    ("alpha_zoo", "districts.investment.stock_analyst", None),
    ("research_engine", "core.research_engine.api", "quick_summary"),
    ("research_engine.settings", "core.research_engine.api.settings_utils", "create_settings_snapshot"),
    ("research wrapper", "districts.research.research_api", "quick_research"),
    ("coding_assistant", "core.coding_assistant.core.tools.builtins", None),
    ("coding wrapper", "districts.coding.coding_tools", None),
    ("shadowbroker", "core.api.routers.sb", None),
    ("social_sim", "core.api.routers.simulation", None),
    ("hedgebot", "districts.investment.vector_hedgebot.orchestrator", None),
]


@pytest.mark.parametrize("name,module,attr", _ENTRY_POINTS, ids=[e[0] for e in _ENTRY_POINTS])
def test_vendored_tree_entry_point_imports(name, module, attr):
    mod = importlib.import_module(module)
    if attr:
        assert hasattr(mod, attr)


def test_research_engine_optional_features_fail_clearly_not_at_import():
    api = importlib.import_module("core.research_engine.api")
    for fn in ("get_news_feed", "research_news_item", "save_news_preferences", "get_news_categories"):
        assert callable(getattr(api, fn))
    from core.research_engine.api.client import LDRClient

    with pytest.raises(RuntimeError, match="not available in this build"):
        LDRClient().get_benchmarks()


def test_research_wrapper_builds_settings_and_returns_engine_result(monkeypatch):
    from districts.research import research_api

    fake = {"summary": "S", "findings": [], "sources": ["http://a"]}
    with patch("core.research_engine.api.research_functions.quick_summary", return_value=fake) as qs:
        out = research_api.quick_research("what is VECTOR", save_to_brain=False)
    assert out["summary"] == "S"
    assert qs.call_args.kwargs["settings_snapshot"]  # a real snapshot was built by the vendored engine
    assert "Research failed" not in out["summary"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
