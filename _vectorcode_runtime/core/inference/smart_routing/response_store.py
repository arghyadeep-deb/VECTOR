"""
VECTOR Smart Routing — Persistent Response Store
Python port of ClawRouter/src/response-store.ts

Stores LLM responses persistently (beyond the 30s in-memory cache).
Enables response retrieval, sharing, and audit trail.

Usage:
    store = ResponseStore()
    resp_id = store.save(model="gpt-4o", messages=[...], response={...})
    retrieved = store.get(resp_id)
    recent = store.list_recent(limit=10)
"""
from __future__ import annotations
from loguru import logger

__all__ = [
    "ResponseStore",
    "StoredResponse",
]


import hashlib
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


_STORE_DIR = Path.home() / ".vector" / "smart_routing" / "responses"


@dataclass
class StoredResponse:
    id: str
    model: str
    messages: list[dict]
    response: dict
    created_at: float
    tier: str = ""
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0


class ResponseStore:
    """
    Persistent response store. Each response stored as a JSON file.
    ID = SHA-256 hash of (model + messages) truncated to 16 chars.
    """

    def __init__(self, store_dir: Path | None = None) -> None:
        self._dir = store_dir or _STORE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def _response_id(self, model: str, messages: list[dict]) -> str:
        raw = json.dumps({"model": model, "messages": messages}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def save(
        self,
        model: str,
        messages: list[dict],
        response: dict,
        tier: str = "",
        cost_usd: float = 0.0,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> str:
        """Store a response. Returns the response ID."""
        resp_id = self._response_id(model, messages)
        stored = StoredResponse(
            id=resp_id,
            model=model,
            messages=messages,
            response=response,
            created_at=time.time(),
            tier=tier,
            cost_usd=cost_usd,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        out_path = self._dir / f"{resp_id}.json"
        out_path.write_text(json.dumps(asdict(stored), indent=2), encoding="utf-8")
        return resp_id

    def get(self, resp_id: str) -> StoredResponse | None:
        """Retrieve a stored response by ID."""
        path = self._dir / f"{resp_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return StoredResponse(**data)

    def list_recent(self, limit: int = 20) -> list[StoredResponse]:
        """List most recently stored responses."""
        files = sorted(self._dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        results = []
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(StoredResponse(**data))
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return results

    def delete(self, resp_id: str) -> bool:
        """Delete a stored response."""
        path = self._dir / f"{resp_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def stats(self) -> dict:
        files = list(self._dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "count":       len(files),
            "size_bytes":  total_size,
            "store_dir":   str(self._dir),
        }


if __name__ == "__main__":
    import sys, tempfile
    sys.stdout.reconfigure(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        store = ResponseStore(store_dir=Path(tmp))
        msgs = [{"role": "user", "content": "hello"}]
        resp = {"choices": [{"message": {"content": "hi"}}]}
        rid = store.save("gpt-4o", msgs, resp, cost_usd=0.001)
        assert len(rid) == 16
        retrieved = store.get(rid)
        assert retrieved.model == "gpt-4o"
        recent = store.list_recent(10)
        assert len(recent) == 1
        st = store.stats()
        assert st["count"] == 1

    print(f"OK response_store.py — persistent response storage")
    print(f"  store_dir: {_STORE_DIR}")
