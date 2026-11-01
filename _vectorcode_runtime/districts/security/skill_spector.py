"""Security district wrapper for VECTOR's pre-load skill scanner."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from core.city.agent_base import AgentBase
from core.security.skill_scanner import scan_artifact


class SkillSpector(AgentBase):
    """Vet skills, MCP manifests, and small repo artifacts before absorption."""

    def __init__(self, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="SkillSpector",
            district="security",
        )
        self.capabilities = ["scan", "security", "security_scan"]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][skill_spector] initialized")

    async def run(self, task: dict | str | None = None) -> dict[str, Any]:
        if isinstance(task, str):
            params = {"path": task}
        elif isinstance(task, dict):
            params = task.get("params", task)
        else:
            params = {}
        target = params.get("path") or params.get("target")
        if not target:
            return {
                "status": "error",
                "error": "missing path",
                "supported": ["scan_artifact"],
            }
        path = Path(str(target))
        report = scan_artifact(path)
        return {
            "status": "ok" if not report.blocked else "blocked",
            "path": str(path),
            "verdict": report.verdict.value,
            "risk_score": report.risk_score,
            "scanned_files": report.scanned_files,
            "skipped_files": report.skipped_files,
            "findings": [
                {
                    "severity": finding.severity.value,
                    "category": finding.category,
                    "message": finding.message,
                    "path": finding.path,
                    "line": finding.line,
                    "evidence": finding.evidence,
                }
                for finding in report.findings
            ],
        }
