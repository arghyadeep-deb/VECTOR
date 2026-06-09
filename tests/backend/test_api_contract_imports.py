from __future__ import annotations

import importlib
import pkgutil

from fastapi.testclient import TestClient


def test_main_api_app_constructs() -> None:
    from core.api.app import create_app

    app = create_app()

    route_paths = {getattr(route, "path", "") for route in app.routes}
    assert "/status" in route_paths
    assert "/health" in route_paths
    assert "/gateway/pending" in route_paths
    assert len(route_paths) > 50


def test_all_core_api_router_modules_import() -> None:
    import core.api.routers as routers_pkg

    failures: dict[str, str] = {}
    for module_info in pkgutil.iter_modules(routers_pkg.__path__):
        module_name = f"{routers_pkg.__name__}.{module_info.name}"
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - failure detail for contract test
            failures[module_name] = f"{type(exc).__name__}: {exc}"

    assert failures == {}


def test_safe_backend_status_endpoints_respond() -> None:
    from core.api.app import create_app

    client = TestClient(create_app())

    for path in ("/health", "/status", "/gateway/pending", "/providers/routes", "/tools/registry"):
        response = client.get(path)
        assert response.status_code < 500, f"{path} returned {response.status_code}: {response.text[:300]}"
