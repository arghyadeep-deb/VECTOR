"""
VECTOR Merkle Audit Chain — cryptographic append-only audit trail.

Every agent action is hashed and chained. Each entry contains:
  - SHA-256 hash of its own content
  - SHA-256 hash of the previous entry (chain link)

Tamper-proof: modifying any entry breaks the chain, detected by verify().
Persisted to ~/.vector_ca/audit/chain.jsonl (one JSON per line).

Ported from the agent OS kernel AuditLog system.
"""
from __future__ import annotations

__all__ = [
    "AuditEntry",
    "AuditVerification",
    "get_audit_chain",
    "MerkleAuditChain",
]


import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from loguru import logger

_CHAIN_DIR = Path.home() / ".vector_ca" / "audit"
_CHAIN_FILE = _CHAIN_DIR / "chain.jsonl"
_GENESIS_HASH = "0" * 64     # Genesis block previous hash


@dataclass
class AuditEntry:
    sequence: int
    timestamp: float
    agent_id: str
    action: str              # e.g. "tool_call", "llm_request", "decision", "act"
    district: str
    payload: dict            # action-specific data (redacts secrets automatically)
    prev_hash: str           # hash of previous entry
    entry_hash: str = ""     # computed hash of this entry (set after construction)

    def _compute_hash(self) -> str:
        """SHA-256 of deterministic JSON of all fields except entry_hash."""
        blob = json.dumps({
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "action": self.action,
            "district": self.district,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    def seal(self) -> "AuditEntry":
        """Compute and set entry_hash. Call after all fields are set."""
        self.entry_hash = self._compute_hash()
        return self

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AuditEntry":
        return cls(**d)

    def is_valid(self) -> bool:
        """Verify this entry's hash matches its content."""
        return self.entry_hash == self._compute_hash()


@dataclass
class AuditVerification:
    valid: bool
    total_entries: int
    broken_at: int | None = None          # sequence number where chain broke
    reason: str = ""

    def __str__(self) -> str:
        if self.valid:
            return f"Chain OK — {self.total_entries} entries verified"
        return f"Chain BROKEN at seq={self.broken_at}: {self.reason}"


class MerkleAuditChain:
    """
    Append-only Merkle hash-chain for VECTOR's audit trail.

    Usage:
        audit = MerkleAuditChain()
        audit.log("agent_001", "tool_call", "coding",
                  {"tool": "bash", "cmd": "git status"})
        result = audit.verify()
        logger.info(result)  # Chain OK — 1 entries verified

    """

    _SENSITIVE_KEYS = frozenset({
        "password", "secret", "token", "api_key", "key", "credential",
        "auth", "private", "passwd", "access_token", "refresh_token",
    })

    def __init__(self, chain_file: Path | None = None) -> None:
        self._file = chain_file or _CHAIN_FILE
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._cache: list[AuditEntry] = []
        self._loaded = False

    def _load(self) -> list[AuditEntry]:
        if self._loaded:
            return self._cache
        entries: list[AuditEntry] = []
        if self._file.exists():
            for line in self._file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(AuditEntry.from_dict(json.loads(line)))
                    except Exception as e:
                        logger.warning("[VECTOR][audit] skipped unreadable chain line: {}", e)
        self._cache = entries
        self._loaded = True
        return entries

    def _last_hash(self) -> str:
        entries = self._load()
        return entries[-1].entry_hash if entries else _GENESIS_HASH

    def _next_seq(self) -> int:
        return len(self._load())

    def _redact(self, payload: dict) -> dict:
        """Remove sensitive values before storing.

        Recurses into nested dicts/lists -- the old version only checked
        top-level keys, so a real secret in e.g. {"request": {"api_key":
        "sk-..."}} (a very plausible shape for the "tool_call"/
        "llm_request" actions this chain exists to log) was written
        unredacted to this persistent, append-only, on-disk audit trail,
        directly contradicting this class's own docstring promise
        ("secrets auto-redacted").
        """
        return self._redact_value(payload)

    def _redact_value(self, value):
        if isinstance(value, dict):
            return {
                k: "[REDACTED]" if any(s in k.lower() for s in self._SENSITIVE_KEYS)
                else self._redact_value(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self._redact_value(v) for v in value]
        return value

    def log(
        self,
        agent_id: str,
        action: str,
        district: str,
        payload: dict | None = None,
    ) -> AuditEntry:
        """
        Append an action to the audit chain.

        Args:
            agent_id: Agent that performed the action
            action:   Action type ("tool_call", "llm_request", "decision", "error")
            district: VECTOR district name
            payload:  Action-specific data (secrets auto-redacted)

        Returns:
            The sealed AuditEntry.
        """
        entry = AuditEntry(
            sequence=self._next_seq(),
            timestamp=time.time(),
            agent_id=agent_id,
            action=action,
            district=district,
            payload=self._redact(payload or {}),
            prev_hash=self._last_hash(),
        ).seal()

        # Append to file (one JSON per line)
        with self._file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), separators=(",", ":")) + "\n")

        self._cache.append(entry)
        logger.debug(
            "[VECTOR][audit] seq={} agent={} action={} hash={}...",
            entry.sequence, agent_id, action, entry.entry_hash[:8],
        )
        return entry

    def verify(self) -> AuditVerification:
        """
        Verify the entire chain is intact.

        Checks:
          1. Each entry's entry_hash matches its content (tamper detection)
          2. Each entry's prev_hash matches the previous entry's hash (chain integrity)
        """
        entries = self._load()
        if not entries:
            return AuditVerification(valid=True, total_entries=0)

        prev_hash = _GENESIS_HASH
        for entry in entries:
            # Check content hash
            if not entry.is_valid():
                return AuditVerification(
                    valid=False,
                    total_entries=len(entries),
                    broken_at=entry.sequence,
                    reason=f"Entry hash mismatch (content tampered)",
                )
            # Check chain link
            if entry.prev_hash != prev_hash:
                return AuditVerification(
                    valid=False,
                    total_entries=len(entries),
                    broken_at=entry.sequence,
                    reason=f"Chain link broken (prev_hash mismatch)",
                )
            prev_hash = entry.entry_hash

        logger.info("[VECTOR][audit] chain verified: {} entries", len(entries))
        return AuditVerification(valid=True, total_entries=len(entries))

    def tail(self, n: int = 20) -> list[AuditEntry]:
        """Return last N entries."""
        return self._load()[-n:]

    def search(self, agent_id: str | None = None, action: str | None = None,
               district: str | None = None) -> list[AuditEntry]:
        """Filter entries by agent, action, or district."""
        results = self._load()
        if agent_id:
            results = [e for e in results if e.agent_id == agent_id]
        if action:
            results = [e for e in results if e.action == action]
        if district:
            results = [e for e in results if e.district == district]
        return results

    def count(self) -> int:
        return len(self._load())

    def export_json(self) -> list[dict]:
        return [e.to_dict() for e in self._load()]


# Singleton
_chain: MerkleAuditChain | None = None


def get_audit_chain() -> MerkleAuditChain:
    global _chain
    if _chain is None:
        _chain = MerkleAuditChain()
    return _chain


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        chain = MerkleAuditChain(chain_file=Path(d) / "chain.jsonl")

        # Append entries
        e1 = chain.log("agent_001", "tool_call", "coding",
                       {"tool": "bash", "cmd": "git status"})
        e2 = chain.log("agent_001", "llm_request", "coding",
                       {"model": "qwen3:14b", "tokens": 150})
        e3 = chain.log("agent_002", "decision", "governance",
                       {"action": "approve", "confidence": 0.9})

        assert chain.count() == 3

        # Verify clean chain
        result = chain.verify()
        assert result.valid, str(result)
        assert result.total_entries == 3

        # Tamper with entry and verify detects it
        chain2 = MerkleAuditChain(chain_file=Path(d) / "chain.jsonl")
        chain2._load()
        chain2._cache[1].payload["model"] = "TAMPERED"  # tamper in memory
        assert not chain2._cache[1].is_valid()

        # Search
        coding_entries = chain.search(district="coding")
        assert len(coding_entries) == 2

        print(f"OK merkle_chain.py — {chain.count()} entries, chain verified, tamper detected")
