from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException


def test_investment_portfolio_does_not_return_synthetic_fallback(monkeypatch) -> None:
    from core.api.routers import investment

    monkeypatch.setattr(investment, "_get_agent", lambda _path: None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(investment.get_portfolio())

    assert exc.value.status_code == 503
    assert "StockAnalyst unavailable" in str(exc.value.detail)


def test_location_does_not_return_owner_coordinates_on_failure(monkeypatch) -> None:
    from core.api.routers import location

    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            raise OSError("network unavailable")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FailingClient)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(location.current_location())

    assert exc.value.status_code == 503
    assert exc.value.detail["status"] == "unavailable"
    assert exc.value.detail["source"] == "ip-api"


def test_shadowbroker_health_reports_503_when_unreachable(monkeypatch) -> None:
    from core.api.routers import sb

    async def fake_proxy_get(path: str, params=None):
        assert path == "/api/health"
        return {"error": "sb_unreachable", "detail": "connection refused"}

    monkeypatch.setattr(sb, "_proxy_get", fake_proxy_get)

    response = asyncio.run(sb.sb_health())

    assert response.status_code == 503


def test_key_mutations_require_current_key_when_configured(monkeypatch) -> None:
    from core.api.routers import keys

    class Headers:
        def __init__(self, values: list[str]):
            self._values = values

        def getlist(self, name: str) -> list[str]:
            return self._values if name.lower() == "authorization" else []

    class Request:
        def __init__(self, values: list[str]):
            self.headers = Headers(values)

    monkeypatch.setenv("VECTOR_API_KEY", "old-secret")

    with pytest.raises(HTTPException) as exc:
        keys._require_current_key_if_configured(Request([]))
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        keys._require_current_key_if_configured(Request(["Bearer wrong"]))
    assert exc.value.status_code == 401

    keys._require_current_key_if_configured(Request(["Bearer old-secret"]))
