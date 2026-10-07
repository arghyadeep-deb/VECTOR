"""
Module: agents/privacy/privacy_enforcer.py
District: privacy | Focus: Data sharing scan, GDPR compliance, PII redaction
"""

import sys
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, re, datetime
from typing import Optional


class PrivacyEnforcer(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="PrivacyEnforcer",
            district="privacy",
            generation=1
        )
        self.capabilities = ["data_flow", "enforce", "privacy"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.pii_patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "phone": r'\b(?:\+?91[-.\s]?)?[6-9]\d{9}\b',
            "aadhar": r'\b[2-9]\d{11}\b',
            "pan": r'\b[A-Z]{5}[0-9]{4}[A-Z]\b',
            "credit_card": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
            "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
            "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        }
        self.gdpr_requirements = [
            "lawfulness_fairness_transparency",
            "purpose_limitation",
            "data_minimisation",
            "accuracy",
            "storage_limitation",
            "integrity_confidentiality",
            "accountability",
        ]
        logger.info("[VECTOR][privacy] PrivacyEnforcer ready")

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
            # Privacy district prompts carry scanned/PII-adjacent content: never cloud.
            district="privacy",
            sensitive=True,
            allow_cloud=False,
        )

    def scan_data_sharing(self) -> dict:
        logger.info("[VECTOR][privacy] Scanning for unintended data sharing")
        self.add_lesson({"action": "scan_data_sharing"})

        # KNOWN_ISSUES #21: don't close EpisodicMemory()'s shared singleton
        # connection from a local instance — see skill_mapper.py's note.
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        events = mem.recall("share", limit=50, event_type=None)

        shared_data_types = []
        sharing_violations = []

        for event in events:
            raw_content = event.get("content") or ""
            content = raw_content.lower()
            context_raw = event.get("context_snapshot")
            context = {}
            if context_raw:
                try:
                    context = json.loads(context_raw) if isinstance(context_raw, str) else context_raw
                except (json.JSONDecodeError, TypeError):
                    logger.debug("[VECTOR][privacy] unparseable context_snapshot on event {}", event.get("id", ""))

            if any(kw in content for kw in ["share", "send", "upload", "export", "api", "third party"]):
                shared_data_types.append({
                    "event_id": event.get("id", ""),
                    "content_preview": content[:100],
                    "timestamp": event.get("timestamp", ""),
                })

                for ptype, pattern in self.pii_patterns.items():
                    # Match the ORIGINAL text: lowercasing hid PAN (uppercase-only pattern).
                    if re.search(pattern, raw_content):
                        sharing_violations.append({
                            "type": ptype,
                            "severity": "high",
                            "event_id": event.get("id", ""),
                            "recommendation": f"Immediately review data sharing containing {ptype}",
                        })

        result = {
            # no_data: recall returned nothing (empty or failed read) - LOW is NOT a clean bill of health
            "status": "ok" if events else "no_data",
            "scanned_events": len(events),
            "data_sharing_incidents": len(shared_data_types),
            "pii_violations": len(sharing_violations),
            "violations": sharing_violations[:10],
            "risk_level": "HIGH" if len(sharing_violations) >= 3 else "MEDIUM" if len(sharing_violations) >= 1 else "LOW",
            "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="data_sharing_scan",
            content=f"Data sharing scan: {len(shared_data_types)} incidents, {len(sharing_violations)} PII violations",
            tags=["privacy", "data_sharing", "scan"],
            context=result,
            source="PrivacyEnforcer"
        )

        logger.info(f"[VECTOR][privacy] Scan complete: {result['risk_level']} risk level")
        return result

    def enforce_gdpr(self, data: dict) -> dict:
        logger.info("[VECTOR][privacy] Running GDPR compliance check")
        self.add_lesson({"action": "enforce_gdpr"})

        compliance_checks = {}
        unanswered = 0
        for req in self.gdpr_requirements:
            prompt = f"Check if this data handling context meets GDPR requirement: '{req}'. Data context: {json.dumps(data, indent=2)[:500]}\nReturn JSON: {{compliant: bool, score: 0-100, issues: string[], recommendations: string[]}}"
            check = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

            try:
                import re
                json_match = re.search(r'\{.*\}', check, re.DOTALL)
                if json_match:
                    result_check = json.loads(json_match.group(0))
                else:
                    result_check = {"compliant": False, "score": 50, "issues": [check[:200]], "recommendations": []}
            except json.JSONDecodeError:
                result_check = {"compliant": False, "score": 50, "issues": [check[:200]], "recommendations": []}

            if not isinstance(result_check, dict):
                result_check = {"compliant": False, "score": 50, "issues": [check[:200]], "recommendations": []}
            try:
                result_check["score"] = float(result_check.get("score", 0))
            except (TypeError, ValueError):
                result_check["score"] = 0
            if not check.strip():
                unanswered += 1
            compliance_checks[req] = result_check

        overall_score = round(sum(c.get("score", 0) for c in compliance_checks.values()) / max(len(compliance_checks), 1), 1)
        compliance_level = "COMPLIANT" if overall_score >= 90 else "PARTIAL" if overall_score >= 60 else "NON_COMPLIANT"

        result = {
            # error: the local LLM answered none of the checks; the score is a placeholder, not an assessment
            "status": "error" if unanswered == len(self.gdpr_requirements) else "ok",
            "checks": compliance_checks,
            "overall_score": overall_score,
            "compliance_level": compliance_level,
            "requirements_count": len(self.gdpr_requirements),
            "compliant_count": sum(1 for c in compliance_checks.values() if c.get("compliant")),
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="gdpr_check",
            content=f"GDPR compliance check: {compliance_level} ({overall_score}%)",
            tags=["privacy", "GDPR", "compliance"],
            context=result,
            source="PrivacyEnforcer"
        )

        return result

    def redact_pii(self, text: str) -> dict:
        logger.info(f"[VECTOR][privacy] Redacting PII from text ({len(text)} chars)")
        self.add_lesson({"action": "redact_pii"})

        redacted_text = text
        findings = []

        for ptype, pattern in self.pii_patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                findings.append({
                    "type": ptype,
                    "count": len(matches),
                })
                placeholder = f"[{ptype.upper()}_REDACTED]"
                redacted_text = re.sub(pattern, placeholder, redacted_text)

        findings_text = "\n".join([f"- {f['type']}: {f['count']} instances" for f in findings])
        prompt = f"""Review this text for any PII that might have been missed by pattern matching:
Original length: {len(text)} chars
Redacted so far: {redacted_text[:300]}...
Found patterns: {findings_text}
Return any additional PII found as JSON: {{additional_finds: [{{type, start, end, value}}]}}, or empty list if nothing found."""
        additional = self._call_ollama(prompt)

        try:
            import re as _re
            json_match = _re.search(r'\{.*\}', additional, _re.DOTALL)
            if json_match:
                add_data = json.loads(json_match.group(0))
                for item in add_data.get("additional_finds", []):
                    # Match by the LLM-reported `value` text, not its `start`/`end`
                    # offsets: the LLM was only shown redacted_text[:300] (a
                    # truncated PREVIEW), so any offset it returns is relative to
                    # that preview, not this live string -- and applying several
                    # items' offsets in sequence against a string that each
                    # substitution itself mutates (placeholder length != matched
                    # length) corrupts every offset after the first. Matching on
                    # the reported value text is immune to both problems.
                    value = item.get("value") or ""
                    if not value or value not in redacted_text:
                        continue
                    placeholder = f"[{item.get('type', 'PII').upper()}_REDACTED]"
                    redacted_text = redacted_text.replace(value, placeholder)
        except (json.JSONDecodeError, TypeError, AttributeError, ValueError):
            logger.debug("[VECTOR][privacy] LLM PII review output unusable; pattern redaction only")

        result = {
            "original_length": len(text),
            "redacted_text": redacted_text,
            "findings": findings,
            "total_redactions": sum(f["count"] for f in findings),
            "redacted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="pii_redacted",
            content=f"Redacted {sum(f['count'] for f in findings)} PII items from text",
            tags=["privacy", "PII", "redaction"],
            context=result,
            source="PrivacyEnforcer"
        )

        logger.info(f"[VECTOR][privacy] Redacted {result['total_redactions']} PII items")
        return result


    async def run(self, task: dict) -> dict:
        result = self.scan_data_sharing()
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = PrivacyEnforcer()
    assert agent.district == "privacy"

    scan = agent.scan_data_sharing()
    assert "risk_level" in scan

    gdpr = agent.enforce_gdpr({"data_type": "user_profile", "retention_days": 365})
    assert "overall_score" in gdpr

    text = "Contact me at john.doe@email.com or call 9876543210. My Aadhar is 234567890123."
    redacted = agent.redact_pii(text)
    assert "redacted_text" in redacted
    assert "john.doe@email.com" not in redacted["redacted_text"]
    assert redacted["total_redactions"] >= 2

    print("✅ privacy_enforcer.py OK")