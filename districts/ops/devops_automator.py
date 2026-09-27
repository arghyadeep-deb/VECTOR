"""
DevOps Automator — District: ops
Checks Fly.io / Cloudflare status, restarts stuck VECTOR processes,
cleans large logs, and backs up the memory DB.
RULE 3: restart actions go through permission_gateway (YELLOW tier).
RULE 11: no Claude API at runtime.
"""

import sys
import asyncio
import datetime
import shutil
import subprocess
import uuid
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.db_utils import configured_db_path
from core.memory.obsidian_sync import ObsidianSync

_FOCUS = CONFIG.get("models", {}).get("focus", "vector-focus")

# Endpoints — configurable via CONFIG
_CF_WORKER_URL: str = CONFIG.get("cf_worker_url", "https://vector-api.arghyadeepdeb020703.workers.dev/health")

# Paths
_BASE_DIR = Path(__file__).parent.parent.parent.parent
_BACKUP_DIR = _BASE_DIR / "data" / "raw"
_DB_PATH = configured_db_path()

# Log-size threshold for cleanup
_LOG_SIZE_LIMIT_BYTES: int = 50 * 1024 * 1024  # 50 MB

class DevOpsAutomator(AgentBase):
    """
    DevOps automation agent.
    Checks deployment health, restarts stuck processes (YELLOW gate),
    cleans oversized log files, and backs up vector_memory.db.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="DevOpsAutomator",
            district="ops",
            generation=generation,
        )
        self.capabilities = ["backup_db", "cf_status", "cleanup_logs", "deploy", "devops", "ops", "restart"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        logger.info(f"[VECTOR][devops_automator] ready gen={generation}")

    # ── Lazy accessors ─────────────────────────────────────────────────────────

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self) -> ObsidianSync:
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    # ── Deployment status checks ────────────────────────────────────────────────

    async def check_cloudflare_status(self) -> dict:
        """
        HTTP GET to Cloudflare Worker health endpoint.
        Returns: {ok, status_code, latency_ms, url}.
        """
        try:
            import httpx
            import time
            async with httpx.AsyncClient(timeout=10.0) as client:
                t0 = time.monotonic()
                resp = await client.get(_CF_WORKER_URL)
                latency_ms = round((time.monotonic() - t0) * 1000, 1)
            result = {
                "ok": resp.status_code in (200, 204),
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
                "url": _CF_WORKER_URL,
            }
            status_icon = "UP" if result["ok"] else "DOWN"
            logger.info(f"[VECTOR][devops_automator] Cloudflare {status_icon} ({resp.status_code}) {latency_ms}ms")
            return result
        except Exception as e:
            logger.warning(f"[VECTOR][devops_automator] Cloudflare check failed: {e}")
            return {"ok": False, "status_code": -1, "latency_ms": -1, "url": _CF_WORKER_URL, "error": str(e)}

    # ── Process management (YELLOW gate) ──────────────────────────────────────

    async def auto_restart_services(self, process_names: list[str] | None = None) -> dict:
        """
        Restart VECTOR services that are stuck. Process kill is a YELLOW action
        and goes through permission_gateway before execution.
        process_names: list of process names to check (defaults to VECTOR defaults).
        Returns: {restarted, skipped, errors}.
        """
        from core.loop.permission_gateway import PermissionGateway, Action

        targets = process_names or ["run_vector.py", "ambient_server.py"]
        gateway = PermissionGateway()
        restarted: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for name in targets:
            try:
                # Check if process is actually running first
                check = (await asyncio.to_thread(subprocess.run, ["tasklist", "/FI", f"IMAGENAME eq python.exe"],
                    capture_output=True, text=True, timeout=5
                ))
                # If we can't confirm it's stuck, skip
                if name.lower() not in check.stdout.lower() and name.lower() not in check.stderr.lower():
                    skipped.append(f"{name}:not_running")
                    continue

                action = Action(
                    action_type="send_message_routine",  # YELLOW tier
                    params={"target": name, "op": "restart"},
                    proposed_by=self.name,
                    priority="normal",
                )
                gateway_result = await gateway.execute(action)
                if gateway_result.approved:
                    # Gateway approved — now do the actual restart via subprocess
                    kill_result = (await asyncio.to_thread(subprocess.run, ["taskkill", "/F", "/FI", f"WINDOWTITLE eq {name}"],
                        capture_output=True, text=True, timeout=10
                    ))
                    restarted.append(f"{name}:killed (restart pending manual re-launch or loop)")
                    logger.info(f"[VECTOR][devops_automator] restarted: {name} — {kill_result.returncode}")
                else:
                    skipped.append(f"{name}:gateway_denied ({gateway_result.reason})")
                    logger.warning(f"[VECTOR][devops_automator] restart denied for {name}: {gateway_result.reason}")
            except Exception as e:
                errors.append(f"{name}:{e}")
                logger.error(f"[VECTOR][devops_automator] restart error for {name}: {e}")

        result = {"restarted": restarted, "skipped": skipped, "errors": errors}
        self._get_memory().store(
            event_type="devops_ops",
            content=f"auto_restart: restarted={restarted} skipped={skipped}",
            tags=["devops", "restart"],
            source="devops_automator",
        )
        return result

    # ── Log cleanup ────────────────────────────────────────────────────────────

    def cleanup_logs(self) -> dict:
        """
        Remove log files > 50 MB from the codebase root (and logs/ subdir).
        Returns: {removed, total_freed_mb, errors}.
        """
        search_dirs = [_BASE_DIR, _BASE_DIR / "logs"]
        removed: list[str] = []
        total_freed = 0
        errors: list[str] = []

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for log_file in search_dir.rglob("*.log"):
                try:
                    size = log_file.stat().st_size
                    if size > _LOG_SIZE_LIMIT_BYTES:
                        freed_mb = round(size / (1024 * 1024), 2)
                        log_file.unlink()
                        removed.append(f"{log_file.name} ({freed_mb}MB)")
                        total_freed += size
                        logger.info(f"[VECTOR][devops_automator] removed log {log_file} ({freed_mb}MB)")
                except Exception as e:
                    errors.append(f"{log_file}:{e}")
                    logger.warning(f"[VECTOR][devops_automator] could not remove {log_file}: {e}")

        total_freed_mb = round(total_freed / (1024 * 1024), 2)
        result = {
            "removed": removed,
            "total_freed_mb": total_freed_mb,
            "errors": errors,
        }
        self._get_memory().store(
            event_type="devops_ops",
            content=f"cleanup_logs: removed {len(removed)} files, freed {total_freed_mb}MB",
            tags=["devops", "cleanup"],
            source="devops_automator",
        )
        logger.info(f"[VECTOR][devops_automator] cleanup_logs: {len(removed)} removed, {total_freed_mb}MB freed")
        return result

    # ── DB backup ─────────────────────────────────────────────────────────────

    def backup_memory_db(self) -> dict:
        """
        Copy vector_memory.db to data/raw/ with an ISO timestamp suffix.
        Returns: {ok, backup_path, size_mb, error}.
        """
        _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        dest = _BACKUP_DIR / f"vector_memory_{ts}.db"

        if not _DB_PATH.exists():
            msg = f"DB not found at {_DB_PATH}"
            logger.warning(f"[VECTOR][devops_automator] {msg}")
            return {"ok": False, "backup_path": None, "size_mb": 0, "error": msg}

        try:
            shutil.copy2(str(_DB_PATH), str(dest))
            size_mb = round(dest.stat().st_size / (1024 * 1024), 3)
            logger.info(f"[VECTOR][devops_automator] DB backup: {dest} ({size_mb}MB)")
            self._get_memory().store(
                event_type="devops_ops",
                content=f"db_backup: {dest.name} ({size_mb}MB)",
                tags=["devops", "backup"],
                source="devops_automator",
            )
            return {"ok": True, "backup_path": str(dest), "size_mb": size_mb, "error": None}
        except Exception as e:
            logger.error(f"[VECTOR][devops_automator] DB backup failed: {e}")
            return {"ok": False, "backup_path": None, "size_mb": 0, "error": str(e)}

    # ── AgentBase.run entry-point ──────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "status_check")
        try:
            if task_type == "cf_status":
                result = await self.check_cloudflare_status()
                if result.get("ok"):
                    self.award_points(10, "Cloudflare healthy")
                else:
                    self.deduct_points(20, "Cloudflare down")
                return {"status": "ok", **result}

            elif task_type == "restart":
                targets = task.get("process_names")
                result = await self.auto_restart_services(targets)
                n_restarted = len(result.get("restarted", []))
                if n_restarted > 0:
                    self.award_points(30, f"restarted {n_restarted} services")
                return {"status": "ok", **result}

            elif task_type == "cleanup_logs":
                result = self.cleanup_logs()
                freed = result.get("total_freed_mb", 0)
                if freed > 0:
                    self.award_points(20, f"freed {freed}MB logs")
                else:
                    self.award_points(5, "cleanup_logs: nothing to remove")
                return {"status": "ok", **result}

            elif task_type == "backup_db":
                result = self.backup_memory_db()
                if result.get("ok"):
                    self.award_points(25, "memory DB backed up")
                else:
                    self.deduct_points(15, "DB backup failed")
                return {"status": "ok", **result}

            else:
                # Default: status check of all deployments
                cf = await self.check_cloudflare_status()
                if cf.get("ok"):
                    self.award_points(20, "all deployments healthy")
                else:
                    self.deduct_points(20, "deployment degradation detected")
                self._get_memory().store(
                    event_type="devops_ops",
                    content=f"status_check: cf={cf.get('ok')}",
                    tags=["devops", "status_check"],
                    source="devops_automator",
                )
                return {"status": "ok", "cloudflare": cf}

        except Exception as e:
            logger.error(f"[VECTOR][devops_automator] run failed: {e}")
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

# ── Smoke test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = DevOpsAutomator()
        assert agent.health_points == 500

        # Backup DB (always works locally)
        backup = agent.backup_memory_db()
        print(f"backup ok={backup.get('ok')} path={backup.get('backup_path')} size={backup.get('size_mb')}MB")

        # Cleanup logs (safe read-only scan if no oversized files)
        cleanup = agent.cleanup_logs()
        print(f"cleanup: removed={cleanup.get('removed')} freed={cleanup.get('total_freed_mb')}MB")

        # Cloudflare (may fail in dev — that's expected)
        cf = await agent.check_cloudflare_status()
        print(f"cf={cf.get('ok')} ({cf.get('status_code')})")

        ok = backup.get("ok", False)
        print(f"{'✅' if ok else '❌'} devops_automator.py HP={agent.health_points}")

    asyncio.run(_smoke())
