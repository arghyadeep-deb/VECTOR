
import sys

import asyncio
import datetime
import re
import subprocess
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

from core.config import CONFIG
from core.city.agent_base import AgentBase

@dataclass
class BlocklistEntry:
    ip: str
    reason: str
    added_at: str = ""
    source: str = "file"

_SUSPICIOUS_PORTS: set[int] = set(CONFIG.get("security", {}).get("suspicious_ports", [4444, 6666, 1337, 31337, 9001, 9050]))

def _parse_netstat(output: str) -> list[dict[str, Any]]:
    connections: list[dict[str, Any]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Proto") or stripped.startswith("Active") or "=======" in stripped:
            continue
        parts = re.split(r"\s+", stripped)
        if len(parts) < 4:
            continue
        proto = parts[0]
        local = parts[1]
        foreign = parts[2]
        state = parts[3] if len(parts) > 3 else ""
        connections.append({
            "proto": proto,
            "local": local,
            "foreign": foreign,
            "state": state,
        })
    return connections

class NetworkMonitor(AgentBase):
    def __init__(self, interval_sec: int | None = None):
        super().__init__(str(uuid.uuid4()), "NetworkMonitor", "security")
        self.capabilities = ["ESTABLISHED", "blocklist", "connection_rate", "network", "port_scan", "report", "scan", "security", "threat"]
        self._interval = interval_sec or CONFIG.get("security_siem", {}).get("network_monitor_interval_sec", 30)
        self._running = False
        self._blocklist: list[BlocklistEntry] = []
        self._connection_history: list[dict[str, Any]] = []
        self._rate_tracker: dict[str, list[float]] = defaultdict(list)
        self._last_scan: dict[str, int] = defaultdict(int)
        from core.runtime_paths import data_path

        self._blocklist_path = data_path("security", "ip_blocklist.txt")
        self._load_blocklist()

    def _load_blocklist(self) -> None:
        self._blocklist = []
        if not self._blocklist_path.exists():
            logger.warning("[VECTOR][network_monitor] blocklist file not found: {}", self._blocklist_path)
            return
        try:
            text = self._blocklist_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    ip, reason = line.split(":", 1)
                else:
                    ip, reason = line, "blocklisted"
                self._blocklist.append(BlocklistEntry(ip=ip.strip(), reason=reason.strip(), source="file"))
            logger.info("[VECTOR][network_monitor] loaded {} blocklist entries", len(self._blocklist))
        except Exception as e:
            logger.error("[VECTOR][network_monitor] failed to load blocklist: {}", e)

    def scan_connections(self) -> list[dict[str, Any]]:
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            connections = _parse_netstat(result.stdout)
            now = datetime.datetime.now(datetime.timezone.utc)
            for conn in connections:
                conn["timestamp"] = now.isoformat()
                conn["suspicious_score"] = self._score_connection(conn)
            self._connection_history = connections
            logger.debug("[VECTOR][network_monitor] scanned {} connections", len(connections))
            return connections
        except subprocess.TimeoutExpired:
            logger.error("[VECTOR][network_monitor] netstat timed out")
            return []
        except FileNotFoundError:
            logger.error("[VECTOR][network_monitor] netstat not found")
            return []
        except Exception as e:
            logger.error("[VECTOR][network_monitor] scan error: {}", e)
            return []

    def _score_connection(self, conn: dict[str, Any]) -> float:
        score = 0.0
        foreign = conn.get("foreign", "")
        if ":" in foreign:
            try:
                port_str = foreign.rsplit(":", 1)[-1]
                if port_str.isdigit():
                    port = int(port_str)
                    if port in _SUSPICIOUS_PORTS:
                        score += 0.6
                    if port < 1024 and conn.get("state") == "LISTENING":
                        score += 0.1
            except (ValueError, IndexError):
                pass
            ip_part = foreign.rsplit(":", 1)[0].strip("[]")
            if self._is_blocklisted(ip_part):
                score += 0.8
            if ip_part.startswith("0.") or ip_part.startswith("224.") or ip_part.startswith("239."):
                pass
            elif ip_part.startswith("10.") or ip_part.startswith("172.") or ip_part.startswith("192.168."):
                score += 0.0
            else:
                if conn.get("state") in ("ESTABLISHED",):
                    score += 0.2
        return min(score, 1.0)

    def _is_blocklisted(self, ip: str) -> bool:
        return any(entry.ip == ip for entry in self._blocklist)

    def detect_port_scan(self) -> list[dict[str, Any]]:
        now = time.time()
        window = 60.0
        threats: list[dict[str, Any]] = []
        for conn in self._connection_history:
            foreign = conn.get("foreign", "")
            if ":" not in foreign:
                continue
            src_ip = foreign.rsplit(":", 1)[0].strip("[]")
            self._rate_tracker[src_ip].append(now)
            self._rate_tracker[src_ip] = [t for t in self._rate_tracker[src_ip] if t > now - window]
            rate = len(self._rate_tracker[src_ip])
            if rate > 100 and now - self._last_scan.get(src_ip, 0) > 300:
                self._last_scan[src_ip] = int(now)
                threats.append({
                    "src_ip": src_ip,
                    "rate_per_min": rate,
                    "window_sec": window,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                })
                logger.warning("[VECTOR][network_monitor] port scan suspected from {}: {} conn/min", src_ip, rate)
        return threats

    def check_blocklist(self) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for conn in self._connection_history:
            foreign = conn.get("foreign", "")
            if ":" not in foreign:
                continue
            ip_part = foreign.rsplit(":", 1)[0].strip("[]")
            entry = self._is_blocklisted(ip_part)
            if entry:
                bl = next((e for e in self._blocklist if e.ip == ip_part), None)
                matches.append({
                    "ip": ip_part,
                    "reason": bl.reason if bl else "blocklisted",
                    "local": conn.get("local", ""),
                    "state": conn.get("state", ""),
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                })
        return matches

    def track_connection_rate(self) -> dict[str, Any]:
        rates: dict[str, int] = defaultdict(int)
        for conn in self._connection_history:
            foreign = conn.get("foreign", "")
            if ":" in foreign:
                ip_part = foreign.rsplit(":", 1)[0].strip("[]")
                rates[ip_part] += 1
        sorted_rates = sorted(rates.items(), key=lambda x: x[1], reverse=True)
        return {
            "top_talkers": [{"ip": ip, "connections": count} for ip, count in sorted_rates[:10]],
            "total_unique_ips": len(rates),
            "total_connections": len(self._connection_history),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def generate_report(self) -> dict[str, Any]:
        connections = self.scan_connections()
        threats = self.detect_port_scan()
        blocklist_matches = self.check_blocklist()
        rates = self.track_connection_rate()
        high_score = [c for c in connections if c.get("suspicious_score", 0) > 0.5]
        return {
            "total_connections": len(connections),
            "high_score_connections": len(high_score),
            "port_scan_threats": len(threats),
            "blocklist_matches": len(blocklist_matches),
            "threats": threats,
            "blocklist_matches_detail": blocklist_matches,
            "top_talkers": rates.get("top_talkers", []),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    async def run_forever(self) -> None:
        self._running = True
        logger.info("[VECTOR][network_monitor] started — {}s interval", self._interval)
        while self._running:
            try:
                self.generate_report()
            except Exception as e:
                logger.error("[VECTOR][network_monitor] tick error: {}", e)
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        self._running = False

    async def run(self, task: dict | None = None) -> dict:
        task = task or {}
        task_type = task.get("type") or "report"
        params = task.get("params") or {}
        supported = ["blocklist", "connection_rate", "port_scan", "report", "scan"]

        if task_type in ("report", "generate_report"):
            return {"status": "ok", **self.generate_report()}
        if task_type in ("scan", "scan_connections"):
            return {"status": "ok", "connections": self.scan_connections()}
        if task_type == "port_scan":
            return {"status": "ok", "threats": self.detect_port_scan()}
        if task_type == "blocklist":
            return {"status": "ok", "matches": self.check_blocklist()}
        if task_type == "connection_rate":
            return {"status": "ok", **self.track_connection_rate()}

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "is my network being scanned or attacked right now?" previously
        # hit the bare "unhandled type" error stub. Route it to the same
        # generate_report() this agent already treats as its safe,
        # argument-free DEFAULT when task_type is entirely absent (see
        # task_type = task.get("type") or "report" above) — passive, local
        # netstat/blocklist inspection only, no external probing, no
        # process kill, no firewall change.
        query = (
            params.get("query") or params.get("content")
            or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            return {"status": "ok", **self.generate_report()}

        return {
            "status": "error",
            "error": f"unhandled type: {task_type}",
            "supported": supported,
        }

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    nm = NetworkMonitor()
    report = nm.generate_report()
    print(f"NetworkMonitor OK — {report['total_connections']} connections, {report['port_scan_threats']} threats, {report['blocklist_matches']} blocklist hits")
    print("network_monitor.py OK")
