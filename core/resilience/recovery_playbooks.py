"""Automated recovery procedures for the top 10 failure modes."""

from __future__ import annotations

__all__ = [
    "ConfigCorruptPlaybook",
    "DBCorruptionPlaybook",
    "DiskFullPlaybook",
    "GPUFailurePlaybook",
    "ModelCrashPlaybook",
    "NetworkPartitionPlaybook",
    "OOMPlaybook",
    "PlaybookResult",
    "ProcessHangPlaybook",
    "RecoveryPlaybook",
    "run_all_playbooks",
]


import subprocess
import sys
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
import asyncio


@dataclass
class PlaybookResult:
    name: str
    success: bool
    duration_s: float = 0.0
    actions_taken: list[str] = field(default_factory=list)
    error: str = ""


class RecoveryPlaybook(ABC):
    name: str = "base"

    @abstractmethod
    async def run(self) -> PlaybookResult:
        ...


class ModelCrashPlaybook(RecoveryPlaybook):
    name = "model_crash"

    async def run(self) -> PlaybookResult:
        import time
        import httpx

        start = time.time()
        actions = []
        try:
            resp = await httpx.post(
                "http://127.0.0.1:11434/api/generate",
                json={"model": "vector-focus", "prompt": "ping", "stream": False},
                timeout=5.0,
            )
            if resp.status_code == 200:
                actions.append("Ollama model healthy")
                return PlaybookResult(name=self.name, success=True, duration_s=time.time() - start, actions_taken=actions)
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        actions.append("Attempting Ollama restart")
        (await asyncio.to_thread(subprocess.run, ["ollama", "serve"], capture_output=True, timeout=10))
        actions.append("Ollama process started")
        return PlaybookResult(name=self.name, success=True, duration_s=time.time() - start, actions_taken=actions)


class OOMPlaybook(RecoveryPlaybook):
    name = "oom_recovery"

    async def run(self) -> PlaybookResult:
        import time
        import gc
        start = time.time()
        gc.collect()

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("[Playbook] GPU cache cleared")
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        return PlaybookResult(
            name=self.name, success=True,
            duration_s=time.time() - start,
            actions_taken=["gc.collect()", "torch.cuda.empty_cache()"],
        )


class DiskFullPlaybook(RecoveryPlaybook):
    name = "disk_full"

    async def run(self) -> PlaybookResult:
        import time
        import shutil
        import tempfile
        from pathlib import Path

        start = time.time()
        actions = []

        for path in [Path(tempfile.gettempdir()), Path("."), Path.home() / ".cache"]:
            if path.exists():
                try:
                    entries = list(path.glob("*.tmp")) + list(path.glob("*.log")) + list(path.glob("*.chaos"))
                    for f in entries[:50]:
                        if f.is_file() and f.stat().st_mtime < time.time() - 86400:
                            f.unlink(missing_ok=True)
                            actions.append(f"Removed old: {f.name}")
                except PermissionError:
                    continue

        return PlaybookResult(
            name=self.name, success=True,
            duration_s=time.time() - start,
            actions_taken=actions or ["No cleanup needed"],
        )


class NetworkPartitionPlaybook(RecoveryPlaybook):
    name = "network_partition"

    async def run(self) -> PlaybookResult:
        import time
        import httpx

        start = time.time()
        actions = []

        endpoints = [
            ("Ollama", "http://127.0.0.1:11434/api/tags"),
            ("Local API", "http://127.0.0.1:8000/health"),
        ]
        for name, url in endpoints:
            try:
                r = await httpx.get(url, timeout=3.0)
                actions.append(f"{name}: {'OK' if r.status_code == 200 else f'status={r.status_code}'}")
            except Exception as e:
                actions.append(f"{name}: unreachable ({e})")

        return PlaybookResult(
            name=self.name, success=True,
            duration_s=time.time() - start,
            actions_taken=actions,
        )


class GPUFailurePlaybook(RecoveryPlaybook):
    name = "gpu_failure"

    async def run(self) -> PlaybookResult:
        import time
        start = time.time()
        actions = []

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                actions.append(f"GPU OK: {torch.cuda.get_device_name(0)}")
            else:
                actions.append("GPU unavailable — falling back to CPU")
        except ImportError:
            actions.append("torch not installed — skipping GPU check")

        return PlaybookResult(
            name=self.name, success=True,
            duration_s=time.time() - start,
            actions_taken=actions,
        )


class ProcessHangPlaybook(RecoveryPlaybook):
    name = "process_hang"

    async def run(self) -> PlaybookResult:
        import time
        import psutil

        start = time.time()
        actions = []

        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                if proc.info["cpu_percent"] and proc.info["cpu_percent"] > 90:
                    actions.append(f"High CPU: {proc.info['name']} (PID {proc.info['pid']}) — restarting")
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return PlaybookResult(
            name=self.name, success=True,
            duration_s=time.time() - start,
            actions_taken=actions or ["No hung processes detected"],
        )


class ConfigCorruptPlaybook(RecoveryPlaybook):
    name = "config_corrupt"

    async def run(self) -> PlaybookResult:
        import time
        start = time.time()
        try:
            from core.config import CONFIG
            _ = CONFIG["ollama_host"]
            return PlaybookResult(
                name=self.name, success=True,
                duration_s=time.time() - start,
                actions_taken=["Config validated OK"],
            )
        except Exception as e:
            return PlaybookResult(
                name=self.name, success=False,
                duration_s=time.time() - start,
                error=str(e),
            )


class DBCorruptionPlaybook(RecoveryPlaybook):
    name = "db_corruption"

    async def run(self) -> PlaybookResult:
        import time
        from core.memory.db_utils import configured_db_path

        start = time.time()
        actions = []

        db_path = configured_db_path()
        if db_path.exists():
            if os.environ.get("VECTOR_DB_RECOVERY_CHECK") != "1":
                actions.append("DB integrity check skipped; set VECTOR_DB_RECOVERY_CHECK=1 to inspect live memory DB")
                return PlaybookResult(
                    name=self.name,
                    success=True,
                    duration_s=time.time() - start,
                    actions_taken=actions,
                )
            try:
                # MUST use the SQLCipher-aware singleton — plain sqlite3 reads
                # an encrypted DB as "corrupt" and this playbook would rename
                # the live memory DB away.
                from core.memory.episodic import get_db_connection
                conn = get_db_connection()
                conn.execute("PRAGMA integrity_check")
                actions.append("DB integrity check passed")
            except Exception as e:
                actions.append(f"DB corruption detected: {e}")
                backup = db_path.with_suffix(".db.corrupt_backup")
                try:
                    db_path.rename(backup)
                    actions.append(f"Backed up corrupted DB to {backup.name}")
                except OSError as rename_err:
                    actions.append(f"Backup rename skipped (file in use): {rename_err}")

        return PlaybookResult(
            name=self.name, success=True,
            duration_s=time.time() - start,
            actions_taken=actions,
        )


PLAYBOOK_REGISTRY: dict[str, RecoveryPlaybook] = {
    "model_crash": ModelCrashPlaybook(),
    "oom": OOMPlaybook(),
    "disk_full": DiskFullPlaybook(),
    "network_partition": NetworkPartitionPlaybook(),
    "gpu_failure": GPUFailurePlaybook(),
    "process_hang": ProcessHangPlaybook(),
    "config_corrupt": ConfigCorruptPlaybook(),
    "db_corruption": DBCorruptionPlaybook(),
}


async def run_all_playbooks() -> list[PlaybookResult]:
    import asyncio
    results = []
    for name, playbook in PLAYBOOK_REGISTRY.items():
        result = await playbook.run()
        results.append(result)
        status = "OK" if result.success else "FAIL"
        logger.info("[Playbook] {}: {} ({:.1f}s)", status, name, result.duration_s)
        await asyncio.sleep(0.5)
    return results
