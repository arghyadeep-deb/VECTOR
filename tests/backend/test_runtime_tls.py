from __future__ import annotations

from pathlib import Path

from core.runtime.tls import load_tls_config, uvicorn_ssl_kwargs


def test_tls_disabled_without_cert_or_proxy(monkeypatch):
    monkeypatch.delenv("VECTOR_TLS_CERTFILE", raising=False)
    monkeypatch.delenv("VECTOR_TLS_KEYFILE", raising=False)
    monkeypatch.delenv("VECTOR_TLS_TERMINATED", raising=False)

    cfg = load_tls_config()

    assert cfg.enabled is False
    assert cfg.terminated is False
    assert cfg.scheme == "http"
    assert uvicorn_ssl_kwargs() == {}


def test_tls_enabled_with_existing_cert_and_key(monkeypatch, tmp_path: Path):
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("test cert", encoding="utf-8")
    key.write_text("test key", encoding="utf-8")
    monkeypatch.setenv("VECTOR_TLS_CERTFILE", str(cert))
    monkeypatch.setenv("VECTOR_TLS_KEYFILE", str(key))
    monkeypatch.delenv("VECTOR_TLS_TERMINATED", raising=False)

    cfg = load_tls_config()

    assert cfg.enabled is True
    assert cfg.scheme == "https"
    assert uvicorn_ssl_kwargs() == {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}


def test_tls_proxy_termination_marker(monkeypatch):
    monkeypatch.delenv("VECTOR_TLS_CERTFILE", raising=False)
    monkeypatch.delenv("VECTOR_TLS_KEYFILE", raising=False)
    monkeypatch.setenv("VECTOR_TLS_TERMINATED", "1")

    cfg = load_tls_config()

    assert cfg.enabled is False
    assert cfg.terminated is True
    assert cfg.scheme == "http"
    assert "upstream proxy" in cfg.detail


def test_tls_misconfigured_when_one_file_missing(monkeypatch, tmp_path: Path):
    cert = tmp_path / "cert.pem"
    cert.write_text("test cert", encoding="utf-8")
    monkeypatch.setenv("VECTOR_TLS_CERTFILE", str(cert))
    monkeypatch.delenv("VECTOR_TLS_KEYFILE", raising=False)

    cfg = load_tls_config()

    assert cfg.enabled is False
    assert cfg.detail.startswith("TLS misconfigured")
