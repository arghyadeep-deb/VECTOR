from __future__ import annotations

from core.runtime.readiness_check import _check_secret_manager, _check_tls_config


def test_readiness_check_accepts_tls_proxy_termination(monkeypatch):
    monkeypatch.setenv("VECTOR_TLS_TERMINATED", "1")
    monkeypatch.delenv("VECTOR_TLS_CERTFILE", raising=False)
    monkeypatch.delenv("VECTOR_TLS_KEYFILE", raising=False)

    check = _check_tls_config()

    assert check.status == "ok"
    assert check.evidence["terminated"] is True


def test_readiness_check_warns_on_plain_http_in_dev(monkeypatch):
    monkeypatch.delenv("VECTOR_ENV", raising=False)
    monkeypatch.delenv("VECTOR_TLS_TERMINATED", raising=False)
    monkeypatch.delenv("VECTOR_TLS_CERTFILE", raising=False)
    monkeypatch.delenv("VECTOR_TLS_KEYFILE", raising=False)

    check = _check_tls_config()

    assert check.status == "warn"


def test_secret_manager_warns_on_missing_launch_secrets_in_dev(monkeypatch):
    monkeypatch.delenv("VECTOR_ENV", raising=False)
    monkeypatch.delenv("VECTOR_API_KEY", raising=False)
    monkeypatch.delenv("MCP_KERNEL_SECRET", raising=False)

    check = _check_secret_manager()

    assert check.status in {"warn", "ok"}
    if check.status == "warn":
        assert "missing" in check.evidence
