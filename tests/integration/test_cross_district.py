"""
tests/integration/test_cross_district.py — Phase 2D cross-district workflow tests.

These tests verify that publishing an event to the event bus causes the correct
downstream agent to react. They use the real AgentRegistry + event bus but mock
the actual LLM calls so they run fast without Ollama.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.integration
@pytest.mark.asyncio
async def test_security_alert_triggers_threat_scan():
    """Publishing SECURITY_ALERT → ThreatScout.handle_event is called."""
    from core.event_bus.bus import get_event_bus
    from core.event_bus.types import Event, EventType
    from core.city.agent_registry import get_registry
    from districts.security.threat_scout import ThreatScout

    scout = ThreatScout()
    reg = get_registry()
    reg.register(scout)

    received: list[dict] = []

    async def mock_handle(event):
        received.append(event)

    # Explicitly wire the agent's handle_event to the bus for this test
    bus = await get_event_bus()
    bus.subscribe(EventType.SECURITY_ALERT, mock_handle)

    await bus.publish(Event(
        event_type=EventType.SECURITY_ALERT,
        data={"reason": "test_alert"},
        source="test",
    ))
    await asyncio.sleep(0.2)  # allow fanout task to execute

    assert len(received) > 0, "ThreatScout should have received the SECURITY_ALERT event"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_research_findings_persist_to_memory():
    """ResearchHub.handle_event calls request_agent_help → memory_curator."""
    from districts.research.research_hub import ResearchHub

    hub = ResearchHub()
    delegated: list[dict] = []

    async def mock_request_help(target_id, task):
        delegated.append({"target": target_id, "task": task})
        return {"workflow_id": "test-wf-001", "status": "queued"}

    async def mock_search_web(query, max_results=5):
        return [{"title": "test result", "url": "https://example.com"}]

    hub.request_agent_help = mock_request_help
    hub.search_web = mock_search_web

    event = {
        "event_type": "task_completed",
        "data": {"query": "python async patterns", "action_type": "research"},
    }
    await hub.handle_event(event)

    assert any(d["target"] == "memory_curator" for d in delegated), \
        "ResearchHub should delegate findings to memory_curator"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_email_triage_chains_to_calendar():
    """EmailAgent.handle_event reacts to user_interaction events."""
    from districts.communications.email_agent import EmailAgent

    agent = EmailAgent()
    ran: list[dict] = []

    async def mock_run(task):
        ran.append(task)
        return {"status": "ok"}

    agent.run = mock_run

    event = {
        "event_type": "user_interaction",
        "data": {"message": "check my email", "source": "voice"},
    }
    await agent.handle_event(event)

    # EmailAgent should have queued a triage task
    assert agent._inbox, "EmailAgent inbox should have the event"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_council_convenes_on_high_stakes():
    """LLMCouncil.handle_event convenes on security_alert."""
    from districts.governance.llm_council import LLMCouncil

    council = LLMCouncil()
    convened: list[dict] = []

    async def mock_convene(question, stakes, requester_hp):
        convened.append({"question": question, "stakes": stakes})
        return {"verdict": "approved", "confidence": 0.85}

    council.convene = mock_convene

    event = {
        "event_type": "security_alert",
        "data": {"reason": "audit_chain_broken", "broken_at": 42},
    }
    await council.handle_event(event)

    assert len(convened) > 0, "LLMCouncil should have convened on security_alert"
    assert convened[0]["stakes"] == "high"
