# VECTOR module -- ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb

"""ABCs and dataclasses for GPU container launch utilities."""

from __future__ import annotations

import json
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from vectorcode.src.vc_core.config import HardwareInfo

@dataclass(slots=True)
class MiningCapabilities:
    """Result of a provider's ``detect()`` call."""
    supported: bool
    reason: Optional[str] = None
    estimated_hashrate: Optional[float] = None

@dataclass(slots=True)
class SoloTarget:
    """Mine directly to a pearld node."""
    pearld_rpc_url: str

@dataclass(slots=True)
class PoolTarget:
    """Mine through an OJ-operated pool."""
    url: str
    worker_id: Optional[str] = None

SubmitTarget = Union[SoloTarget, PoolTarget]

@dataclass(slots=True)
class MiningConfig:
    """User-supplied mining configuration."""
    provider: str
    wallet_address: str
    submit_target: SubmitTarget
    fee_bps: int = 0
    fee_payout_address: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class MiningStats:
    """Live mining statistics."""
    provider_id: str
    shares_submitted: int = 0
    shares_accepted: int = 0
    blocks_found: int = 0
    hashrate: float = 0.0
    uptime_seconds: float = 0.0
    last_share_at: Optional[float] = None
    last_error: Optional[str] = None
    payout_target: str = "solo"
    fees_owed: int = 0

class MiningProvider(ABC):
    """ABC for a mining provider."""

    provider_id: str

    @classmethod
    @abstractmethod
    def detect(cls, hw: HardwareInfo, engine_id: str, model: str) -> MiningCapabilities:
        ...

    @abstractmethod
    async def start(self, config: MiningConfig) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @abstractmethod
    def is_running(self) -> bool:
        ...

    @abstractmethod
    def stats(self) -> MiningStats:
        ...

class Sidecar:
    """Read/write helpers for runtime state JSON."""

    @staticmethod
    def write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".mining-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @staticmethod
    def read(path: Path) -> Optional[dict[str, Any]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def remove(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
