"""VECTOR OAuth Integration Registry — 118+ integrations, cloud-ready."""
from core.openhuman.oauth.registry import OAuthRegistry, Integration, get_integration, list_integrations
from core.openhuman.oauth.flows import OAuthFlowManager
__all__ = ["OAuthRegistry", "Integration", "get_integration", "list_integrations", "OAuthFlowManager"]
