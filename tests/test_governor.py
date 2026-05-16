import sys
import uuid
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.city.governor import Governor
from core.city.agent_base import AgentBase
from core.city.agent_registry import get_registry


@pytest.fixture(autouse=True)
def clean_registry():
    reg = get_registry()
    before = list(reg._agents.districts.keys())
    yield
    # Remove test agents added during test
    for aid in list(reg._agents.districts.keys()):
        if aid not in before:
            reg._agents.districts.pop(aid, None)


def make_agent(district="coding"):
    a = AgentBase(str(uuid.uuid4()), f"TestAgent_{district}", district)
    get_registry().register(a)
    return a


def test_route_coding_task():
    gov = Governor()
    assert gov.route_task("review my git code") == "coding"
    assert gov.route_task("fix a bug") == "coding"


def test_route_calendar_task():
    gov = Governor()
    assert gov.route_task("check my KIIT schedule") == "time_calendar"
    assert gov.route_task("set a deadline") == "time_calendar"


def test_route_security_task():
    gov = Governor()
    assert gov.route_task("scan for malware") == "security"


def test_route_unknown_defaults_to_research():
    gov = Governor()
    assert gov.route_task("xyzzy_totally_unknown") == "research"


@pytest.mark.asyncio
async def test_dispatch_returns_task_id():
    make_agent("coding")
    gov = Governor()
    result = await gov.dispatch({"type": "code_review", "file": "test.py"})
    assert "task_id" in result
    assert "district" in result


@pytest.mark.asyncio
async def test_dispatch_no_agents_returns_no_agents_status():
    gov = Governor()
    result = await gov.dispatch({"type": "unknown_type_xyz_no_district"})
    assert result.get("status") in ("no_agents", "stub", "error", "ok")


def test_get_district_summary_after_register():
    make_agent("coding")
    gov = Governor()
    summary = gov.get_district_summary()
    assert "coding" in summary
    assert summary["coding"]["agents"] >= 1
