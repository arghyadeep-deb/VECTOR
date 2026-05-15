"""VECTOR mining stub types."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path
import json

@dataclass
class MiningCapabilities:
    supported: bool = False
    reason: str = ""

@dataclass
class MiningConfig:
    wallet_address: str = ""
    extra: Optional[Dict[str, Any]] = None

@dataclass
class MiningStats:
    provider_id: str = ""
    shares_submitted: int = 0
    shares_accepted: int = 0
    blocks_found: int = 0
    uptime_seconds: float = 0.0
    last_error: str = ""

class MiningProvider:
    """Abstract mining provider base class."""
    provider_id: str = "unknown"

    @classmethod
    def detect(cls, hw, engine_id: str, model: str) -> MiningCapabilities:
        return MiningCapabilities(supported=False, reason="not implemented")

    async def start(self, config: MiningConfig) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    def is_running(self) -> bool:
        return False

    def stats(self) -> MiningStats:
        return MiningStats(provider_id=self.provider_id)

class Sidecar:
    """Sidecar JSON file for mining process state."""
    @staticmethod
    def write(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def remove(path: Path) -> None:
        if path.exists():
            path.unlink()
