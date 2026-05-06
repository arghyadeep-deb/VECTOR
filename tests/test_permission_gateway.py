import sys
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.loop.permission_gateway import PermissionGateway, Action


def make_action(action_type, params=None, proposed_by="test_agent"):
    return Action(action_type=action_type, params=params or {}, proposed_by=proposed_by)


@pytest.mark.asyncio
async def test_green_action_auto_executes():
    gw = PermissionGateway()
    result = await gw.execute(make_action("search_web", {"query": "test"}))
    assert result.approved is True
    assert result.level == "GREEN"
    assert result.executed is True


@pytest.mark.asyncio
async def test_forbidden_action_blocked():
    gw = PermissionGateway()
    result = await gw.execute(make_action("format_drive"))
    assert result.approved is False
    assert result.level == "FORBIDDEN"
    assert result.executed is False


@pytest.mark.asyncio
async def test_yellow_action_executes_with_notification():
    gw = PermissionGateway()
    result = await gw.execute(make_action("commit_code", {"msg": "test"}))
    assert result.level == "YELLOW"
    assert result.executed is True


@pytest.mark.asyncio
async def test_audit_log_grows():
    gw = PermissionGateway()
    await gw.execute(make_action("search_web", {"query": "q1"}))
    await gw.execute(make_action("search_web", {"query": "q2"}))
    log = gw.get_audit_log()
    assert len(log) == 2
    assert log[0]["action_type"] == "search_web"


@pytest.mark.asyncio
async def test_audit_log_capped_at_500():
    gw = PermissionGateway()
    for i in range(510):
        gw._write_audit(
            make_action("search_web", {"q": str(i)}),
            type("R", (), {"level": "GREEN", "approved": True, "executed": True, "reason": ""})()
        )
    assert len(gw.audit_log) == 500


@pytest.mark.asyncio
async def test_unknown_action_type_blocked():
    gw = PermissionGateway()
    result = await gw.execute(make_action("unknown_action_xyz"))
    assert result.level == "UNKNOWN"
    assert result.executed is False


def test_classify_all_permission_levels():
    gw = PermissionGateway()
    assert gw._classify("search_web") == "GREEN"
    assert gw._classify("commit_code") == "YELLOW"
    assert gw._classify("format_drive") == "FORBIDDEN"
    assert gw._classify("totally_unknown_xyz") == "UNKNOWN"


@pytest.mark.asyncio
async def test_red_action_times_out_without_confirmation():
    gw = PermissionGateway()
    # RED actions time out after 30s by default — override to 1s for test speed
    original = gw._wait_for_confirmation
    async def fast_timeout(action, timeout=1):
        return await original(action, timeout=1)
    gw._wait_for_confirmation = fast_timeout
    result = await gw.execute(make_action("send_email", {"to": "test@test.com"}))
    assert result.level == "RED"
    assert result.approved is False
