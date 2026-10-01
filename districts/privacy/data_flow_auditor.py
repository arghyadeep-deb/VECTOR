"""
Module: agents/privacy/data_flow_auditor.py
District: privacy | Focus: Audit data flows, find leaks, generate privacy audit reports
"""

import sys
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime, collections
from typing import Optional


class DataFlowAuditor(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="DataFlowAuditor",
            district="privacy",
            generation=1
        )
        self.capabilities = ["audit", "data_flow", "privacy"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.data_flows = []
        self.leak_candidates = []
        logger.info("[VECTOR][privacy] DataFlowAuditor ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
            district="privacy",
            sensitive=True,
            allow_cloud=False,
        )

    def audit_data_flows(self) -> dict:
        logger.info("[VECTOR][privacy] Auditing all data flows")
        self.add_lesson({"action": "audit_data_flows"})

        events = self.memory.recall("", limit=200)

        flow_sources = collections.Counter()
        flow_destinations = collections.Counter()
        data_types = collections.Counter()
        suspicious_flows = []

        for event in events:
            content = (event.get("content") or "").lower()
            event_type = event.get("event_type", "")

            if any(kw in content for kw in ["send", "share", "upload", "export", "api", "http", "post", "request"]):
                flow_sources[event_type or "unknown"] += 1

            if any(kw in content for kw in ["receive", "store", "save", "db", "database", "file"]):
                flow_destinations[event_type or "unknown"] += 1

            for dtype in ["email", "phone", "password", "token", "key", "ssn", "aadhar", "credit_card"]:
                if dtype in content:
                    data_types[dtype] += 1

            risk_keywords = ["unencrypted", "public", "exposed", "leak", "breach", "hack"]
            if any(kw in content for kw in risk_keywords):
                suspicious_flows.append({
                    "event_id": event.get("id", ""),
                    "timestamp": event.get("timestamp", ""),
                    "risk": "HIGH",
                })

        self.data_flows = [
            {"source": s, "destination": d, "frequency": f}
            for s, f in flow_sources.items()
            for d in [flow_destinations.most_common(1)[0][0] if flow_destinations else "unknown"]
        ]

        result = {
            "total_events_audited": len(events),
            "data_flows_detected": len(self.data_flows),
            "data_types_involved": dict(data_types.most_common(10)),
            "suspicious_flows": len(suspicious_flows),
            "flow_sources": dict(flow_sources.most_common(10)),
            "flow_destinations": dict(flow_destinations.most_common(10)),
            "audited_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="data_flow_audited",
            content=f"Audited {len(events)} events: {len(self.data_flows)} flows, {len(suspicious_flows)} suspicious",
            tags=["privacy", "audit", "data_flow"],
            context=result,
            source="DataFlowAuditor"
        )

        logger.info(f"[VECTOR][privacy] Audited {len(events)} events: {len(self.data_flows)} flows")
        return result

    def find_leaks(self) -> dict:
        logger.info("[VECTOR][privacy] Finding potential data leaks")
        self.add_lesson({"action": "find_leaks"})

        events = self.memory.recall("", limit=100)

        leak_indicators = []
        pii_keywords = ["email", "phone", "password", "token", "api_key", "ssn", "aadhar", "credit_card", "bank"]
        network_leak_keywords = ["http://", "https://", "api/", "webhook", "callback", "post/", "json"]
        storage_leak_keywords = ["publicly", "exposed", "unauthenticated", "no auth", "open"]

        for event in events:
            content = (event.get("content") or "").lower()

            leak_score = 0
            reasons = []

            for kw in pii_keywords:
                if kw in content:
                    leak_score += 2
                    reasons.append(f"PII keyword found: {kw}")

            for kw in network_leak_keywords:
                if kw in content:
                    leak_score += 1
                    reasons.append(f"Network leak indicator: {kw}")

            for kw in storage_leak_keywords:
                if kw in content:
                    leak_score += 3
                    reasons.append(f"Storage leak indicator: {kw}")

            if leak_score >= 4:
                leak_indicators.append({
                    "event_id": event.get("id", ""),
                    "leak_score": leak_score,
                    "reasons": reasons,
                    "timestamp": event.get("timestamp", ""),
                    "severity": "CRITICAL" if leak_score >= 7 else "HIGH" if leak_score >= 5 else "MEDIUM",
                })

        self.leak_candidates = leak_indicators

        result = {
            "status": "ok" if events else "no_data",
            "leaks_found": len(leak_indicators),
            "critical_leaks": sum(1 for l in leak_indicators if l["severity"] == "CRITICAL"),
            "high_leaks": sum(1 for l in leak_indicators if l["severity"] == "HIGH"),
            "medium_leaks": sum(1 for l in leak_indicators if l["severity"] == "MEDIUM"),
            "leak_indicators": sorted(leak_indicators, key=lambda x: x["leak_score"], reverse=True)[:10],
            "risk_level": "CRITICAL" if any(l["severity"] == "CRITICAL" for l in leak_indicators) else "HIGH" if any(l["severity"] == "HIGH" for l in leak_indicators) else "MEDIUM" if leak_indicators else "LOW",
            "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="leaks_found",
            content=f"Found {len(leak_indicators)} potential data leaks, risk: {result['risk_level']}",
            tags=["privacy", "leak", "security"],
            context=result,
            source="DataFlowAuditor"
        )

        logger.info(f"[VECTOR][privacy] Found {len(leak_indicators)} leak candidates, risk: {result['risk_level']}")
        return result

    def generate_audit_report(self) -> dict:
        logger.info("[VECTOR][privacy] Generating privacy audit report")
        self.add_lesson({"action": "generate_audit_report"})

        if not self.data_flows:
            self.audit_data_flows()
        if not self.leak_candidates:
            self.find_leaks()

        prompt = f"""Generate a comprehensive privacy audit report:
Data flows tracked: {len(self.data_flows)}
Leaks found: {len(self.leak_candidates)}
Data flow summary: {json.dumps(self.data_flows[:5])}
Top leaks: {json.dumps([{'event_id': l['event_id'], 'severity': l['severity'], 'score': l['leak_score']} for l in self.leak_candidates[:5]])}
Include: 1) Executive summary, 2) Key findings, 3) Data flow map summary, 4) Leak severity breakdown, 5) Remediation steps (prioritized), 6) Compliance status."""
        report = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        if not (report or "").strip():
            logger.error("[VECTOR][privacy] Audit report generation failed: local LLM returned nothing")
            return {
                "status": "error",
                "error": "local LLM returned no report",
                "audit_scope": "comprehensive",
                "data_flows_tracked": len(self.data_flows),
                "leaks_identified": len(self.leak_candidates),
                "report": "",
                "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

        result = {
            "audit_scope": "comprehensive",
            "data_flows_tracked": len(self.data_flows),
            "leaks_identified": len(self.leak_candidates),
            "report": report,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="audit_report_generated",
            content=f"Privacy audit report: {len(self.data_flows)} flows, {len(self.leak_candidates)} leaks",
            tags=["privacy", "audit", "report"],
            context=result,
            source="DataFlowAuditor"
        )

        return result


    async def run(self, task: dict) -> dict:
        result = self.generate_audit_report()
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = DataFlowAuditor()
    assert agent.district == "privacy"

    audit = agent.audit_data_flows()
    assert "data_flows_detected" in audit

    leaks = agent.find_leaks()
    assert "leaks_found" in leaks
    assert "risk_level" in leaks

    report = agent.generate_audit_report()
    assert "report" in report

    print("✅ data_flow_auditor.py OK")
