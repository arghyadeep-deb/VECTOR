"""OD-43 regression coverage for governed channel-to-agent dispatch."""

from __future__ import annotations

import asyncio

import pytest

import core.city.a2a_bus as bus_mod
import core.city.agent_registry as registry_mod
from core.city.a2a_bus import A2ABus
from core.city.agent_base import AgentBase
from core.city.agent_registry import AgentRegistry
from vectorcode.src.gateway.run import GatewayRunner
from vectorcode.src.vc_agents.channel_agent import ChannelAgent, GovernedAgentInvoker


class _EchoAgent(AgentBase):
    def __init__(self, calls: list[dict]) -> None:
        super().__init__(agent_id="channel-echo", name="ChannelEcho", district="communications")
        self.capabilities = ["respond"]
        self._calls = calls

    async def run(self, task: dict) -> dict:
        self._calls.append(task)
        return {
            "status": "ok",
            "agent": self.name,
            "response": f"handled: {task['params']['query']}",
        }


@pytest.fixture
def governed_channel_world(isolated_vector_db):
    original_registry = registry_mod._registry_singleton
    original_bus = bus_mod._BUS
    registry = AgentRegistry()
    calls: list[dict] = []
    agent = _EchoAgent(calls)
    registry.register(agent)
    registry_mod._registry_singleton = registry
    bus_mod._BUS = A2ABus(registry=registry)
    try:
        yield agent, calls
    finally:
        registry_mod._registry_singleton = original_registry
        bus_mod._BUS = original_bus


@pytest.mark.asyncio
async def test_gateway_agent_command_invokes_named_agent_through_governed_dispatch(
    governed_channel_world,
) -> None:
    agent, calls = governed_channel_world
    initial_hp = agent.health_points
    runner = GatewayRunner.__new__(GatewayRunner)
    runner._channel_agent = ChannelAgent(None, GovernedAgentInvoker())

    response = await runner._handle_channel_agent_message(
        "/agent ChannelEcho respond explain the current status"
    )

    assert response == "handled: explain the current status"
    assert len(calls) == 1
    assert calls[0]["type"] == "respond"
    assert calls[0]["params"]["query"] == "explain the current status"
    assert calls[0]["_a2a_target"] == agent.id
    assert agent.health_points > initial_hp, "real Governor HP accounting must run"
    await runner._channel_agent.shutdown()


@pytest.mark.asyncio
async def test_gateway_agent_command_keeps_real_permission_gate(
    governed_channel_world,
) -> None:
    _agent, calls = governed_channel_world
    runner = GatewayRunner.__new__(GatewayRunner)
    runner._channel_agent = ChannelAgent(None, GovernedAgentInvoker())

    response = await runner._handle_channel_agent_message(
        "/agent ChannelEcho format_drive erase everything"
    )

    assert "FORBIDDEN" in response
    assert calls == [], "a forbidden channel request must never reach agent.run()"
    await runner._channel_agent.shutdown()


@pytest.mark.asyncio
async def test_channel_agent_owns_asyncio_tasks_and_drains_them() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class Agent:
        async def run(self, _content: str) -> str:
            started.set()
            await release.wait()
            return "done"

    agent = ChannelAgent(None, Agent())
    task = agent.submit_text("hello")
    await started.wait()

    assert isinstance(task, asyncio.Task)
    assert task in agent.pending_tasks
    release.set()
    await agent.shutdown()
    assert agent.pending_tasks == ()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
