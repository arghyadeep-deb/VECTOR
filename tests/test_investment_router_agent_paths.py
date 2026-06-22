"""Regression test for a real bug found during the 2026-06-21 manifest-gap
audit: core/api/routers/investment.py's `/analyze`, `/dcf`, `/alpha`,
`/backtest`, `/geopolitics` endpoints all resolved FinAgentAgent via the
module path "districts.investment.vector_finagent_agent" — which has never
existed (the real file is districts/investment/finagent_agent.py, no
"vector_" prefix). `_get_agent()` swallows the resulting ImportError and
returns None, so every one of those 5 endpoints has been silently
returning HTTP 503 "FinAgentAgent unavailable" regardless of how
finagent_agent.py itself was doing. Caught only by actually calling
_get_agent() with the literal string each route uses, not by reading the
code (it parses fine, the typo is in a runtime-only string)."""
import re
from pathlib import Path

import pytest


@pytest.fixture
def investment_router(monkeypatch, tmp_path):
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "investment_router_paths.db"))
    from core.api.routers import investment

    investment._agent_cache.clear()
    return investment


def test_finagent_agent_module_path_resolves(investment_router):
    agent = investment_router._get_agent("districts.investment.finagent_agent.FinAgentAgent")
    assert agent is not None, "FinAgentAgent must be importable at this path"


def test_no_get_agent_call_site_references_a_nonexistent_module(investment_router):
    """Belt-and-suspenders: parse every _get_agent("...") literal out of the
    router source and confirm each one actually imports, so a future typo
    in any of the 10 call sites (not just the 5 that broke) fails CI
    instead of degrading silently to a 503 at request time."""
    src = Path("core/api/routers/investment.py").read_text(encoding="utf-8")
    paths = set(re.findall(r'_get_agent\("([\w\.]+)"\)', src))
    assert paths, "expected at least one _get_agent(...) call site in investment.py"
    for path in paths:
        agent = investment_router._get_agent(path)
        assert agent is not None, f"_get_agent({path!r}) returned None — module/class path is broken"


if __name__ == "__main__":
    test_finagent_agent_module_path_resolves()
    test_no_get_agent_call_site_references_a_nonexistent_module()
    print("[OK] test_investment_router_agent_paths")
