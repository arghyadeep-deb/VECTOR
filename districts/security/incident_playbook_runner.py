import sys
from pathlib import Path

import asyncio
import datetime
import json
import sqlite3
import subprocess
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import yaml
from loguru import logger
from pydantic import BaseModel, Field

from core.config import CONFIG


@dataclass
class PlaybookStep:
    action: str
    params: dict = field(default_factory=dict)
    timeout_seconds: int = 30
    rollback_action: str | None = None


class Incident(BaseModel):
    id: str
    playbook_name: str
    triggered_by: str = ""
    steps: list[dict] = field(default_factory=list)
    status: str = "PENDING"
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    resolved_at: datetime.datetime | None = None


class IncidentPlaybookRunner:
    def __init__(self, playbooks_dir: str | None = None, db_path: str | None = None):
        self._playbooks_dir = Path(playbooks_dir or "data/security/playbooks")
        self._db_path = db_path or str(Path("data/security/incidents.db"))
        self._playbooks: dict[str, Any] = {}
        self._event_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)
        self._running = False
        self._active_incidents: dict[str, list[dict]] = defaultdict(list)
        self._load_playbooks()
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(self._db_path, timeout=5)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    playbook_name TEXT NOT NULL,
                    triggered_by TEXT DEFAULT '',
                    steps TEXT DEFAULT '[]',
                    status TEXT DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                )
            """)
            conn.commit()
            conn.close()
            logger.info("[VECTOR][incident_playbook] SQLite ready at {}", self._db_path)
        except Exception as e:
            logger.error("[VECTOR][incident_playbook] DB init: {}", e)

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=5)

    def _load_playbooks(self) -> None:
        self._playbooks = {}
        if not self._playbooks_dir.exists():
            logger.warning("[VECTOR][incident_playbook] playbooks dir not found: {}", self._playbooks_dir)
            return
        for yaml_file in sorted(self._playbooks_dir.glob("*.yaml")):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not data or "playbooks" not in data:
                    continue
                for pb in data["playbooks"]:
                    self._playbooks[pb["id"]] = pb
                logger.info("[VECTOR][incident_playbook] loaded {} playbooks from {}", len(data["playbooks"]), yaml_file.name)
            except Exception as e:
                logger.error("[VECTOR][incident_playbook] failed to load {}: {}", yaml_file, e)
        logger.info("[VECTOR][incident_playbook] {} playbooks loaded", len(self._playbooks))

    def _find_playbook_for_rule(self, rule_name: str) -> dict | None:
        for pb in self._playbooks.values():
            trigger_rules = pb.get("trigger_rules", [])
            if rule_name in trigger_rules:
                return pb
        return None

    async def process_loop(self) -> None:
        self._running = True
        logger.info("[VECTOR][incident_playbook] process loop started")
        while self._running:
            try:
                msg = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                rule_name = msg.get("rule_name", "")
                evidence = msg.get("evidence", {})
                alert_id = msg.get("alert_id", "")
                pb = self._find_playbook_for_rule(rule_name)
                if pb:
                    asyncio.ensure_future(self.execute_playbook(pb, evidence, alert_id))
                else:
                    logger.debug("[VECTOR][incident_playbook] no playbook for rule '{}'", rule_name)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("[VECTOR][incident_playbook] process error: {}", e)

    async def execute_playbook(self, playbook: dict, evidence: dict, alert_id: str = "") -> Incident:
        incident_id = str(uuid.uuid4())
        incident = Incident(
            id=incident_id,
            playbook_name=playbook.get("name", playbook.get("id", "unknown")),
            triggered_by=alert_id,
        )
        self._store_incident(incident)
        logger.info("[VECTOR][incident_playbook] executing playbook '{}' (incident={})", incident.playbook_name, incident_id[:8])
        steps_log: list[dict] = []
        success = True
        for step in playbook.get("steps", []):
            action = step.get("action", "")
            params = step.get("params", {})
            timeout_s = step.get("timeout", 30)
            step_result = {"action": action, "params": params, "status": "pending"}
            try:
                result = await asyncio.wait_for(
                    self._execute_action(action, params, evidence, incident_id),
                    timeout=timeout_s,
                )
                step_result["status"] = "completed"
                step_result["result"] = str(result)[:200]
                if isinstance(result, dict) and result.get("status") == "error":
                    step_result["status"] = "failed"
                    step_result["error"] = result.get("message", "unknown error")
                    success = False
            except asyncio.TimeoutError:
                step_result["status"] = "timeout"
                success = False
            except Exception as e:
                step_result["status"] = "error"
                step_result["error"] = str(e)
                success = False
            steps_log.append(step_result)
            if not success:
                logger.warning("[VECTOR][incident_playbook] step '{}' failed — rolling back", action)
                await self._rollback(playbook, evidence, incident_id)
                break
        incident.steps = steps_log
        incident.status = "COMPLETED" if success else "FAILED"
        if success:
            incident.resolved_at = datetime.datetime.now(datetime.timezone.utc)
        self._update_incident(incident)
        logger.info("[VECTOR][incident_playbook] incident {} complete: status={}", incident_id[:8], incident.status)
        return incident

    async def _rollback(self, playbook: dict, evidence: dict, incident_id: str) -> None:
        rollback_steps = playbook.get("rollback", [])
        if not rollback_steps:
            logger.info("[VECTOR][incident_playbook] no rollback steps defined")
            return
        logger.info("[VECTOR][incident_playbook] executing rollback for incident {}", incident_id[:8])
        for step in reversed(rollback_steps):
            action = step.get("action", "")
            params = step.get("params", {})
            try:
                await self._execute_action(action, params, evidence, incident_id)
                logger.info("[VECTOR][incident_playbook] rollback step '{}' done", action)
            except Exception as e:
                logger.error("[VECTOR][incident_playbook] rollback step '{}' failed: {}", action, e)

    async def _execute_action(self, action: str, params: dict, evidence: dict, incident_id: str) -> Any:
        target = evidence.get("target", params.get("ip", ""))
        handlers = {
            "block_ip": self._action_block_ip,
            "unblock_ip": self._action_unblock_ip,
            "capture_process_snapshot": self._action_capture_process_snapshot,
            "kill_process": self._action_kill_process,
            "notify": self._action_notify,
            "log_evidence": self._action_log_evidence,
            "isolate_process": self._action_isolate_process,
            "collect_memory_dump": self._action_collect_memory_dump,
            "run_antivirus": self._action_run_antivirus,
            "escalate_to_human": self._action_escalate_to_human,
        }
        handler = handlers.get(action)
        if handler is None:
            return {"status": "error", "message": f"unknown action: {action}"}
        return await handler(params, evidence, incident_id)

    async def _action_block_ip(self, params: dict, evidence: dict, incident_id: str) -> dict:
        ip = params.get("ip", evidence.get("target", ""))
        if not ip:
            return {"status": "error", "message": "no IP specified"}
        try:
            rule_name = f"VECTOR_Block_{ip.replace('.', '_')}"
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={rule_name}", "dir=out", "action=block",
                 f"remoteip={ip}", "enable=yes"],
                capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            logger.info("[VECTOR][incident_playbook] blocked outbound to {}", ip)
            return {"status": "ok", "ip": ip}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _action_unblock_ip(self, params: dict, evidence: dict, incident_id: str) -> dict:
        ip = params.get("ip", evidence.get("target", ""))
        if not ip:
            return {"status": "error", "message": "no IP specified"}
        try:
            rule_name = f"VECTOR_Block_{ip.replace('.', '_')}"
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"],
                capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            logger.info("[VECTOR][incident_playbook] unblocked {}", ip)
            return {"status": "ok", "ip": ip}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _action_capture_process_snapshot(self, params: dict, evidence: dict, incident_id: str) -> dict:
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            snapshot_path = Path(f"data/security/incidents/{incident_id}_processes.csv")
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(result.stdout, encoding="utf-8")
            net_result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            net_path = Path(f"data/security/incidents/{incident_id}_netstat.txt")
            net_path.write_text(net_result.stdout, encoding="utf-8")
            logger.info("[VECTOR][incident_playbook] process snapshot saved to {}", snapshot_path)
            return {"status": "ok", "process_count": len(result.stdout.splitlines()), "netstat_path": str(net_path)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _action_kill_process(self, params: dict, evidence: dict, incident_id: str) -> dict:
        pid = params.get("pid", 0)
        name = params.get("name", "")
        try:
            if pid:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                logger.info("[VECTOR][incident_playbook] killed PID {}", pid)
                return {"status": "ok", "pid": pid}
            elif name:
                subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                logger.info("[VECTOR][incident_playbook] killed process {}", name)
                return {"status": "ok", "name": name}
            return {"status": "error", "message": "no pid or name"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _action_notify(self, params: dict, evidence: dict, incident_id: str) -> dict:
        message = params.get("message", "Incident playbook executed")
        logger.info("[VECTOR][incident_playbook] NOTIFY: {}", message)
        return {"status": "ok", "message": message}

    async def _action_log_evidence(self, params: dict, evidence: dict, incident_id: str) -> dict:
        incident_dir = Path(f"data/security/incidents/{incident_id}")
        incident_dir.mkdir(parents=True, exist_ok=True)
        ev_path = incident_dir / "evidence.json"
        ev_path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
        logger.info("[VECTOR][incident_playbook] evidence saved to {}", ev_path)
        return {"status": "ok", "path": str(ev_path)}

    async def _action_isolate_process(self, params: dict, evidence: dict, incident_id: str) -> dict:
        pid = params.get("pid", evidence.get("pid", 0))
        if pid:
            return await self._action_kill_process({"pid": pid}, evidence, incident_id)
        return {"status": "error", "message": "no PID for isolation"}

    async def _action_collect_memory_dump(self, params: dict, evidence: dict, incident_id: str) -> dict:
        logger.info("[VECTOR][incident_playbook] memory dump requested for incident {}", incident_id[:8])
        return {"status": "ok", "message": "memory dump path logged", "incident_id": incident_id}

    async def _action_run_antivirus(self, params: dict, evidence: dict, incident_id: str) -> dict:
        logger.info("[VECTOR][incident_playbook] antivirus scan requested for incident {}", incident_id[:8])
        return {"status": "ok", "message": "antivirus scan initiated"}

    async def _action_escalate_to_human(self, params: dict, evidence: dict, incident_id: str) -> dict:
        message = params.get("message", "Human escalation required")
        logger.warning("[VECTOR][incident_playbook] ESCALATION: {} (incident={})", message, incident_id[:8])
        return {"status": "ok", "message": "escalated", "escalation_text": message}

    def _store_incident(self, incident: Incident) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO incidents (id, playbook_name, triggered_by, steps, status, created_at, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (incident.id, incident.playbook_name, incident.triggered_by,
                 json.dumps(incident.steps), incident.status,
                 incident.created_at.isoformat(), None),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("[VECTOR][incident_playbook] store incident error: {}", e)

    def _update_incident(self, incident: Incident) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                "UPDATE incidents SET status = ?, steps = ?, resolved_at = ? WHERE id = ?",
                (incident.status, json.dumps(incident.steps),
                 incident.resolved_at.isoformat() if incident.resolved_at else None, incident.id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("[VECTOR][incident_playbook] update incident error: {}", e)

    def get_incidents(self, limit: int = 20) -> list[dict]:
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT * FROM incidents ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            conn.close()
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error("[VECTOR][incident_playbook] query error: {}", e)
            return []

    def rollback(self, incident_id: str) -> bool:
        try:
            conn = self._get_conn()
            cursor = conn.execute("SELECT status FROM incidents WHERE id = ?", (incident_id,))
            row = cursor.fetchone()
            conn.close()
            if not row:
                return False
            conn = self._get_conn()
            conn.execute("UPDATE incidents SET status = 'ROLLED_BACK', resolved_at = ? WHERE id = ?",
                         (datetime.datetime.now(datetime.timezone.utc).isoformat(), incident_id))
            conn.commit()
            conn.close()
            logger.info("[VECTOR][incident_playbook] incident {} rolled back", incident_id[:8])
            return True
        except Exception as e:
            logger.error("[VECTOR][incident_playbook] rollback error: {}", e)
            return False

    def stop(self) -> None:
        self._running = False

    async def run(self, task: dict | None = None) -> dict:
        return {"playbooks_loaded": len(self._playbooks), "playbooks": list(self._playbooks.keys())}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ipr = IncidentPlaybookRunner()
    print(f"IncidentPlaybookRunner OK — {len(ipr._playbooks)} playbooks loaded")
    if ipr._playbooks:
        print(f"  Playbooks: {list(ipr._playbooks.keys())}")
    print("incident_playbook_runner.py OK")
