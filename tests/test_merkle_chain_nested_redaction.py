"""Regression: core/audit/merkle_chain.py's MerkleAuditChain._redact() only
checked top-level payload keys -- a nested secret (e.g.
{"request": {"api_key": "sk-real-secret"}}, a plausible shape for the
"tool_call"/"llm_request" actions this chain exists to log) was written
unredacted to the persistent, append-only, on-disk audit trail at
~/.vector_ca/audit/chain.jsonl, contradicting the class's own docstring
promise ("secrets auto-redacted").
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.audit.merkle_chain import MerkleAuditChain


def test_nested_secret_is_redacted(tmp_path):
    chain = MerkleAuditChain(chain_file=tmp_path / "chain.jsonl")
    entry = chain.log("agent_001", "llm_request", "coding", {
        "request": {"api_key": "sk-real-secret", "model": "qwen3:14b"},
        "headers": [{"name": "Authorization", "token": "real-token"}],
    })
    assert entry.payload["request"]["api_key"] == "[REDACTED]"
    assert entry.payload["request"]["model"] == "qwen3:14b"
    assert entry.payload["headers"][0]["token"] == "[REDACTED]"
    assert entry.payload["headers"][0]["name"] == "Authorization"

    raw = (tmp_path / "chain.jsonl").read_text(encoding="utf-8")
    assert "sk-real-secret" not in raw
    assert "real-token" not in raw


def test_top_level_secret_still_redacted():
    chain = MerkleAuditChain.__new__(MerkleAuditChain)
    redacted = chain._redact({"password": "plaintext", "safe": "ok"})
    assert redacted == {"password": "[REDACTED]", "safe": "ok"}


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
