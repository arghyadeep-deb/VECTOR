"""
Compliance Auditor — SOC2, GDPR, privacy policy compliance checking.
Loaded from: vectorcode/agents/vector-compliance-auditor.md
District: governance
"""
import asyncio

from loguru import logger
from core.city.prompt_agent import PromptAgent


class ComplianceAuditor(PromptAgent):
    """
    Compliance checking across SOC2, GDPR, privacy requirements.
    Audits VECTOR's own code and any client systems for compliance gaps.
    Powered by vector-compliance-auditor.md system prompt.
    """

    def __init__(self):
        super().__init__("vector-compliance-auditor.md", "compliance_auditor_001", "governance")
        self.capabilities = ["audit", "audit_log", "audit_verify", "compliance"]

    async def audit_data_handling(self, code: str, standard: str = "GDPR") -> dict:
        """Audit code for compliance with a specific standard."""
        query = (
            f"Audit this code for {standard} compliance. Check:\n"
            f"- PII data handling and storage\n"
            f"- Data retention policies\n"
            f"- Access controls and logging\n"
            f"- Encryption at rest and transit\n"
            f"- Third-party data sharing\n\n"
            f"```python\n{code[:3000]}\n```\n\n"
            f"Return: COMPLIANT / NON-COMPLIANT / NEEDS-REVIEW per category, with specific fixes."
        )
        response = await self.ask(query, timeout=40.0)
        compliant = "NON-COMPLIANT" not in response.upper()
        return {"status": "ok", "standard": standard, "audit": response, "likely_compliant": compliant}

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        task = {**task, **(task.get("params") or {})}
        task_type = task.get("type", "ask")
        try:
            if task_type == "audit":
                result = await self.audit_data_handling(
                    task.get("code", ""), task.get("standard", "GDPR")
                )
                self.award_points(25, "compliance_audited")
                return result
            else:
                return await super().run(task)
        except Exception as e:
            logger.error("[VECTOR][compliance] {}", e)
            self.deduct_points(30, "compliance_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    async def _smoke():
        agent = ComplianceAuditor()
        print(f"[OK] loaded: {agent.name} prompt={len(agent._system_prompt)}chars")
        print("compliance_auditor.py OK")
    asyncio.run(_smoke())
