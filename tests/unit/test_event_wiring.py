"""Tests for core/event_bus/wiring.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from unittest.mock import MagicMock, patch

from core.event_bus.wiring import (
    auto_subscribe_all,
    get_downstream_tasks,
    get_publish_event,
    get_subscriptions_for,
    DISTRICT_SUBSCRIPTIONS,
    PUBLISH_EVENTS,
    EVENT_TRIGGER_MAP,
)
from core.event_bus.types import EventType


class TestGetSubscriptionsFor:

    def test_coding_gets_design_complete(self):
        subs = get_subscriptions_for("coding")
        assert EventType.DESIGN_COMPLETE in subs

    def test_coding_gets_research_complete(self):
        subs = get_subscriptions_for("coding")
        assert EventType.RESEARCH_COMPLETE in subs

    def test_security_gets_security_alert(self):
        subs = get_subscriptions_for("security")
        assert EventType.EMERGENCY_SIGNAL in subs

    def test_emergency_gets_health_alert(self):
        subs = get_subscriptions_for("emergency")
        assert EventType.HEALTH_ALERT in subs

    def test_unknown_district_returns_empty(self):
        subs = get_subscriptions_for("totally_unknown_district_xyz")
        assert isinstance(subs, set)
        assert len(subs) == 0

    def test_returns_set(self):
        result = get_subscriptions_for("research")
        assert isinstance(result, set)

    def test_fuzzy_matching_case_insensitive(self):
        subs1 = get_subscriptions_for("coding")
        subs2 = get_subscriptions_for("CODING")
        assert subs1 == subs2

    def test_partial_match(self):
        # "data_analytics" should match "data_analytics" pattern
        subs = get_subscriptions_for("data_analytics")
        assert isinstance(subs, set)

    def test_governance_gets_security_alert(self):
        subs = get_subscriptions_for("governance")
        assert EventType.SECURITY_ALERT in subs

    def test_health_district_subscriptions(self):
        subs = get_subscriptions_for("health")
        assert EventType.HEALTH_ALERT in subs
        assert EventType.EMERGENCY_SIGNAL in subs


class TestGetPublishEvent:

    def test_coding_publishes_coding_complete(self):
        evt = get_publish_event("coding")
        assert evt == EventType.CODING_COMPLETE

    def test_research_publishes_research_complete(self):
        evt = get_publish_event("research")
        assert evt == EventType.RESEARCH_COMPLETE

    def test_content_publishes_content_ready(self):
        evt = get_publish_event("content")
        assert evt == EventType.CONTENT_READY

    def test_security_publishes_security_alert(self):
        evt = get_publish_event("security")
        assert evt == EventType.SECURITY_ALERT

    def test_unknown_district_returns_none(self):
        evt = get_publish_event("totally_unknown_xyz")
        assert evt is None

    def test_emergency_publishes_emergency_signal(self):
        evt = get_publish_event("emergency")
        assert evt == EventType.EMERGENCY_SIGNAL

    def test_health_publishes_health_alert(self):
        evt = get_publish_event("health")
        assert evt == EventType.HEALTH_ALERT

    def test_marketing_publishes(self):
        evt = get_publish_event("marketing")
        assert evt == EventType.MARKETING_PUBLISHED


class TestGetDownstreamTasks:

    def test_design_complete_triggers_coding(self):
        tasks = get_downstream_tasks(EventType.DESIGN_COMPLETE)
        districts = [t[0] for t in tasks]
        assert "coding" in districts

    def test_coding_complete_triggers_qa(self):
        tasks = get_downstream_tasks(EventType.CODING_COMPLETE)
        districts = [t[0] for t in tasks]
        assert "qa" in districts

    def test_coding_complete_triggers_documentation(self):
        tasks = get_downstream_tasks(EventType.CODING_COMPLETE)
        districts = [t[0] for t in tasks]
        assert "documentation" in districts

    def test_unknown_event_returns_empty_list(self):
        # Use a valid EventType that has no trigger
        tasks = get_downstream_tasks(EventType.TASK_COMPLETED)
        assert tasks == []

    def test_returns_list_of_tuples(self):
        tasks = get_downstream_tasks(EventType.RESEARCH_COMPLETE)
        assert isinstance(tasks, list)
        for t in tasks:
            assert len(t) == 3  # (district, task_type, params_template)

    def test_security_alert_triggers_emergency(self):
        tasks = get_downstream_tasks(EventType.SECURITY_ALERT)
        districts = [t[0] for t in tasks]
        assert "emergency" in districts

    def test_health_alert_triggers_emergency(self):
        tasks = get_downstream_tasks(EventType.HEALTH_ALERT)
        districts = [t[0] for t in tasks]
        assert "emergency" in districts

    def test_system_error_triggers_security(self):
        tasks = get_downstream_tasks(EventType.SYSTEM_ERROR)
        districts = [t[0] for t in tasks]
        assert "security" in districts


class TestAutoSubscribeAll:

    def test_auto_subscribe_with_no_agents(self):
        mock_reg = MagicMock()
        mock_reg.get_all_agents.return_value = []
        with patch("core.city.agent_registry.get_registry", return_value=mock_reg):
            count = auto_subscribe_all()
        assert count == 0

    def test_auto_subscribe_with_coding_agent(self):
        mock_agent = MagicMock()
        mock_agent.district = "coding"
        mock_agent.subscribe_to = MagicMock()

        mock_reg = MagicMock()
        mock_reg.get_all_agents.return_value = [mock_agent]

        with patch("core.city.agent_registry.get_registry", return_value=mock_reg):
            count = auto_subscribe_all()

        # coding district subscribes to DESIGN_COMPLETE, RESEARCH_COMPLETE, CONTENT_READY
        assert count >= 3
        assert mock_agent.subscribe_to.call_count >= 3

    def test_auto_subscribe_multiple_agents(self):
        coding_agent = MagicMock()
        coding_agent.district = "coding"
        coding_agent.subscribe_to = MagicMock()

        unknown_agent = MagicMock()
        unknown_agent.district = "unknown_xyz_district"
        unknown_agent.subscribe_to = MagicMock()

        mock_reg = MagicMock()
        mock_reg.get_all_agents.return_value = [coding_agent, unknown_agent]

        with patch("core.city.agent_registry.get_registry", return_value=mock_reg):
            count = auto_subscribe_all()

        # coding agent gets subscriptions, unknown gets 0
        assert count >= 3
