import json
import os
import tempfile

__all__ = [
    "CheckpointData",
    "CheckpointManager",
]

from pathlib import Path
from dataclasses import dataclass, field

import anyio
from anyio import Path as AsyncPath

from core.scraper.core.utils import log
from core.scraper.core._types import List, Set, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.scraper.spiders.request import Request


@dataclass
class CheckpointData:
    """Container for checkpoint state."""

    requests: List["Request"] = field(default_factory=list)
    seen: Set[bytes] = field(default_factory=set)


class CheckpointManager:
    """Manages saving and loading checkpoint state to/from disk via JSON."""

    CHECKPOINT_FILE = "checkpoint.json"

    def __init__(self, crawldir: str | Path | AsyncPath, interval: float = 300.0):
        self.crawldir = AsyncPath(crawldir)
        self._checkpoint_path = self.crawldir / self.CHECKPOINT_FILE
        self.interval = interval
        if not isinstance(interval, (int, float)):
            raise TypeError("Checkpoints interval must be integer or float.")
        else:
            if interval < 0:
                raise ValueError("Checkpoints interval must be equal or greater than 0.")

    async def has_checkpoint(self) -> bool:
        """Check if a checkpoint exists (JSON, or a legacy pickle file that will be ignored)."""
        if await self._checkpoint_path.exists():
            return True
        legacy = self._checkpoint_path.with_suffix(".pkl")
        return await legacy.exists()

    async def save(self, data: CheckpointData) -> None:
        """Save checkpoint data to disk atomically as JSON."""
        await self.crawldir.mkdir(parents=True, exist_ok=True)

        try:
            payload = {
                "requests": [r.to_dict() for r in data.requests],
                "seen": [s.hex() for s in data.seen],
            }
            serialized = json.dumps(payload, indent=2, default=str).encode("utf-8")
            target = Path(str(self._checkpoint_path))

            def _write_atomically() -> None:
                fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(serialized)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(temp_name, target)
                except BaseException:
                    try:
                        os.unlink(temp_name)
                    except FileNotFoundError:
                        pass
                    raise

            await anyio.to_thread.run_sync(_write_atomically)

            log.info(f"Checkpoint saved: {len(data.requests)} requests, {len(data.seen)} seen URLs")
        except Exception as e:
            log.error(f"Failed to save checkpoint: {e}")
            raise

    async def _try_load_json(self, path: AsyncPath) -> Optional[CheckpointData]:
        """Try to load checkpoint as JSON (current format)."""
        try:
            async with await anyio.open_file(path, "rb") as f:
                content = await f.read()
            payload = json.loads(content)
            from core.scraper.spiders.request import Request as _Req
            requests = [_Req.from_dict(r) for r in payload.get("requests", [])]
            seen = set(bytes.fromhex(s) for s in payload.get("seen", []))
            return CheckpointData(requests=requests, seen=seen)
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, KeyError, TypeError, ValueError) as e:
            log.warning(f"[VECTOR][scraper] JSON checkpoint load failed: {e}")
            return None

    async def load(self) -> Optional[CheckpointData]:
        """Load checkpoint data from disk. JSON only (legacy pickle checkpoints are ignored)."""
        if not await self.has_checkpoint():
            return None

        try:
            resolved = Path(str(self._checkpoint_path)).resolve()
            expected_dir = Path(str(self.crawldir)).resolve()
            if not resolved.is_relative_to(expected_dir):
                log.error(f"Checkpoint path outside crawl directory — refusing to load: {resolved}")
                return None

            json_path = self._checkpoint_path
            if await json_path.exists():
                result = await self._try_load_json(json_path)
                if result is not None:
                    log.info(f"Checkpoint loaded: {len(result.requests)} requests, {len(result.seen)} seen URLs")
                    return result

            if await json_path.with_suffix(".pkl").exists():
                # pickle is banned project-wide (RCE on load); legacy checkpoints are not migrated.
                log.warning("[VECTOR][scraper] ignoring legacy pickle checkpoint (unsupported); starting fresh")

            log.error("[VECTOR][scraper] checkpoint exists but could not be loaded as JSON")
            return None

        except Exception as e:
            log.error(f"Failed to load checkpoint (starting fresh): {e}")
            return None

    async def cleanup(self) -> None:
        """Remove checkpoint files (both JSON and legacy pickle)."""
        for path in [self._checkpoint_path, self._checkpoint_path.with_suffix(".pkl")]:
            try:
                if await path.exists():
                    await path.unlink()
                    log.info(f"Checkpoint removed: {path.name}")
            except Exception as e:
                log.warning(f"Failed to remove {path}: {e}")
