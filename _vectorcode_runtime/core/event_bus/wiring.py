from loguru import logger

__all__ = [
    "auto_subscribe_all",
    "get_downstream_tasks",
    "get_publish_event",
    "get_subscriptions_for",
]

from core.event_bus.types import EventType


DISTRICT_SUBSCRIPTIONS: dict[str, set[EventType]] = {
    "coding": {
        EventType.DESIGN_COMPLETE,
        EventType.RESEARCH_COMPLETE,
        EventType.CONTENT_READY,
    },
    "engineering": {
        EventType.DESIGN_COMPLETE,
        EventType.RESEARCH_COMPLETE,
    },
    "qa": {
        EventType.CODING_COMPLETE,
        EventType.CONTENT_READY,
    },
    "testing": {
        EventType.CODING_COMPLETE,
    },
    "documentation": {
        EventType.CODING_COMPLETE,
        EventType.RESEARCH_COMPLETE,
    },
    "content": {
        EventType.RESEARCH_COMPLETE,
        EventType.DESIGN_COMPLETE,
        EventType.ANALYTICS_READY,
    },
    "marketing": {
        EventType.CONTENT_READY,
        EventType.CONTENT_REVIEWED,
        EventType.ANALYTICS_READY,
    },
    "emergency": {
        EventType.SECURITY_ALERT,
        EventType.HEALTH_ALERT,
        EventType.SYSTEM_ERROR,
    },
    "security": {
        EventType.EMERGENCY_SIGNAL,
        EventType.SYSTEM_ERROR,
    },
    "health": {
        EventType.EMERGENCY_SIGNAL,
        EventType.HEALTH_ALERT,
    },
    "governance": {
        EventType.SECURITY_ALERT,
        EventType.EMERGENCY_SIGNAL,
        EventType.SYSTEM_ERROR,
    },
    "investment": {
        EventType.RESEARCH_COMPLETE,
        EventType.ANALYTICS_READY,
    },
    "intelligence": {
        EventType.RESEARCH_COMPLETE,
        EventType.MARKETING_PUBLISHED,
        EventType.ANALYTICS_READY,
    },
    "strategy": {
        EventType.ANALYTICS_READY,
        EventType.RESEARCH_COMPLETE,
    },
    "reflection": {
        EventType.TASK_COMPLETED,
        EventType.EMERGENCY_SIGNAL,
    },
    "predictive_analytics": {
        EventType.RESEARCH_COMPLETE,
        EventType.HEALTH_ALERT,
    },
    "data_analytics": {
        EventType.MARKETING_PUBLISHED,
    },
    "projects": {
        EventType.DESIGN_COMPLETE,
        EventType.CODING_COMPLETE,
    },
    "product": {
        EventType.DESIGN_COMPLETE,
        EventType.CODING_COMPLETE,
        EventType.RESEARCH_COMPLETE,
    },
}


PUBLISH_EVENTS: dict[str, EventType] = {
    "content": EventType.CONTENT_READY,
    "coding": EventType.CODING_COMPLETE,
    "design": EventType.DESIGN_COMPLETE,
    "research": EventType.RESEARCH_COMPLETE,
    "security": EventType.SECURITY_ALERT,
    "emergency": EventType.EMERGENCY_SIGNAL,
    "health": EventType.HEALTH_ALERT,
    "marketing": EventType.MARKETING_PUBLISHED,
    "qa": EventType.CONTENT_REVIEWED,
    "data_analytics": EventType.ANALYTICS_READY,
    "predictive_analytics": EventType.ANALYTICS_READY,
}


EVENT_TRIGGER_MAP: dict[EventType, list[tuple[str, str, dict]]] = {
    EventType.DESIGN_COMPLETE: [
        ("coding", "implement_design", {"source_event": "{event_type}"}),
        ("content", "plan_content_from_design", {"source_event": "{event_type}"}),
    ],
    EventType.CONTENT_READY: [
        ("marketing", "distribute_content", {"content_source": "{event_type}"}),
        ("qa", "review_content", {"content_source": "{event_type}"}),
    ],
    EventType.CODING_COMPLETE: [
        ("qa", "test_feature", {"code_source": "{event_type}"}),
        ("documentation", "document_feature", {"code_source": "{event_type}"}),
    ],
    EventType.CONTENT_REVIEWED: [
        ("content", "update_content_from_review", {"review_source": "{event_type}"}),
    ],
    EventType.RESEARCH_COMPLETE: [
        ("content", "create_content_from_research", {"research_source": "{event_type}"}),
        ("intelligence", "analyze_research_findings", {"research_source": "{event_type}"}),
        ("investment", "evaluate_research_opportunities", {"research_source": "{event_type}"}),
    ],
    EventType.SECURITY_ALERT: [
        ("emergency", "respond_to_security_threat", {"alert_source": "{event_type}"}),
        ("governance", "review_security_incident", {"alert_source": "{event_type}"}),
    ],
    EventType.EMERGENCY_SIGNAL: [
        ("health", "check_user_safety", {"emergency_source": "{event_type}"}),
        ("security", "lockdown_systems", {"emergency_source": "{event_type}"}),
    ],
    EventType.HEALTH_ALERT: [
        ("emergency", "assess_health_crisis", {"alert_source": "{event_type}"}),
        ("predictive_analytics", "update_health_forecast", {"alert_source": "{event_type}"}),
    ],
    EventType.MARKETING_PUBLISHED: [
        ("intelligence", "track_campaign_performance", {"campaign_source": "{event_type}"}),
        ("data_analytics", "analyze_campaign_metrics", {"campaign_source": "{event_type}"}),
    ],
    EventType.ANALYTICS_READY: [
        # Task 89B: ("strategy", "review_analytics_insights", ...) retired
        # 2026-09-08 — verified zero registered agents for the "strategy"
        # district (no `strategy:` key in config/agent_manifest.yaml, and
        # AgentRegistry.get_by_district() does exact-string match, so no
        # baseline agent is ever created for it either). Every dispatch to
        # this edge logged "no agents in strategy" and wasted a fan-out slot
        # with zero possible effect. See VECTOR_TECHNICAL_KNOWLEDGE/89B_EVENT_FANOUT.md.
        ("content", "optimize_from_analytics", {"analytics_source": "{event_type}"}),
        ("marketing", "adjust_campaign_from_analytics", {"analytics_source": "{event_type}"}),
    ],
    EventType.SYSTEM_ERROR: [
        ("emergency", "diagnose_system_error", {"error_source": "{event_type}"}),
        ("security", "investigate_error_source", {"error_source": "{event_type}"}),
    ],
}


def _match_district(district: str, pattern: str) -> bool:
    d = district.lower().replace("_", "").replace("-", "")
    p = pattern.lower().replace("_", "").replace("-", "")
    return p in d or d in p


def get_subscriptions_for(district: str) -> set[EventType]:
    result: set[EventType] = set()
    for pattern, events in DISTRICT_SUBSCRIPTIONS.items():
        if _match_district(district, pattern):
            result.update(events)
    return result


def get_publish_event(district: str) -> EventType | None:
    for pattern, event in PUBLISH_EVENTS.items():
        if _match_district(district, pattern):
            return event
    return None


def get_downstream_tasks(event_type: EventType) -> list[tuple[str, str, dict]]:
    return EVENT_TRIGGER_MAP.get(event_type, [])


def auto_subscribe_all() -> int:
    from core.city.agent_registry import get_registry
    registry = get_registry()
    count = 0
    for agent in registry.get_all_agents():
        events = get_subscriptions_for(agent.district)
        for et in events:
            agent.subscribe_to(et.value)
            count += 1
    if count:
        logger.info("[VECTOR][event_wiring] auto-subscribed {} agent-event pairs", count)
    return count

