
import sys
from pathlib import Path

import asyncio
import datetime
import uuid

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.control.security.malware_detector import MalwareDetector
from core.control.security.threat_detector import check_process_anomalies

# ---------------------------------------------------------------------------
# Constants (sourced from CONFIG — never hardcoded in business logic)
# ---------------------------------------------------------------------------
_SUSPICIOUS_NAMES: set[str] = set(
    CONFIG.get("security", {}).get(
        "suspicious_process_names",
        ["cryptominer", "keylogger", "miner", "rat", "netcat"],
    )
)

_SUSPICIOUS_DIRS: tuple[str, ...] = (
    "\\temp\\",
    "\\tmp\\",
    "\\appdata\\local\\temp\\",
    "/tmp/",
    "/var/tmp/",
)

class ThreatScout(AgentBase):
    """Monitors processes, network, and files for threats.

    Wraps core/control/security/malware_detector.py (3-layer file scanning)
    and core/control/security/threat_detector.py (process anomaly detection).
    All actions routed through PermissionGateway. RULE 3.
    """

    def __init__(self, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ThreatScout",
            district="security",
        )
        self.capabilities = ["low", "malware", "scan", "scan_prompt", "security", "security_scan", "ssrf_check", "system_error", "taint_check", "threat", "threat_level"]
        self._malware = MalwareDetector()
        self._process_scan_ok = True
        if ghost:
            self.inherit_ghost(ghost)
        # Phase 2B: subscribe to security-relevant events
        self.subscribe_to("system_error")
        self.subscribe_to("security_alert")
        self.subscribe_to("login_attempt")
        logger.info("[VECTOR][threat_scout] ThreatScout initialised")

    async def handle_event(self, event: dict) -> dict:
        """Phase 2B: React to security events by running a threat scan."""
        await super().handle_event(event)
        et = event.get("event_type", "")
        if et in ("system_error", "security_alert", "login_attempt"):
            try:
                data = event.get("data", {})
                scan_target = data.get("error", data.get("detail", str(data)))[:200]
                logger.info(f"[VECTOR][threat_scout] event-triggered scan: {et}")
                await self.run({"type": "scan_process", "params": {"target": scan_target, "source": "event"}})
            except Exception as e:
                logger.debug(f"[VECTOR][threat_scout] handle_event scan failed: {e}")
        return {"status": "handled", "agent": self.name, "event": et}

    # ------------------------------------------------------------------
    # Process scanning
    # ------------------------------------------------------------------

    def scan_running_processes(self) -> list[dict]:
        """Scan all running processes for suspicious indicators.

        Returns:
            List of dicts: {pid, name, exe, suspicious: bool, reason: str}
        Never raises.
        """
        self._process_scan_ok = True
        try:
            return check_process_anomalies()
        except Exception as e:
            self._process_scan_ok = False
            logger.error(f"[VECTOR][threat_scout] scan_running_processes error: {e}")
            return []

    # ------------------------------------------------------------------
    # Startup entry scanning (Windows registry)
    # ------------------------------------------------------------------

    def scan_startup_entries(self) -> list[dict]:
        """Read HKCU\\...\\Run registry key and flag suspicious entries.

        Returns:
            List of dicts: {name, path, suspicious: bool, reason: str}
        Never raises.
        """
        entries: list[dict] = []
        try:
            import winreg  # Windows-only — graceful skip on Linux/Mac
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                    i = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                            path_lower = value.lower()
                            suspicious = False
                            reason = ""

                            # Flag if the exe path is in a temp directory
                            for bad_dir in _SUSPICIOUS_DIRS:
                                if bad_dir in path_lower:
                                    suspicious = True
                                    reason = f"startup entry in temp dir: {value}"
                                    break

                            # Flag if the name itself matches known bad patterns
                            if not suspicious:
                                for bad in _SUSPICIOUS_NAMES:
                                    if bad in name.lower() or bad in path_lower:
                                        suspicious = True
                                        reason = f"startup name matches suspicious pattern: {bad}"
                                        break

                            entries.append({
                                "name": name,
                                "path": value,
                                "suspicious": suspicious,
                                "reason": reason,
                            })
                            i += 1
                        except OSError:
                            break  # No more values
            except FileNotFoundError:
                logger.warning("[VECTOR][threat_scout] Registry Run key not found")
            except Exception as e:
                logger.error(f"[VECTOR][threat_scout] registry read error: {e}")

        except ImportError:
            logger.info("[VECTOR][threat_scout] winreg not available (non-Windows) — startup scan skipped")
        except Exception as e:
            logger.error(f"[VECTOR][threat_scout] scan_startup_entries error: {e}")

        logger.info(
            f"[VECTOR][threat_scout] startup entries: {len(entries)} total, "
            f"{sum(1 for e in entries if e['suspicious'])} suspicious"
        )
        return entries

    # ------------------------------------------------------------------
    # File scanning (delegates to MalwareDetector)
    # ------------------------------------------------------------------

    async def scan_file(self, file_path: str) -> dict:
        """Delegate file scan to MalwareDetector (3-layer).

        Returns:
            Dict with keys: file, hash, verdict, virustotal, mime, lgbm
        Never raises.
        """
        try:
            return await self._malware.scan_file(file_path)
        except Exception as e:
            logger.error(f"[VECTOR][threat_scout] scan_file error: {e}")
            return {"file": file_path, "verdict": "unknown", "error": str(e)}

    # ------------------------------------------------------------------
    # Full threat assessment
    # ------------------------------------------------------------------

    async def run_threat_assessment(self) -> dict:
        """Combine process + startup scans into a consolidated threat report.

        Returns:
            {
                threat_level: "low" | "medium" | "high",
                alerts: list[str],
                process_count: int,
                suspicious_processes: int,
                startup_count: int,
                suspicious_startups: int,
                timestamp: str,
            }
        Never raises.
        """
        alerts: list[str] = []
        try:
            processes = self.scan_running_processes()
            startups = self.scan_startup_entries()

            suspicious_procs = [p for p in processes if p.get("suspicious")]
            suspicious_starts = [s for s in startups if s.get("suspicious")]

            for p in suspicious_procs:
                alerts.append(
                    f"[PROCESS] PID {p['pid']} '{p['name']}': {p['reason']}"
                )

            for s in suspicious_starts:
                alerts.append(
                    f"[STARTUP] '{s['name']}' → {s['path']}: {s['reason']}"
                )

            # Determine threat level
            n_alerts = len(alerts)
            if not self._process_scan_ok:
                threat_level = "unknown"
                alerts.append("[SCAN] Running-process scan failed; clean state cannot be established")
            elif n_alerts == 0:
                threat_level = "low"
            elif n_alerts <= 3:
                threat_level = "medium"
            else:
                threat_level = "high"

            result = {
                "threat_level": threat_level,
                "alerts": alerts,
                "process_count": len(processes),
                "suspicious_processes": len(suspicious_procs),
                "startup_count": len(startups),
                "suspicious_startups": len(suspicious_starts),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

            logger.info(
                f"[VECTOR][threat_scout] assessment complete — "
                f"level={threat_level}, alerts={n_alerts}"
            )

            # Award / deduct HP based on outcome (RULE 9 — real HP wiring)
            if threat_level == "unknown":
                self.deduct_points(5, "process_scan_failed")
            elif threat_level == "low":
                self.award_points(10, "clean threat assessment")
            elif threat_level == "medium":
                self.award_points(5, "medium threat assessment completed")
            else:
                self.award_points(5, "high-threat assessment completed")
                self.add_lesson(f"High threat detected: {alerts[:3]}")

            return result

        except Exception as e:
            logger.error(f"[VECTOR][threat_scout] run_threat_assessment error: {e}")
            return {
                "threat_level": "unknown",
                "alerts": [f"assessment error: {e}"],
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

    async def run_forever(self) -> None:
        logger.info("[VECTOR][threat_scout] run_forever started — fires every 6 hours")
        while self.is_alive:
            try:
                await self.run_threat_assessment()
            except Exception as e:
                logger.error(f"[VECTOR][threat_scout] tick error: {e}")
                self.deduct_points(5, "tick_error")
            for _ in range(3600):
                if not self.is_alive:
                    break
                await asyncio.sleep(1)
        logger.warning("[VECTOR][threat_scout] died — HP=0")

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        if p.get("file"):
            return await self.scan_file(p["file"])
        return await self.run_threat_assessment()

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True

    agent = ThreatScout()
    if agent.name != "ThreatScout" or agent.district != "security":
        logger.error("[VECTOR][threat_scout] agent init failed")
        ok = False

    # --- scan_running_processes ---
    procs = agent.scan_running_processes()
    if not isinstance(procs, list):
        logger.error("[VECTOR][threat_scout] scan_running_processes not list")
        ok = False
    else:
        logger.info(f"[VECTOR][threat_scout] {len(procs)} processes scanned")

    # --- scan_startup_entries ---
    startups = agent.scan_startup_entries()
    if not isinstance(startups, list):
        logger.error("[VECTOR][threat_scout] scan_startup_entries not list")
        ok = False
    else:
        logger.info(f"[VECTOR][threat_scout] {len(startups)} startup entries found")

    # --- scan_file ---
    config_path = str(Path(__file__).parent.parent.parent.parent / "core" / "config.py")
    scan = asyncio.run(agent.scan_file(config_path))
    if "verdict" not in scan:
        logger.error(f"[VECTOR][threat_scout] scan_file missing 'verdict': {scan}")
        ok = False
    else:
        logger.info(f"[VECTOR][threat_scout] config.py scan verdict = {scan['verdict']}")

    # --- run_threat_assessment ---
    assessment = asyncio.run(agent.run_threat_assessment())
    for key in ("threat_level", "alerts", "timestamp"):
        if key not in assessment:
            logger.error(f"[VECTOR][threat_scout] assessment missing key '{key}'")
            ok = False
    if assessment.get("threat_level") not in ("low", "medium", "high", "unknown"):
        logger.error(f"[VECTOR][threat_scout] unexpected threat_level: {assessment.get('threat_level')}")
        ok = False
    else:
        logger.info(
            f"[VECTOR][threat_scout] threat_level={assessment['threat_level']}, "
            f"alerts={len(assessment.get('alerts', []))}"
        )

    print("✅ threat_scout.py OK" if ok else "❌ FAILED")
