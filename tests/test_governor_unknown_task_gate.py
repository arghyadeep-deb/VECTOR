"""Governor.dispatch() must not run an unclassified task type just because the caller named a district.

Finding 2026-09-24 (self-review, left open pending an independent review): a caller-supplied `district` was trusted for
ANY task_type, including agent-internal names that were never in DISTRICT_TASK_MAP and never in a permission tier
(e.g. "cleanup_logs" / "backup_db", real DevOpsAutomator methods that delete files / copy the database).
`Governor().dispatch({"type": "cleanup_logs", "district": "ops"})` reached `DevOpsAutomator.cleanup_logs()` with no
receipt. UNKNOWN is deliberately not blocked by the tier check (a few hundred agent-declared capability labels are
untiered), so the closure has two parts, both covered here:

  1. consequential agent-declared names are tiered (cleanup_logs RED, backup_db YELLOW, delete/publish/upload RED, ...);
  2. an UNKNOWN name that is neither a routing key nor a capability some registered agent declares is refused outright,
     whatever district the caller names.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.city.agent_registry import AgentRegistry
from core.city.governor import Governor
from core.loop.permission_gateway import PermissionGateway


@pytest.fixture()
def registry(monkeypatch):
    """A real registry with one real ops agent, swapped in for the module singleton."""
    from core.city import agent_registry as reg_mod
    from districts.ops.devops_automator import DevOpsAutomator

    reg = AgentRegistry()
    agent = DevOpsAutomator()
    # The real agent would delete logs / call Cloudflare; these tests are about whether dispatch REACHES it.
    agent.run = AsyncMock(return_value={"status": "ok", "agent": "stub"})
    reg.register(agent)
    reg.stub_agent = agent
    monkeypatch.setattr(reg_mod, "_registry", reg, raising=False)
    monkeypatch.setattr(reg_mod, "get_registry", lambda: reg)
    return reg


def _governor(reg):
    g = Governor()
    g._registry = reg
    g._get_registry = lambda: reg
    return g


@pytest.mark.parametrize("name,tier", [
    ("cleanup_logs", "RED"), ("backup_db", "YELLOW"), ("cf_status", "GREEN"),
    ("delete", "RED"), ("publish", "RED"), ("upload", "RED"), ("prune", "RED"),
    ("write", "YELLOW"), ("generate", "YELLOW"), ("create", "YELLOW"), ("create_branch", "YELLOW"),
    ("update_draft", "YELLOW"), ("generate_tests", "YELLOW"), ("merge", "YELLOW"),
    ("scan_bugs", "GREEN"), ("scan_codebase", "GREEN"),
])
def test_consequential_agent_declared_names_are_tiered(name, tier):
    assert PermissionGateway()._classify(name) == tier


@pytest.mark.asyncio
async def test_cleanup_logs_with_a_named_district_is_refused_without_a_receipt(registry):
    result = await _governor(registry).dispatch({"type": "cleanup_logs", "district": "ops", "params": {}})
    assert result["status"] == "blocked", result


@pytest.mark.asyncio
async def test_an_undeclared_unclassified_name_is_refused_even_with_a_district(registry):
    result = await _governor(registry).dispatch({"type": "wipe_the_disk_now", "district": "ops", "params": {}})
    assert result["status"] == "blocked", result
    assert "not a known" in result["reason"]


@pytest.mark.asyncio
async def test_a_declared_but_untiered_label_still_dispatches(registry):
    """'ops' is a capability label DevOpsAutomator declares; it is not in any tier and must keep working."""
    assert PermissionGateway()._classify("ops") == "UNKNOWN"
    result = await _governor(registry).dispatch({"type": "ops", "district": "ops", "params": {}})
    assert result["status"] != "blocked", result


@pytest.mark.asyncio
async def test_a_classified_green_task_with_an_explicit_district_is_unaffected(registry):
    result = await _governor(registry).dispatch({"type": "cf_status", "district": "ops", "params": {}})
    assert result.get("status") != "blocked", result


@pytest.mark.asyncio
async def test_blocked_dispatch_never_reaches_the_agent(registry):
    await _governor(registry).dispatch({"type": "cleanup_logs", "district": "ops", "params": {}})
    await _governor(registry).dispatch({"type": "wipe_the_disk_now", "district": "ops", "params": {}})
    assert registry.stub_agent.run.await_count == 0
