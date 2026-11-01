"""FastAPI dependencies for V.E.C.T.O.R.

ServiceLocator pattern for managing app-level singletons via app.state.
Dependencies are registered during startup and injected via Depends().

Usage:
    from core.api.dependencies import get_context_engine
    
    @router.get("/status")
    async def status(engine=Depends(get_context_engine)):
        # Already exists from startup_event
        return {"engine": engine}
"""

import sys

__all__ = [
    "get_agent_registry",
    "get_context_engine",
    "get_decision_engine",
    "get_episodic_memory",
    "get_permission_gateway",
    "ServiceLocator",
]


from fastapi import Depends, HTTPException, Request
from loguru import logger
from core.config import CONFIG


class ServiceLocator:
    """Singleton service container - stores services registered during startup."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.services = {}
        return cls._instance
    
    def register(self, key: str, service):
        """Register a service instance (called during startup)."""
        self.services[key] = service
        logger.info(f"[VECTOR][deps] Service registered: {key}")
    
    def get(self, key: str):
        """Get a service instance."""
        if key not in self.services:
            raise KeyError(f"Service '{key}' not initialized")
        return self.services[key]


# Global singleton
_locator = ServiceLocator()


def _lazy_get_or_create(request: Request, key: str, factory):
    """Get service from app.state first, then ServiceLocator, then create lazily."""
    # Check app.state first — avoids duplicate singletons when lifespan already created them
    if request is not None:
        app_val = getattr(getattr(request, "app", None), "state", None)
        if app_val is not None:
            val = getattr(app_val, key, None)
            if val is not None:
                return val
    try:
        return _locator.get(key)
    except KeyError:
        try:
            instance = factory()
            _locator.register(key, instance)
            return instance
        except Exception as e:
            logger.error(f"[VECTOR][deps] {key} creation failed: {e}")
            raise HTTPException(status_code=503, detail=f"Service unavailable: {key}")


# Dependency functions (injected via Depends)
def get_context_engine(request: Request):
    """Get ContextEngine singleton."""
    return _lazy_get_or_create(
        request, "context_engine", 
        lambda: __import__("core.loop.context_engine", fromlist=["ContextEngine"]).ContextEngine()
    )


def get_decision_engine(request: Request):
    """Get DecisionEngine singleton."""
    return _lazy_get_or_create(
        request, "decision_engine",
        lambda: __import__("core.loop.decision_engine", fromlist=["DecisionEngine"]).DecisionEngine()
    )


def get_permission_gateway(request: Request):
    """Get PermissionGateway singleton (the process-wide shared instance, so
    pending approvals are visible to the loop's remote-command relay too)."""
    return _lazy_get_or_create(
        request, "permission_gateway",
        lambda: __import__("core.loop.permission_gateway", fromlist=["PermissionGateway"]).PermissionGateway.get_shared()
    )


def get_episodic_memory(request: Request):
    """Get EpisodicMemory singleton."""
    return _lazy_get_or_create(
        request, "episodic_memory",
        lambda: __import__("core.memory.episodic", fromlist=["EpisodicMemory"]).EpisodicMemory()
    )


def get_agent_registry(request: Request):
    """Get AgentRegistry singleton."""
    return _lazy_get_or_create(
        request, "agent_registry",
        lambda: __import__("core.city.agent_registry", fromlist=["get_registry"]).get_registry()
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK")
