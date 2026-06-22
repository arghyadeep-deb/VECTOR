"""Coverage tests for core/audit/ and core/runtime/ modules."""

import json
import tempfile
from pathlib import Path
import pytest

from core.audit.merkle_chain import MerkleAuditChain, AuditEntry
from core.runtime.tls import load_tls_config, uvicorn_ssl_kwargs, TLSConfig


class TestMerkleAuditChain:
    def test_log_and_verify(self):
        with tempfile.TemporaryDirectory() as d:
            chain = MerkleAuditChain(chain_file=Path(d) / "chain.jsonl")
            chain.log("agent-1", "read_file", "security", payload={"path": "/etc/hosts"})
            chain.log("agent-2", "write_file", "coding", payload={"path": "/tmp/test.py"})
            result = chain.verify()
            assert result.valid is True

    def test_verify_detects_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            chain = MerkleAuditChain(chain_file=Path(d) / "chain.jsonl")
            chain.log("agent-1", "read", "district-a", payload={})
            chain.log("agent-2", "write", "district-b", payload={})
            chain._cache[0].payload["tampered"] = True
            result = chain.verify()
            assert result.valid is False

    def test_redacts_sensitive_keys(self):
        with tempfile.TemporaryDirectory() as d:
            chain = MerkleAuditChain(chain_file=Path(d) / "chain.jsonl")
            chain.log("agent-1", "login", "security", payload={"password": "secret123", "user": "admin"})
            result = chain.verify()
            assert result.valid is True
            assert chain._cache[0].payload["password"] == "[REDACTED]"
            assert chain._cache[0].payload["user"] == "admin"

    def test_empty_chain_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            chain = MerkleAuditChain(chain_file=Path(d) / "chain.jsonl")
            result = chain.verify()
            assert result.valid is True


class TestAuditEntry:
    def test_seal_creates_hash(self):
        entry = AuditEntry(
            sequence=1, timestamp=1000.0, agent_id="test", action="read",
            district="test", payload={}, prev_hash="0" * 64,
        )
        sealed = entry.seal()
        assert sealed.entry_hash is not None
        assert len(sealed.entry_hash) == 64

    def test_different_entries_different_hashes(self):
        e1 = AuditEntry(sequence=1, timestamp=1000.0, agent_id="a", action="read", district="d", payload={}, prev_hash="0" * 64).seal()
        e2 = AuditEntry(sequence=2, timestamp=1001.0, agent_id="a", action="read", district="d", payload={}, prev_hash=e1.entry_hash).seal()
        assert e1.entry_hash != e2.entry_hash


class TestTLSConfig:
    def test_no_tls_when_no_env(self, monkeypatch):
        monkeypatch.delenv("VECTOR_TLS_CERTFILE", raising=False)
        monkeypatch.delenv("VECTOR_TLS_KEYFILE", raising=False)
        monkeypatch.delenv("VECTOR_TLS_TERMINATED", raising=False)
        cfg = load_tls_config()
        assert cfg.enabled is False
        assert cfg.scheme == "http"

    def test_tls_terminated_mode(self, monkeypatch):
        monkeypatch.delenv("VECTOR_TLS_CERTFILE", raising=False)
        monkeypatch.delenv("VECTOR_TLS_KEYFILE", raising=False)
        monkeypatch.setenv("VECTOR_TLS_TERMINATED", "1")
        cfg = load_tls_config()
        assert cfg.enabled is False
        assert cfg.terminated is True
        assert "upstream proxy" in cfg.detail

    def test_uvicorn_kwargs_empty_when_no_tls(self, monkeypatch):
        monkeypatch.delenv("VECTOR_TLS_CERTFILE", raising=False)
        monkeypatch.delenv("VECTOR_TLS_KEYFILE", raising=False)
        assert uvicorn_ssl_kwargs() == {}
