"""
VECTOR OAuth System — self-hosted proxy, 20 provider configs, 119-integration registry.

Quick start:
  # Start OAuth server (handles authorize/callback/refresh)
  python -m core.engine.oauth.server

  # Add to existing FastAPI app
  from core.engine.oauth.server import oauth_router
  app.include_router(oauth_router, prefix="/oauth")

  # Check if GitHub is connected
  from core.engine.oauth import OAuthFlowManager
  mgr = OAuthFlowManager()
  logger.info(mgr.is_connected("github"))


  # Route to authorization page
  # GET http://localhost:7788/oauth/authorize/github
"""
from core.engine.oauth.registry import OAuthRegistry, Integration, get_integration, list_integrations
from core.engine.oauth.flows import OAuthFlowManager, OAuthToken
from core.engine.oauth.providers import get_provider, PROVIDERS, configured_providers

__all__ = [
    "OAuthRegistry", "Integration", "get_integration", "list_integrations",
    "OAuthFlowManager", "OAuthToken",
    "get_provider", "PROVIDERS", "configured_providers",
]
