"""Regression tests for AdsOrchestratorAgent (Phase 3 whole-repo audit, 2026-10-01).

_ADS_SCRIPTS/_ADS_REFERENCES/_ADS_TEMPLATES chained 4 .parent hops from
ads_orchestrator_agent.py to a nonexistent core/ads/ directory ONE LEVEL
ABOVE the repo root -- the real files live at districts/marketing/ads/
{scripts,references,templates}/. Every _run_script() call therefore always
returned {"error": "Script not found: ..."}, and every _load_reference()/
_load_template() call always returned "" -- but every task_type branch that
used these still returned {"status": "ok"}, wrapping the error/empty result
as if it were a successful result. Zero prior test coverage existed for this
agent (confirmed via grep before writing this file).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.marketing.ads_orchestrator_agent import (
    AdsOrchestratorAgent,
    _ADS_SCRIPTS,
    _ADS_REFERENCES,
    _ADS_TEMPLATES,
)


def test_ads_paths_resolve_to_real_existing_directories():
    assert _ADS_SCRIPTS.exists(), f"_ADS_SCRIPTS does not exist: {_ADS_SCRIPTS}"
    assert _ADS_REFERENCES.exists(), f"_ADS_REFERENCES does not exist: {_ADS_REFERENCES}"
    assert _ADS_TEMPLATES.exists(), f"_ADS_TEMPLATES does not exist: {_ADS_TEMPLATES}"
    assert (_ADS_SCRIPTS / "fetch_page.py").exists()


def test_run_script_finds_a_real_script_instead_of_reporting_not_found():
    agent = AdsOrchestratorAgent()
    # fetch_page.py with no args exits 1 (argparse "required: url"), which is
    # a REAL script failure -- the point is it's found and executed at all,
    # not the stale "Script not found: fetch_page.py" phantom error.
    result = agent._run_script("fetch_page.py", [])
    assert result.get("error") != "Script not found: fetch_page.py", result


def test_load_reference_returns_real_content_not_empty_string():
    agent = AdsOrchestratorAgent()
    # At least one reference file must exist in the real references dir for
    # this to be meaningful; benchmarks.md is referenced directly in ads_math.
    any_ref = next(_ADS_REFERENCES.glob("*.md"), None)
    assert any_ref is not None, "no reference .md files found to test against"
    content = agent._load_reference(any_ref.stem)
    assert content != "", "reference load silently returned empty content"


@pytest.mark.asyncio
async def test_ads_landing_reports_error_status_when_script_fails():
    agent = AdsOrchestratorAgent()
    agent._run_script = lambda *a, **k: {"error": "Script not found: analyze_landing.py"}
    result = await agent.run({"type": "ads_landing", "params": {"url": "https://example.com"}})
    assert result["status"] == "error", (
        f"phantom success: script failed but status was {result['status']!r}"
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_ads_generate_reports_error_status_when_script_fails():
    agent = AdsOrchestratorAgent()
    agent._run_script = lambda *a, **k: {"error": "simulated failure"}
    result = await agent.run({"type": "ads_generate", "params": {"prompt": "a cat"}})
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_ads_photoshoot_reports_error_status_when_script_fails():
    agent = AdsOrchestratorAgent()
    agent._run_script = lambda *a, **k: {"error": "simulated failure"}
    result = await agent.run({"type": "ads_photoshoot", "params": {"product": "shoe"}})
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_ads_report_reports_error_status_when_script_fails():
    agent = AdsOrchestratorAgent()
    agent._run_script = lambda *a, **k: {"error": "simulated failure"}
    result = await agent.run({"type": "ads_report", "params": {"audit_markdown": "# audit"}})
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_ads_audit_memory_store_call_does_not_crash():
    """Separate from the _run_script path: ads_audit's own
    self._get_memory().store(...) call used metadata= (not a real store()
    kwarg) and omitted the required event_type -- always raised TypeError,
    always masked into {"status": "error"} by the bare except Exception.
    """
    agent = AdsOrchestratorAgent()

    async def _fake_llm_audit(platform, account_data):
        return {"platform": platform, "audit": "ok"}

    agent._llm_audit = _fake_llm_audit
    result = await agent.run({"type": "ads_audit", "params": {"platforms": ["google"]}})
    assert result["status"] == "ok", result


@pytest.mark.asyncio
async def test_ads_landing_still_reports_ok_on_genuine_success():
    agent = AdsOrchestratorAgent()
    agent._run_script = lambda *a, **k: {"output": "landing page analysis text"}
    result = await agent.run({"type": "ads_landing", "params": {"url": "https://example.com"}})
    assert result["status"] == "ok"
    assert "analysis" in result


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
