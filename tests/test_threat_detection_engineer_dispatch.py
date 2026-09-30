"""Regression test for a real, verified bug found during the 2026-09-30 Phase 3
codebase audit: districts/security/threat_detection_engineer.py::
ThreatDetectionEngineer.run()'s structured branches (sigma_rule/coverage_map/
analyze_logs) read technique_id/sources/log_lines straight off `task` instead
of `task["params"]` -- only the free-text fallback branch already checked
params correctly.

The real governor dispatch shape (core/city/governor.py dispatch() ->
`await agent.run(task)`, task = {"type": ..., "params": {...}}) always put
the caller's real arguments under `params`, so every real dispatch to these
3 capabilities silently fell back to the hardcoded defaults, ignoring the
caller's real request. Verified live before fixing:
    agent.run({"type": "sigma_rule", "params": {"technique_id": "T1003.001"}})
    -> returned the T1059.001 default instead
    agent.run({"type": "analyze_logs", "params": {"log_lines": [
        "powershell -enc SGVsbG8="]}})
    -> found 0 threats in an obviously malicious log line
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.security.threat_detection_engineer import ThreatDetectionEngineer


@pytest.mark.asyncio
async def test_sigma_rule_reads_real_governor_dispatch_shape():
    agent = ThreatDetectionEngineer()
    result = await agent.run({
        "type": "sigma_rule",
        "params": {"technique_id": "T1003.001", "description": "custom LSASS dump rule"},
    })
    assert result["status"] == "ok"
    assert result["technique_id"] == "T1003.001"
    assert "T1003.001" in result["sigma_rule"]


@pytest.mark.asyncio
async def test_coverage_map_reads_real_governor_dispatch_shape():
    agent = ThreatDetectionEngineer()
    result = await agent.run({
        "type": "coverage_map",
        "params": {"sources": ["auth_log"]},
    })
    assert result["status"] == "ok"
    # Must reflect the real supplied source, not silently fall back to the
    # ["windows_event", "process_creation"] hardcoded default.
    assert result["monitored_sources"] == ["auth_log"]


@pytest.mark.asyncio
async def test_analyze_logs_reads_real_governor_dispatch_shape():
    agent = ThreatDetectionEngineer()
    result = await agent.run({
        "type": "analyze_logs",
        "params": {"log_lines": ["powershell -enc SGVsbG8=", "a normal boring log line"]},
    })
    assert result["status"] == "ok"
    assert result["finding_count"] == 1


@pytest.mark.asyncio
async def test_flat_legacy_shape_still_works_for_backward_compat():
    """The file's own __main__ smoke test uses this flat (no "params" key)
    shape for sigma_rule -- must keep working exactly as before the fix."""
    agent = ThreatDetectionEngineer()
    result = await agent.run({"type": "sigma_rule", "technique_id": "T1078"})
    assert result["status"] == "ok"
    assert result["technique_id"] == "T1078"


@pytest.mark.asyncio
async def test_query_fallback_still_reads_params_correctly():
    """The pre-existing free-text fallback branch (already correct before
    this fix) must be unaffected by the new `params` variable it now shares."""
    agent = ThreatDetectionEngineer()
    result = await agent.run({
        "type": "what_is_a_sigma_rule",
        "params": {"query": "What's the difference between a Sigma rule and a YARA rule?"},
    })
    assert result["status"] == "ok"
    assert "agent" not in result  # must not be the static status-dump shape


@pytest.mark.asyncio
async def test_nested_params_alias_keys_are_honored():
    """Regression for a real bug Codex's independent review caught in the
    first version of this fix (2026-09-30, same cycle): each key's
    flat-shape ALIAS (e.g. "technique" for "technique_id") was preserved
    only at the top-level `task` fallback, never checked nested inside
    `params` itself -- so a real governor-shaped call using the alias
    under params (e.g. {"type": "sigma_rule", "params": {"technique":
    "T1003.001"}}) silently fell through to the hardcoded default.
    """
    agent = ThreatDetectionEngineer()

    r1 = await agent.run({"type": "sigma_rule", "params": {"technique": "T1003.001"}})
    assert r1["technique_id"] == "T1003.001"

    r2 = await agent.run({"type": "coverage_map", "params": {"log_sources": ["aws_cloudtrail"]}})
    assert r2["monitored_sources"] == ["aws_cloudtrail"]

    r3 = await agent.run({"type": "analyze_logs", "params": {"lines": "powershell -enc SGVsbG8="}})
    assert r3["finding_count"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
