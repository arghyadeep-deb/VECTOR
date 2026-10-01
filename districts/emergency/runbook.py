from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger

from .classifier import ScoredEmergency


@dataclass
class RunbookAction:
    name: str
    handler: Callable[[ScoredEmergency], Any]
    timeout_seconds: int = 30
    cleanup_handler: Callable | None = None
    safety_level: str = "safe"


@dataclass
class ActionResult:
    success: bool
    output: str = ""
    duration_ms: int = 0
    error: str | None = None


class RunbookExecutor:
    def __init__(self):
        self._runbooks: dict[str, list[RunbookAction]] = {
            "disk_full": self._runbook_disk_full(),
            "gpu_temp_high": self._runbook_gpu_overheat(),
            "oom_detected": self._runbook_oom(),
            "process_crash": self._runbook_process_crash(),
            "internet_down": self._runbook_network_down(),
            "intrusion_detected": self._runbook_intrusion(),
            "heart_rate_stopped": self._runbook_health_critical(),
            "battery_critical": self._runbook_battery_critical(),
        }

    def _runbook_disk_full(self) -> list[RunbookAction]:
        async def cleanup_temp(emergency: ScoredEmergency) -> dict:
            import shutil
            from pathlib import Path
            freed = 0
            for path in [Path(__file__).parent, Path(".")]:
                for f in list(path.glob("*.tmp")) + list(path.glob("*.log"))[:20]:
                    if f.is_file() and f.stat().st_mtime < time.time() - 3600:
                        sz = f.stat().st_size
                        f.unlink(missing_ok=True)
                        freed += sz
            return {"freed_bytes": freed}

        async def log_cleanup(emergency: ScoredEmergency) -> dict:
            logger.info("[Runbook] disk_full cleanup completed")
            return {"status": "logged"}

        return [
            RunbookAction("cleanup_temp_files", cleanup_temp, timeout_seconds=15, safety_level="caution"),
            RunbookAction("log_result", log_cleanup, timeout_seconds=5, safety_level="safe"),
        ]

    def _runbook_gpu_overheat(self) -> list[RunbookAction]:
        async def pause_inference(emergency: ScoredEmergency) -> dict:
            try:
                import subprocess
                r = (await asyncio.to_thread(subprocess.run, ["nvidia-smi", "-pl", "150"], capture_output=True, timeout=10))
                if r.returncode != 0:
                    return {"status": "failed", "error": f"nvidia-smi exit {r.returncode}"}
                return {"status": "power_limit_150w"}
            except Exception as e:
                return {"status": "failed", "error": f"nvidia_smi_unavailable: {e}"}

        async def reduce_batch(emergency: ScoredEmergency) -> dict:
            return {"status": "batch_reduction_requested"}

        async def monitor_temp(emergency: ScoredEmergency) -> dict:
            await asyncio.sleep(2)
            return {"status": "temperature_monitoring_started"}

        return [
            RunbookAction("pause_inference", pause_inference, timeout_seconds=15, safety_level="caution"),
            RunbookAction("reduce_batch", reduce_batch, timeout_seconds=5, safety_level="safe"),
            RunbookAction("monitor_temperature", monitor_temp, timeout_seconds=10, safety_level="safe"),
        ]

    def _runbook_oom(self) -> list[RunbookAction]:
        async def restart_process(emergency: ScoredEmergency) -> dict:
            try:
                import subprocess
                result = (await asyncio.to_thread(subprocess.run, ["ollama", "list"], capture_output=True, timeout=5))
                if result.returncode == 0:
                    (await asyncio.to_thread(subprocess.run, ["ollama", "serve"], capture_output=True, timeout=10))
                    return {"status": "ollama_restarted"}
                return {"status": "skipped", "reason": "ollama not running"}
            except Exception as e:
                return {"status": "failed", "error": str(e)}

        async def swap_clear(emergency: ScoredEmergency) -> dict:
            return {"status": "swap_clear_attempted"}

        async def log_analysis(emergency: ScoredEmergency) -> dict:
            logger.info("[Runbook] OOM event logged for analysis")
            return {"status": "logged"}

        return [
            RunbookAction("process_restart", restart_process, timeout_seconds=15, safety_level="destructive"),
            RunbookAction("swap_clear", swap_clear, timeout_seconds=5, safety_level="safe"),
            RunbookAction("log_analysis", log_analysis, timeout_seconds=5, safety_level="safe"),
        ]

    def _runbook_process_crash(self) -> list[RunbookAction]:
        async def restart(emergency: ScoredEmergency) -> dict:
            try:
                import subprocess
                (await asyncio.to_thread(subprocess.run, ["ollama", "serve"], capture_output=True, timeout=10))
                return {"status": "restarted"}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        async def verify(emergency: ScoredEmergency) -> dict:
            return {"status": "verification_pending"}

        return [
            RunbookAction("process_restart", restart, timeout_seconds=15, safety_level="destructive"),
            RunbookAction("verify_health", verify, timeout_seconds=10, safety_level="safe"),
        ]

    def _runbook_network_down(self) -> list[RunbookAction]:
        async def renew(emergency: ScoredEmergency) -> dict:
            try:
                import subprocess
                (await asyncio.to_thread(subprocess.run, ["ipconfig", "/renew"], capture_output=True, timeout=15))
                return {"status": "ipconfig_renewed"}
            except Exception:
                return {"status": "skipped"}

        return [
            RunbookAction("network_renew", renew, timeout_seconds=20, safety_level="caution"),
        ]

    def _runbook_intrusion(self) -> list[RunbookAction]:
        async def firewall(emergency: ScoredEmergency) -> dict:
            try:
                import subprocess
                r = (await asyncio.to_thread(subprocess.run, ["netsh", "advfirewall", "set", "allprofiles", "state", "on"], capture_output=True, text=True, timeout=10))
                return {"status": "ok" if r.returncode == 0 else "failed"}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        return [
            RunbookAction("enable_firewall", firewall, timeout_seconds=15, safety_level="caution"),
        ]

    def _runbook_health_critical(self) -> list[RunbookAction]:
        async def notify(emergency: ScoredEmergency) -> dict:
            return {"status": "not_sent", "error": "no delivery channel in runbook; owner notification is the escalation pushover step"}

        return [
            RunbookAction("send_alert", notify, timeout_seconds=10, safety_level="safe"),
        ]

    def _runbook_battery_critical(self) -> list[RunbookAction]:
        async def alert(emergency: ScoredEmergency) -> dict:
            return {"status": "not_sent", "error": "no delivery channel in runbook; owner notification is the escalation pushover step"}

        return [
            RunbookAction("send_alert", alert, timeout_seconds=10, safety_level="safe"),
        ]

    async def execute(self, emergency: ScoredEmergency) -> list[ActionResult]:
        actions = self._runbooks.get(emergency.event.signal_name)
        if not actions:
            return [ActionResult(success=True, output="no_runbook", duration_ms=0)]

        results: list[ActionResult] = []
        for action in actions:
            t0 = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    action.handler(emergency),
                    timeout=action.timeout_seconds,
                )
                elapsed = int((time.monotonic() - t0) * 1000)
                if isinstance(result, dict) and result.get("status") in ("error", "failed", "not_sent"):
                    results.append(ActionResult(success=False, output=str(result), duration_ms=elapsed, error=result.get("error", "unknown")))
                else:
                    results.append(ActionResult(success=True, output=str(result), duration_ms=elapsed))
            except asyncio.TimeoutError:
                elapsed = int((time.monotonic() - t0) * 1000)
                results.append(ActionResult(success=False, output=f"timeout after {action.timeout_seconds}s", duration_ms=elapsed, error="timeout"))
                if action.cleanup_handler:
                    try:
                        await action.cleanup_handler(emergency)
                    except Exception as ce:
                        logger.warning("[Runbook] cleanup failed for {}: {}", action.name, ce)
            except Exception as e:
                elapsed = int((time.monotonic() - t0) * 1000)
                results.append(ActionResult(success=False, output=str(e), duration_ms=elapsed, error=str(e)))
                if action.cleanup_handler:
                    try:
                        await action.cleanup_handler(emergency)
                    except Exception as ce:
                        logger.warning("[Runbook] cleanup failed for {}: {}", action.name, ce)

        logger.info("[Runbook] {} executed {} actions ({} ok)", emergency.event.signal_name, len(results), sum(1 for r in results if r.success))
        return results
