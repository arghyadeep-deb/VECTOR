"""Disabled optional external memory mirror boundary."""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ExternalMirrorConfig", "ExternalMemoryMirror"]


@dataclass(frozen=True)
class ExternalMirrorConfig:
    enabled: bool = False
    provider: str = "helixdb"
    endpoint: str = ""
    token: str = ""


class ExternalMemoryMirror:
    """Async enrichment mirror. SQLite remains the source of truth."""

    def __init__(self, config: ExternalMirrorConfig | None = None):
        self.config = config or ExternalMirrorConfig()

    def available(self) -> bool:
        return bool(self.config.enabled and self.config.endpoint)

    async def mirror_chunk(self, chunk_id: str, text: str, metadata: dict | None = None) -> dict:
        if not self.available():
            return {"status": "disabled", "provider": self.config.provider}
        return {
            "status": "queued",
            "provider": self.config.provider,
            "chunk_id": chunk_id,
            "bytes": len(text.encode("utf-8")),
            "metadata": metadata or {},
        }
