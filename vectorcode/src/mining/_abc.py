"""VECTOR mining stub types."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
from pathlib import Path
import json
import os
import tempfile

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
    hashrate: float = 0.0
    uptime_seconds: float = 0.0
    last_share_at: Optional[float] = None
    last_error: Optional[str] = None

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
        fd, tmp_name = tempfile.mkstemp(prefix=".mining-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def read(path: Path) -> Optional[dict]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def remove(path: Path) -> None:
        if path.exists():
            path.unlink()
