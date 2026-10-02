"""
Module: core/api_manager.py
API manager - wraps all V.E.C.T.O.R. API endpoints.
"""

import sys

__all__ = [
    "APIClient",
    "APIManager",
    "APIRoute",
    "HttpMethod",
    "main",
]


from core.config import CONFIG
from loguru import logger
import httpx
import asyncio
import uuid
import json
from typing import Dict, Any, Optional, List, Callable, Awaitable
from datetime import datetime
from enum import Enum


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class APIRoute:
    """Represents an API route."""

    def __init__(
        self,
        method: str,
        path: str,
        handler: Callable,
        description: str = "",
    ):
        self.id = str(uuid.uuid4().hex[:8])
        self.method = method.upper()
        self.path = path
        self.handler = handler
        self.description = description
        self.registered_at = datetime.now().isoformat()
        self.call_count = 0
        self.last_called = None
        self.success_count = 0
        self.failure_count = 0


class APIManager:
    """
    Manages V.E.C.T.O.R API endpoints, registration, and health checks.
    """

    def __init__(self):
        self.base_url = CONFIG.get("api_base_url", "http://127.0.0.1:8000")
        self.routes: Dict[str, APIRoute] = {}
        self._client = httpx.AsyncClient(timeout=30.0)
        self.health_check_endpoints: Dict[str, str] = {}
        self._initialize_default_routes()
        logger.info(f"[APIManager] Initialized with base URL: {self.base_url}")

    def _initialize_default_routes(self):
        """Initialize default V.E.C.T.O.R API routes."""
        self.health_check_endpoints = {
            "api": f"{self.base_url}/health",
            "ollama": f"{CONFIG['ollama_host']}/api/tags",
        }

    def register_route(
        self,
        method: str,
        path: str,
        handler: Callable[[Any], Awaitable[Any]],
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Register an API route.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            path: URL path (e.g., '/api/v1/agent')
            handler: Async function to handle the request
            description: Route description

        Returns:
            Dict with registration status
        """
        route_key = f"{method.upper()}:{path}"

        if route_key in self.routes:
            logger.warning(f"[APIManager] Route {route_key} already registered, overwriting")

        route = APIRoute(method, path, handler, description)
        self.routes[route_key] = route

        logger.info(f"[APIManager] Registered route: {method} {path}")
        return {
            "success": True,
            "route_id": route.id,
            "method": method,
            "path": path,
        }

    def list_routes(self) -> List[Dict[str, Any]]:
        """
        List all registered routes.

        Returns:
            List of route information dicts
        """
        return [
            {
                "route_id": route.id,
                "method": route.method,
                "path": route.path,
                "description": route.description,
                "registered_at": route.registered_at,
                "call_count": route.call_count,
                "success_rate": route.success_count / route.call_count if route.call_count > 0 else 0,
            }
            for route in self.routes.values()
        ]

    async def call_endpoint(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Call an API endpoint.

        Args:
            method: HTTP method
            path: URL path
            data: Optional request body data
            headers: Optional headers

        Returns:
            Dict with response data
        """
        route_key = f"{method.upper()}:{path}"

        route = self.routes.get(route_key)
        if route:
            route.call_count += 1
            route.last_called = datetime.now().isoformat()

            try:
                if asyncio.iscoroutinefunction(route.handler):
                    result = await route.handler(data)
                else:
                    result = route.handler(data)

                route.success_count += 1
                logger.info(f"[APIManager] Handled {route_key} internally")
                return {"success": True, "handled": "internal", "data": result}

            except Exception as e:
                route.failure_count += 1
                logger.error(f"[APIManager] Handler error for {route_key}: {e}")
                return {"success": False, "error": str(e)}

        url = f"{self.base_url}{path}"
        request_headers = headers or {}

        try:
            if method.upper() == "GET":
                response = await self._client.get(url, headers=request_headers)
            elif method.upper() == "POST":
                response = await self._client.post(url, json=data, headers=request_headers)
            elif method.upper() == "PUT":
                response = await self._client.put(url, json=data, headers=request_headers)
            elif method.upper() == "DELETE":
                response = await self._client.delete(url, headers=request_headers)
            elif method.upper() == "PATCH":
                response = await self._client.patch(url, json=data, headers=request_headers)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}

            response.raise_for_status()
            logger.info(f"[APIManager] Called {method} {path} -> {response.status_code}")
            return {
                "success": True,
                "status_code": response.status_code,
                "data": response.json() if response.text else None,
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"[APIManager] HTTP error: {e.response.status_code}")
            return {"success": False, "error": f"HTTP {e.response.status_code}", "status_code": e.response.status_code}
        except Exception as e:
            logger.error(f"[APIManager] Request failed: {e}")
            return {"success": False, "error": str(e)}

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of all V.E.C.T.O.R services.

        Returns:
            Dict with health status of each service
        """
        services = {}
        overall_healthy = True

        ollama_status = await self._check_ollama_health()
        services["ollama"] = ollama_status
        if not ollama_status["healthy"]:
            overall_healthy = False

        api_status = await self._check_api_health()
        services["api"] = api_status
        if not api_status["healthy"]:
            overall_healthy = False

        services["memory"] = await self._check_memory_health()

        services["voice"] = await self._check_voice_health()

        logger.info(f"[APIManager] Health check: {'healthy' if overall_healthy else 'degraded'}")
        return {
            "healthy": overall_healthy,
            "timestamp": datetime.now().isoformat(),
            "services": services,
        }

    async def _check_ollama_health(self) -> Dict[str, Any]:
        """Check Ollama service health."""
        try:
            response = await self._client.get(f"{CONFIG['ollama_host']}/api/tags", timeout=5.0)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return {
                    "healthy": True,
                    "models_count": len(models),
                    "models": [m.get("name") for m in models[:5]],
                }
            return {"healthy": False, "error": f"Status {response.status_code}"}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def _check_api_health(self) -> Dict[str, Any]:
        """Check API server health."""
        try:
            response = await self._client.get(f"{self.base_url}/health", timeout=5.0)
            if response.status_code == 200:
                return {"healthy": True, "data": response.json()}
            return {"healthy": False, "error": f"Status {response.status_code}"}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def _check_memory_health(self) -> Dict[str, Any]:
        """Check memory services health."""
        try:
            # KNOWN_ISSUES #21: EpisodicMemory() wraps a process-wide singleton
            # connection (core.memory.episodic.get_db_connection()). Closing
            # it from a periodic health check used to poison memory access for
            # every other agent/thread in the system on every health-check
            # tick — see districts/skills/skill_mapper.py for the full note.
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            stats = mem.get_stats()
            return {
                "healthy": True,
                "stats": {
                    "episodic": stats.get("episodic_memory", 0),
                    "semantic": stats.get("semantic_memory", 0),
                    "reasoning_chains": stats.get("reasoning_chains", 0),
                },
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def _check_voice_health(self) -> Dict[str, Any]:
        """Check voice services health."""
        return {"healthy": True, "note": "Voice not initialized in this context"}

    def register_health_endpoint(self, name: str, url: str):
        """Register an additional health check endpoint."""
        self.health_check_endpoints[name] = url
        logger.info(f"[APIManager] Registered health endpoint: {name}")

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
        logger.info("[APIManager] HTTP client closed")


class APIClient:
    """Client for making requests to V.E.C.T.O.R API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def get(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make GET request."""
        try:
            response = await self._client.get(f"{self.base_url}{path}", **kwargs)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def post(self, path: str, data: Dict = None, **kwargs) -> Dict[str, Any]:
        """Make POST request."""
        try:
            response = await self._client.post(f"{self.base_url}{path}", json=data, **kwargs)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def close(self):
        """Close the client."""
        await self._client.aclose()


async def main():
    """Test the API manager."""
    manager = APIManager()

    async def test_handler(data):
        return {"message": "test response"}

    manager.register_route("GET", "/test", test_handler, "Test endpoint")

    logger.info("Routes: {}", manager.list_routes())


    health = await manager.health_check()
    logger.info(f"Health: {health}")


    await manager.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
    print("✅ api_manager.py OK")
