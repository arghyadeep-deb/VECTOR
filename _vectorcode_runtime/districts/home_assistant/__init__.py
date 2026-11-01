"""Home Assistant district — smart home integration via REST + WebSocket."""

from districts.home_assistant.connector import HAConfig, HARestClient, HAWebSocketClient, HAConnector
from districts.home_assistant.entity_manager import HAEntity, EntityRegistry, EntityCache, EntityMatcher, EntityManager
from districts.home_assistant.voice_bridge import VoiceCommand, IntentMapper, EntityResolver, ConfirmDialog, VoiceBridge
from districts.home_assistant.automation_engine import AutomationRule, SceneManager, AutomationEngine

__all__ = [
    "HAConfig",
    "HARestClient",
    "HAWebSocketClient",
    "HAConnector",
    "HAEntity",
    "EntityRegistry",
    "EntityCache",
    "EntityMatcher",
    "EntityManager",
    "VoiceCommand",
    "IntentMapper",
    "EntityResolver",
    "ConfirmDialog",
    "VoiceBridge",
    "AutomationRule",
    "SceneManager",
    "AutomationEngine",
]
