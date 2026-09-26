"""Exploration routing (weaker agents get GREEN work) and verified-only collaboration credit."""
from __future__ import annotations

import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import core.city.a2a_bus as bus_mod
import core.city.agent_registry as registry_mod
from core.city import experience as xp
from core.city.a2a_bus import A2ABus
from core.city.agent_base import AgentBase
from core.city.agent_registry import AgentRegistry
from core.city.governor import Governor


class Echo(AgentBase):
    async def run(self, task):
        return {"status": "ok", "agent": self.name, "answer": 42}


@pytest.fixture
def world(isolated_vector_db, monkeypatch):
    for v in ("VECTOR_EXPLORE", "VECTOR_EXPLORE_SHARE"):
        monkeypatch.delenv(v, raising=False)
    xp._reset_for_tests()
    original = registry_mod._registry_singleton
    reg = AgentRegistry()
    registry_mod._registry_singleton = reg
    bus = A2ABus(registry=reg)
    old, bus_mod._BUS = bus_mod._BUS, bus

    def add(name, hp, district="d"):
        a = Echo(agent_id=f"id-{name}", name=name, district=district)
        a.health_points = hp
        reg.register(a)
        return a

    yield SimpleNamespace(reg=reg, bus=bus, add=add)
    registry_mod._registry_singleton = original
    bus_mod._BUS = old
    xp._reset_for_tests()


def collab_xp(agent) -> float:
    """XP from collaboration rows only (the Governor also records the unverified work itself; that is not what is under test)."""
    xp._ensure()
    return float(xp._conn().execute("SELECT COALESCE(SUM(xp),0) FROM agent_experience WHERE lineage=? AND task_type LIKE 'collab:%'",
                                    (xp.lineage_key(agent),)).fetchone()[0])


def picks(gov, capable, tier="GREEN", n=400):
    return [gov._pick_capable(capable, "respond", tier).name for _ in range(n)]


# ── exploration ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_by_default_the_top_hp_agent_always_wins(world):
    a, b, c = world.add("Top", 900), world.add("Mid", 500), world.add("Low", 300)
    assert set(picks(Governor(), [a, b, c])) == {"Top"}


def test_with_exploration_on_a_share_goes_to_less_tried_agents_never_to_the_dead_or_for_non_green(world, monkeypatch):
    monkeypatch.setenv("VECTOR_EXPLORE", "1")
    monkeypatch.setenv("VECTOR_EXPLORE_SHARE", "0.3")
    top, mid, low, dead = world.add("Top", 900), world.add("Mid", 500), world.add("Low", 300), world.add("Dead", 0)
    for _ in range(30):
        xp.record(mid, "t", "success")                     # Mid has plenty of history; Low has none
    gov = Governor()
    gov._explore_rng = random.Random(7)
    chosen = picks(gov, [top, mid, low, dead])
    share = 1 - chosen.count("Top") / len(chosen)
    assert 0.2 < share < 0.4, f"about 30% explored, got {share:.2f}"
    assert "Dead" not in chosen
    assert chosen.count("Low") > chosen.count("Mid"), "the agent with the fewest attempts is favoured"
    for tier in ("YELLOW", "RED", "UNKNOWN"):
        assert set(picks(gov, [top, mid, low], tier=tier, n=100)) == {"Top"}, f"{tier} work always goes to the best agent"


def test_exploration_never_picks_an_agent_outside_the_capable_list(world, monkeypatch):
    monkeypatch.setenv("VECTOR_EXPLORE", "1")
    monkeypatch.setenv("VECTOR_EXPLORE_SHARE", "0.5")
    a, b = world.add("A", 900), world.add("B", 100)
    outsider = world.add("Outsider", 500)
    gov = Governor()
    gov._explore_rng = random.Random(1)
    assert set(picks(gov, [a, b])) <= {"A", "B"} and outsider.name not in picks(gov, [a, b])


# ── collaboration credit ────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_only_an_answer_the_asker_verifies_earns_the_helper_xp(world):
    helper, asker = world.add("Helper", 500, "da"), world.add("Asker", 500, "db")
    no_check = await asker.a2a_ask("respond", {}, to="Helper")
    assert no_check.ok and xp.skill_table(helper).get("collab:respond") is None
    failed_check = await asker.a2a_ask("respond", {}, to="Helper", verify=lambda r: r.get("answer") == 41)
    assert xp.skill_table(helper).get("collab:respond") is None, "a rejected answer earns nothing"
    good = await asker.a2a_ask("respond", {}, to="Helper", verify=lambda r: r.get("answer") == 42)
    row = xp.skill_table(helper)["collab:respond"]
    assert good.ok and row["success"] == 1 and row["verified"] == 1
    assert collab_xp(helper) == pytest.approx(10 * 0.5 * 0.5, abs=0.01), "10 base x difficulty 0.5 x collab weight 0.5"


@pytest.mark.asyncio
async def test_trading_requests_back_and_forth_cannot_farm_credit(world, monkeypatch):
    monkeypatch.setitem(bus_mod._DEFAULTS, "rate_per_minute", 1000)
    monkeypatch.setitem(bus_mod._DEFAULTS, "max_messages_per_conversation", 1000)
    a, b = world.add("A", 500, "da"), world.add("B", 500, "db")
    for _ in range(10):
        await a.a2a_ask("respond", {}, to="B", verify=lambda r: True)
        await b.a2a_ask("respond", {}, to="A", verify=lambda r: True)
    for who in (a, b):
        assert xp.skill_table(who)["collab:respond"]["success"] == A2ABus._COLLAB_DAILY_CAP
    assert collab_xp(a) < 5.8, "3 capped credits, each worth less than the last (novelty): 2.5 + 1.77 + 1.44"
