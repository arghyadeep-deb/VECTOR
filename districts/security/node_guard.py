
import sys

import asyncio
import datetime
import uuid

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

from core.config import CONFIG
from core.city.agent_base import AgentBase

# ---------------------------------------------------------------------------
# Constants sourced from CONFIG — never hardcoded in business logic (RULE from code_style)
# ---------------------------------------------------------------------------
_SUSPICIOUS_PORTS: set[int] = set(
    CONFIG.get("security", {}).get(
        "suspicious_ports", [4444, 6666, 1337, 31337, 9001, 9050]
    )
)

_SUSPICIOUS_DIRS: tuple[str, ...] = (
    "\\temp\\",
    "\\tmp\\",
    "\\appdata\\local\\temp\\",
    "/tmp/",
    "/var/tmp/",
)

class NodeGuard(AgentBase):
    """Monitors network connections and detects anomalies.

    Scans active TCP/UDP connections via psutil, flags suspicious ports
    and unexpected processes communicating externally.
    All actions routed through PermissionGateway (RULE 3).
    """

    def __init__(self, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="NodeGuard",
            district="security",
        )
        self.capabilities = ["bytes_sent", "connections", "laddr", "malware", "node_guard", "python.exe", "scan", "security"]
        if ghost:
            self.inherit_ghost(ghost)
        self._connection_scan_ok = True
        logger.info("[VECTOR][node_guard] NodeGuard initialised")

    # ------------------------------------------------------------------
    # Active connection enumeration
    # ------------------------------------------------------------------

    def get_active_connections(self) -> list[dict]:
        """Return all active inet connections enriched with process names.

        Returns:
            List of dicts:
            {laddr, raddr, status, pid, process_name}
        Never raises.
        """
        results: list[dict] = []
        self._connection_scan_ok = True
        try:
            import psutil  # type: ignore

            for conn in psutil.net_connections(kind="inet"):
                try:
                    laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else ""
                    raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else ""
                    pid = conn.pid or 0
                    status = conn.status or ""

                    # Enrich with process name
                    process_name = ""
                    if pid:
                        try:
                            proc = psutil.Process(pid)
                            process_name = proc.name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            process_name = ""

                    results.append({
                        "laddr": laddr,
                        "raddr": raddr,
                        "status": status,
                        "pid": pid,
                        "process_name": process_name,
                    })
                except Exception as e:
                    logger.warning(f"[VECTOR][node_guard] connection entry error: {e}")
                    continue

        except ImportError:
            self._connection_scan_ok = False
            logger.error("[VECTOR][node_guard] psutil not installed — cannot list connections")
        except Exception as e:
            self._connection_scan_ok = False
            logger.error(f"[VECTOR][node_guard] get_active_connections error: {e}")

        logger.info(f"[VECTOR][node_guard] {len(results)} active connections found")
        return results

    # ------------------------------------------------------------------
    # Suspicious connection filtering
    # ------------------------------------------------------------------

    def flag_suspicious_connections(self, connections: list[dict]) -> list[dict]:
        """Filter *connections* for suspicious indicators.

        Flags:
          - Connections to known bad ports (from CONFIG security.suspicious_ports)
          - Python/script processes running from temp directories

        Returns:
            Subset of *connections* with added keys:
            {suspicious: True, reason: str}
        Never raises.
        """
        flagged: list[dict] = []
        try:
            for conn in connections:
                suspicious = False
                reason = ""

                raddr = conn.get("raddr", "")
                process_name = (conn.get("process_name") or "").lower()

                # Check remote port against known bad ports
                if raddr and ":" in raddr:
                    try:
                        remote_port = int(raddr.split(":")[-1])
                        if remote_port in _SUSPICIOUS_PORTS:
                            suspicious = True
                            reason = f"connection to suspicious port {remote_port}"
                    except (ValueError, IndexError):
                        logger.opt(exception=True).debug(
                            "[VECTOR][node_guard] could not parse remote port from {}", raddr
                        )

                # Check if process is a script interpreter running from temp dir
                if not suspicious:
                    try:
                        import psutil  # type: ignore
                        pid = conn.get("pid", 0)
                        if pid:
                            try:
                                proc = psutil.Process(pid)
                                exe = (proc.exe() or "").lower()
                                for bad_dir in _SUSPICIOUS_DIRS:
                                    if bad_dir in exe:
                                        suspicious = True
                                        reason = f"process '{process_name}' exe in temp dir: {exe}"
                                        break
                                # Script interpreters (python, node, etc.) with temp-dir args
                                if not suspicious and process_name in ("python.exe", "python3", "node.exe", "wscript.exe", "cscript.exe"):
                                    cmdline = proc.cmdline()
                                    for arg in cmdline:
                                        for bad_dir in _SUSPICIOUS_DIRS:
                                            if bad_dir in arg.lower():
                                                suspicious = True
                                                reason = f"script process '{process_name}' running from temp: {arg}"
                                                break
                                        if suspicious:
                                            break
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                logger.opt(exception=True).debug(
                                    "[VECTOR][node_guard] process details unavailable for PID {}", pid
                                )
                    except ImportError:
                        logger.opt(exception=True).debug(
                            "[VECTOR][node_guard] psutil unavailable during suspicious-process check"
                        )

                if suspicious:
                    flagged_conn = dict(conn)
                    flagged_conn["suspicious"] = True
                    flagged_conn["reason"] = reason
                    flagged.append(flagged_conn)

        except Exception as e:
            logger.error(f"[VECTOR][node_guard] flag_suspicious_connections error: {e}")

        logger.info(
            f"[VECTOR][node_guard] {len(flagged)} suspicious connections "
            f"out of {len(connections)} total"
        )
        return flagged

    # ------------------------------------------------------------------
    # Network I/O stats
    # ------------------------------------------------------------------

    def get_network_stats(self) -> dict:
        """Return bytes/packets counters from psutil.net_io_counters().

        Returns:
            {bytes_sent, bytes_recv, packets_sent, packets_recv}
            or empty dict on failure.
        Never raises.
        """
        try:
            import psutil  # type: ignore
            counters = psutil.net_io_counters()
            stats = {
                "bytes_sent": counters.bytes_sent,
                "bytes_recv": counters.bytes_recv,
                "packets_sent": counters.packets_sent,
                "packets_recv": counters.packets_recv,
            }
            logger.debug(
                f"[VECTOR][node_guard] net stats: "
                f"sent={counters.bytes_sent}, recv={counters.bytes_recv}"
            )
            return stats
        except ImportError:
            logger.error("[VECTOR][node_guard] psutil not installed — cannot get net stats")
            return {}
        except Exception as e:
            logger.error(f"[VECTOR][node_guard] get_network_stats error: {e}")
            return {}

    # ------------------------------------------------------------------
    # Monitoring tick
    # ------------------------------------------------------------------

    async def monitor_tick(self) -> dict:
        """One monitoring pass: enumerate → flag → report.

        Returns:
            {
                connections: int,
                suspicious: int,
                alerts: list[str],
                net_stats: dict,
                timestamp: str,
            }
        Never raises.
        """
        try:
            connections = self.get_active_connections()
            suspicious = self.flag_suspicious_connections(connections)
            net_stats = self.get_network_stats()

            alerts: list[str] = []
            for conn in suspicious:
                alerts.append(
                    f"[CONN] PID {conn['pid']} '{conn['process_name']}' "
                    f"{conn['laddr']} → {conn['raddr']}: {conn['reason']}"
                )

            result = {
                "connections": len(connections),
                "suspicious": len(suspicious),
                "alerts": alerts,
                "net_stats": net_stats,
                "scan_status": "ok" if self._connection_scan_ok else "error",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

            logger.info(
                f"[VECTOR][node_guard] tick — "
                f"connections={len(connections)}, suspicious={len(suspicious)}"
            )

            # HP wiring (RULE 9 — real, not fake)
            if not self._connection_scan_ok:
                self.deduct_points(5, "connection_scan_failed")
            elif len(suspicious) == 0:
                self.award_points(5, "clean network tick")
            else:
                self.add_lesson(f"suspicious connections detected: {alerts[:3]}")

            return result

        except Exception as e:
            logger.error(f"[VECTOR][node_guard] monitor_tick error: {e}")
            return {
                "connections": 0,
                "suspicious": 0,
                "alerts": [f"tick error: {e}"],
                "net_stats": {},
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

    async def run_forever(self) -> None:
        logger.info("[VECTOR][node_guard] run_forever started — fires every 5 minutes")
        while self.is_alive:
            try:
                await self.monitor_tick()
            except Exception as e:
                logger.error(f"[VECTOR][node_guard] tick error: {e}")
                self.deduct_points(5, "tick_error")
            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(1)
        logger.warning("[VECTOR][node_guard] died — HP=0")

    async def run(self, task: dict) -> dict:
        result = await self.monitor_tick()
        return {"status": "ok", **result}

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True

    agent = NodeGuard()
    if agent.name != "NodeGuard" or agent.district != "security":
        logger.error("[VECTOR][node_guard] agent init failed")
        ok = False

    # --- get_active_connections ---
    conns = agent.get_active_connections()
    if not isinstance(conns, list):
        logger.error("[VECTOR][node_guard] get_active_connections did not return list")
        ok = False
    else:
        logger.info(f"[VECTOR][node_guard] {len(conns)} active connections")
        if conns:
            first = conns[0]
            for key in ("laddr", "raddr", "status", "pid", "process_name"):
                if key not in first:
                    logger.error(f"[VECTOR][node_guard] missing key '{key}' in connection dict")
                    ok = False

    # --- flag_suspicious_connections ---
    # Inject a synthetic suspicious connection (bad port 4444)
    fake_conns = [
        {"laddr": "192.168.1.10:53210", "raddr": "1.2.3.4:4444", "status": "ESTABLISHED", "pid": 0, "process_name": "test_proc"},
        {"laddr": "127.0.0.1:8080", "raddr": "8.8.8.8:443", "status": "ESTABLISHED", "pid": 0, "process_name": "chrome.exe"},
    ]
    flagged = agent.flag_suspicious_connections(fake_conns)
    if len(flagged) != 1:
        logger.error(f"[VECTOR][node_guard] expected 1 flagged, got {len(flagged)}: {flagged}")
        ok = False
    else:
        logger.info(f"[VECTOR][node_guard] flag_suspicious_connections: {flagged[0]['reason']}")

    # --- get_network_stats ---
    stats = agent.get_network_stats()
    if not isinstance(stats, dict):
        logger.error("[VECTOR][node_guard] get_network_stats did not return dict")
        ok = False
    elif stats:
        for key in ("bytes_sent", "bytes_recv", "packets_sent", "packets_recv"):
            if key not in stats:
                logger.error(f"[VECTOR][node_guard] missing key '{key}' in net stats")
                ok = False
        logger.info(f"[VECTOR][node_guard] net stats: {stats}")

    # --- monitor_tick ---
    tick = asyncio.run(agent.monitor_tick())
    for key in ("connections", "suspicious", "alerts", "timestamp"):
        if key not in tick:
            logger.error(f"[VECTOR][node_guard] monitor_tick missing key '{key}'")
            ok = False
    logger.info(
        f"[VECTOR][node_guard] monitor_tick: "
        f"connections={tick.get('connections')}, suspicious={tick.get('suspicious')}"
    )

    print("✅ node_guard.py OK" if ok else "❌ FAILED")
