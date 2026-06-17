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


def test_encrypted_memory_key_mismatch_is_actionable(monkeypatch, tmp_path) -> None:
    from core.memory import episodic as ep

    db_path = tmp_path / "vector_memory.db"
    db_path.write_bytes(b"not-a-sqlite-header-and-not-openable")

    monkeypatch.setitem(ep.CONFIG, "db_path", db_path)
    monkeypatch.setattr(ep, "_USE_SQLCIPHER", True)
    monkeypatch.setattr(ep, "_db_connection", None)

    def fail_open(_path):
        raise RuntimeError("bad key")

    monkeypatch.setattr(ep, "_open_sqlcipher_connection", fail_open)

    report = ep.diagnose_memory_db()

    assert report["status"] == "key_mismatch_or_corrupt"
    assert report["can_open"] is False
    assert "VECTOR_DB_KEY" in report["detail"]

    with pytest.raises(ep.MemoryDatabaseUnavailable) as exc:
        ep.get_db_connection()
    assert "memory-repair" in str(exc.value)


def test_safe_expression_evaluator_blocks_dunder_escape() -> None:
    from core.security.safe_eval import UnsafeExpressionError, safe_eval_expression

    assert safe_eval_expression("price > 10 and volume >= 100", {"price": 12, "volume": 200}) is True

    with pytest.raises(UnsafeExpressionError):
        safe_eval_expression("().__class__.__bases__", {})


def test_dynamic_strategy_execution_requires_explicit_opt_in(monkeypatch) -> None:
    from core.security.dynamic_execution import (
        DynamicExecutionDisabled,
        dynamic_strategy_execution_enabled,
        require_dynamic_strategy_execution,
    )

    monkeypatch.delenv("VECTOR_ALLOW_DYNAMIC_STRATEGIES", raising=False)
    assert dynamic_strategy_execution_enabled() is False
    with pytest.raises(DynamicExecutionDisabled):
        require_dynamic_strategy_execution("test strategy")

    monkeypatch.setenv("VECTOR_ALLOW_DYNAMIC_STRATEGIES", "1")
    require_dynamic_strategy_execution("test strategy")
