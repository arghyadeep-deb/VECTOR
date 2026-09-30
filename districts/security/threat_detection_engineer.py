"""
ThreatDetectionEngineer — SIEM rule development and MITRE ATT&CK coverage.

Writes Sigma rules, maps to ATT&CK techniques, assesses detection coverage,
analyzes logs for threat indicators. Detection-as-code for personal computing.
"""

import asyncio
import re
import datetime

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat

# ---------------------------------------------------------------------------
# MITRE ATT&CK technique catalog (personal computing relevance)
# ---------------------------------------------------------------------------
# Maps technique ID → (name, tactic, log_sources_needed)
_ATTACK_TECHNIQUES: dict[str, dict] = {
    "T1059.001": {"name": "PowerShell", "tactic": "Execution",
                  "log_sources": ["windows_event", "powershell_log"]},
    "T1059.003": {"name": "Windows Command Shell (cmd.exe)", "tactic": "Execution",
                  "log_sources": ["windows_event", "process_creation"]},
    "T1078":     {"name": "Valid Accounts", "tactic": "Persistence",
                  "log_sources": ["auth_log", "windows_event"]},
    "T1053.005": {"name": "Scheduled Task", "tactic": "Persistence",
                  "log_sources": ["windows_event", "sysmon"]},
    "T1547.001": {"name": "Registry Run Keys / Startup Folder", "tactic": "Persistence",
                  "log_sources": ["windows_event", "registry_audit"]},
    "T1566.001": {"name": "Spearphishing Attachment", "tactic": "Initial Access",
                  "log_sources": ["email_log", "endpoint_log"]},
    "T1055":     {"name": "Process Injection", "tactic": "Privilege Escalation",
                  "log_sources": ["sysmon", "windows_event"]},
    "T1040":     {"name": "Network Sniffing", "tactic": "Credential Access",
                  "log_sources": ["network_log", "process_creation"]},
    "T1110.001": {"name": "Brute Force: Password Guessing", "tactic": "Credential Access",
                  "log_sources": ["auth_log", "windows_event"]},
    "T1003.001": {"name": "OS Credential Dumping: LSASS Memory", "tactic": "Credential Access",
                  "log_sources": ["sysmon", "windows_event"]},
    "T1071.001": {"name": "Application Layer Protocol: Web Protocols (C2)", "tactic": "C2",
                  "log_sources": ["network_log", "proxy_log"]},
    "T1083":     {"name": "File and Directory Discovery", "tactic": "Discovery",
                  "log_sources": ["windows_event", "sysmon"]},
    "T1057":     {"name": "Process Discovery", "tactic": "Discovery",
                  "log_sources": ["process_creation", "sysmon"]},
    "T1041":     {"name": "Exfiltration Over C2 Channel", "tactic": "Exfiltration",
                  "log_sources": ["network_log", "dns_log"]},
    "T1486":     {"name": "Data Encrypted for Impact (Ransomware)", "tactic": "Impact",
                  "log_sources": ["filesystem_log", "windows_event"]},
    "T1562.001": {"name": "Disable/Modify Security Tools", "tactic": "Defense Evasion",
                  "log_sources": ["windows_event", "endpoint_log"]},
    "T1070.001": {"name": "Clear Windows Event Logs", "tactic": "Defense Evasion",
                  "log_sources": ["windows_event"]},
    "T1036":     {"name": "Masquerading", "tactic": "Defense Evasion",
                  "log_sources": ["sysmon", "process_creation"]},
    "T1190":     {"name": "Exploit Public-Facing Application", "tactic": "Initial Access",
                  "log_sources": ["web_log", "application_log"]},
    "T1133":     {"name": "External Remote Services (RDP/VPN)", "tactic": "Initial Access",
                  "log_sources": ["auth_log", "network_log"]},
}

# ---------------------------------------------------------------------------
# IOC patterns for log analysis (regex-based, no external API)
# ---------------------------------------------------------------------------
_IOC_PATTERNS: list[tuple[str, str, str, str]] = [
    # (pattern, technique_id, severity, description)
    (r"(?i)powershell\s+-(?:enc|encodedcommand|nop|noprofile|w\s+hidden)",
     "T1059.001", "high", "Encoded/hidden PowerShell execution"),
    (r"(?i)cmd\.exe\s+/c\s+(?:whoami|ipconfig|net\s+user)",
     "T1059.003", "medium", "Reconnaissance via cmd.exe"),
    (r"(?i)mimikatz|lsadump|sekurlsa|procdump.*lsass",
     "T1003.001", "critical", "Credential dumping tool signature"),
    (r"(?i)net\s+user\s+/domain|net\s+localgroup\s+administrators",
     "T1078", "medium", "Account enumeration"),
    (r"(?i)schtasks\s+/create|taskschd\.msc",
     "T1053.005", "medium", "Scheduled task creation"),
    (r"(?i)reg\s+add\s+.*\\run\b",
     "T1547.001", "high", "Registry run key modification"),
    (r"(?i)vssadmin\s+delete\s+shadows|bcdedit\s+/set.*recoveryenabled\s+no",
     "T1486", "critical", "Ransomware shadow copy deletion"),
    (r"(?i)wevtutil\s+cl\s+|Clear-EventLog",
     "T1070.001", "high", "Event log clearing"),
    (r"(?i)netsh\s+(?:firewall|advfirewall)\s+(?:set|add)",
     "T1562.001", "high", "Firewall modification"),
    (r"(?i)tasklist|Get-Process\s+-Name",
     "T1057", "low", "Process discovery"),
    (r"(?i)dir\s+/[as]|Get-ChildItem\s+-Recurse",
     "T1083", "low", "File/directory discovery"),
    (r"(?i)\b(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b.*(?:cmd|shell|bash|powershell)",
     "T1071.001", "high", "Suspicious IP + shell combination (possible C2)"),
    (r"(?i)failed\s+password|authentication\s+failure|invalid\s+password",
     "T1110.001", "medium", "Authentication failure — possible brute force"),
    (r"(?i)procdump|process\s+hacker|processhacker",
     "T1055", "high", "Process injection / memory dump tool"),
]

# Tactics covered per known log source
_LOG_SOURCE_COVERAGE: dict[str, list[str]] = {
    "windows_event":   ["Execution", "Persistence", "Defense Evasion", "Discovery"],
    "sysmon":          ["Execution", "Persistence", "Privilege Escalation", "Defense Evasion"],
    "auth_log":        ["Credential Access", "Initial Access", "Persistence"],
    "network_log":     ["C2", "Exfiltration", "Initial Access"],
    "dns_log":         ["C2", "Exfiltration"],
    "proxy_log":       ["C2", "Initial Access"],
    "process_creation": ["Execution", "Discovery", "Defense Evasion"],
    "registry_audit":  ["Persistence"],
    "filesystem_log":  ["Impact", "Discovery"],
    "email_log":       ["Initial Access"],
    "endpoint_log":    ["Execution", "Defense Evasion"],
    "web_log":         ["Initial Access"],
    "application_log": ["Initial Access"],
    "powershell_log":  ["Execution"],
}

# All unique tactics across known techniques
_ALL_TACTICS = list({v["tactic"] for v in _ATTACK_TECHNIQUES.values()})

class ThreatDetectionEngineer(AgentBase):
    """SIEM rule development, MITRE ATT&CK coverage mapping, detection-as-code."""

    def __init__(self):
        super().__init__(
            agent_id="threat_detection_001",
            name="ThreatDetectionEngineer",
            district="security",
        )
        self.capabilities = ["analyze_logs", "coverage_map", "report", "scan_prompt", "security", "security_scan", "sigma_rule", "ssrf_check", "threat"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        self._attack_techniques: dict[str, dict] = _ATTACK_TECHNIQUES
        logger.info("[VECTOR][threat_detection_engineer] initialized")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def generate_sigma_rule(self, technique_id: str, description: str) -> str:
        """Generate a Sigma-format detection rule YAML for the given ATT&CK technique.

        Returns a Sigma YAML string. Never raises.
        """
        try:
            tech = self._attack_techniques.get(technique_id)
            if not tech:
                logger.warning(
                    f"[VECTOR][threat_detection] Unknown technique: {technique_id} — generating generic rule"
                )
                tech = {
                    "name": technique_id,
                    "tactic": "Unknown",
                    "log_sources": ["windows_event"],
                }

            tactic = tech["tactic"]
            tech_name = tech["name"]
            log_sources = tech.get("log_sources", ["windows_event"])
            primary_log = log_sources[0]

            # Map primary log source to Sigma logsource block
            logsource_map = {
                "windows_event":   "category: process_creation\nproduct: windows",
                "sysmon":          "category: process_creation\nproduct: windows\ndefinition: sysmon",
                "auth_log":        "category: authentication\nproduct: linux",
                "network_log":     "category: network_connection\nproduct: windows",
                "powershell_log":  "product: windows\nservice: powershell",
                "registry_audit":  "category: registry_event\nproduct: windows",
                "filesystem_log":  "category: file_event\nproduct: windows",
            }
            logsource_block = logsource_map.get(
                primary_log, "category: process_creation\nproduct: windows"
            )

            # Generate a detection condition based on technique
            detection_hints = {
                "T1059.001": "CommandLine|contains|all:\n          - 'powershell'\n          - '-enc'",
                "T1059.003": "CommandLine|contains|all:\n          - 'cmd.exe'\n          - '/c'",
                "T1003.001": "CommandLine|contains:\n          - 'mimikatz'\n          - 'lsadump'\n          - 'sekurlsa'",
                "T1547.001": "TargetObject|contains:\n          - '\\Run\\'\n          - '\\RunOnce\\'",
                "T1070.001": "CommandLine|contains|all:\n          - 'wevtutil'\n          - 'cl '",
                "T1486":     "CommandLine|contains:\n          - 'vssadmin delete shadows'\n          - 'bcdedit /set'",
                "T1110.001": "EventID: 4625",
                "T1053.005": "CommandLine|contains:\n          - 'schtasks'\n          - '/create'",
                "T1562.001": "CommandLine|contains:\n          - 'netsh'\n          - 'firewall'",
            }
            detection_condition = detection_hints.get(
                technique_id,
                f"CommandLine|contains:\n          - '{tech_name.split(':')[0].lower()}'",
            )

            # Severity mapping
            severity_map = {
                "Execution":          "medium",
                "Persistence":        "high",
                "Privilege Escalation": "high",
                "Credential Access":  "critical",
                "Defense Evasion":    "high",
                "C2":                 "critical",
                "Exfiltration":       "critical",
                "Impact":             "critical",
                "Initial Access":     "high",
                "Discovery":          "low",
            }
            level = severity_map.get(tactic, "medium")

            sigma_yaml = (
                f"title: Detection of {tech_name}\n"
                f"id: vector-sigma-{technique_id.replace('.', '-').lower()}\n"
                f"status: experimental\n"
                f"description: |\n"
                f"    {description}\n"
                f"    MITRE ATT&CK: {technique_id} — {tech_name}\n"
                f"    Tactic: {tactic}\n"
                f"references:\n"
                f"    - https://attack.mitre.org/techniques/{technique_id.replace('.', '/')}/\n"
                f"author: VECTOR ThreatDetectionEngineer (auto-generated)\n"
                f"date: {datetime.date.today().isoformat()}\n"
                f"tags:\n"
                f"    - attack.{tactic.lower().replace(' ', '_')}\n"
                f"    - attack.{technique_id.lower()}\n"
                f"logsource:\n"
                f"    {logsource_block}\n"
                f"detection:\n"
                f"    selection:\n"
                f"        {detection_condition}\n"
                f"    condition: selection\n"
                f"falsepositives:\n"
                f"    - Legitimate administrative activity\n"
                f"    - Security tooling and pen-test environments\n"
                f"level: {level}\n"
            )

            self._get_memory().store(
                event_type="generate_sigma_rule",
                content=f"technique={technique_id} tactic={tactic} level={level}",
                tags=["sigma", "detection", technique_id, tactic.lower()],
                source="threat_detection_engineer",
            )

            self.award_points(20, "sigma_rule_generated")
            logger.info(
                f"[VECTOR][threat_detection] generate_sigma_rule: "
                f"technique={technique_id} level={level}"
            )
            return sigma_yaml

        except Exception as e:
            logger.error(f"[VECTOR][threat_detection] generate_sigma_rule error: {e}")
            self.deduct_points(10, "sigma_rule_failed")
            return f"# Error generating Sigma rule for {technique_id}: {e}\n"

    def map_attack_coverage(self, monitored_sources: list[str]) -> dict:
        """Given log sources, return covered/uncovered ATT&CK tactics + coverage %.

        Returns:
            {
                monitored_sources: list[str],
                covered_tactics: list[str],
                uncovered_tactics: list[str],
                coverage_pct: float,
                covered_techniques: list[str],
                uncovered_techniques: list[str],
                gaps: list[str],
            }
        Never raises.
        """
        try:
            monitored_lower = [s.lower() for s in monitored_sources]

            # Determine covered tactics from monitored sources
            covered_tactics: set[str] = set()
            for src in monitored_lower:
                tactics = _LOG_SOURCE_COVERAGE.get(src, [])
                covered_tactics.update(tactics)

            uncovered_tactics = sorted(set(_ALL_TACTICS) - covered_tactics)
            covered_tactics_sorted = sorted(covered_tactics)

            # Determine covered techniques: a technique is covered if ANY of its
            # required log sources is in monitored_sources
            covered_techniques: list[str] = []
            uncovered_techniques: list[str] = []
            for tid, info in self._attack_techniques.items():
                required = info.get("log_sources", [])
                if any(src in monitored_lower for src in required):
                    covered_techniques.append(tid)
                else:
                    uncovered_techniques.append(tid)

            total = len(self._attack_techniques)
            coverage_pct = round(len(covered_techniques) / max(total, 1) * 100, 1)

            # Gaps: which log sources would expand coverage the most
            uncovered_source_tactics: dict[str, set] = {}
            for src, tactics in _LOG_SOURCE_COVERAGE.items():
                if src not in monitored_lower:
                    new_coverage = set(tactics) - covered_tactics
                    if new_coverage:
                        uncovered_source_tactics[src] = new_coverage

            gaps = sorted(
                [
                    f"Add '{src}' to cover: {', '.join(sorted(tc))}"
                    for src, tc in uncovered_source_tactics.items()
                ],
                key=lambda x: len(x),
                reverse=True,
            )[:5]  # top 5 recommendations

            result = {
                "monitored_sources": monitored_sources,
                "covered_tactics": covered_tactics_sorted,
                "uncovered_tactics": uncovered_tactics,
                "coverage_pct": coverage_pct,
                "covered_techniques": covered_techniques,
                "uncovered_techniques": uncovered_techniques,
                "gaps": gaps,
            }

            self._get_memory().store(
                event_type="map_attack_coverage",
                content=f"sources={len(monitored_sources)} coverage={coverage_pct}%",
                tags=["mitre", "coverage", "detection"],
                source="threat_detection_engineer",
            )

            if coverage_pct >= 70:
                self.award_points(30, "good_coverage")
            elif coverage_pct >= 40:
                self.award_points(15, "partial_coverage")
            else:
                self.deduct_points(10, "low_coverage")

            logger.info(
                f"[VECTOR][threat_detection] map_attack_coverage: "
                f"coverage={coverage_pct}% covered={len(covered_techniques)}/{total}"
            )
            return result

        except Exception as e:
            logger.error(f"[VECTOR][threat_detection] map_attack_coverage error: {e}")
            self.deduct_points(30, "task_failed")
            return {
                "monitored_sources": monitored_sources,
                "covered_tactics": [],
                "uncovered_tactics": _ALL_TACTICS,
                "coverage_pct": 0.0,
                "covered_techniques": [],
                "uncovered_techniques": list(self._attack_techniques.keys()),
                "gaps": [],
                "error": str(e),
            }

    def analyze_log_for_threats(self, log_lines: list[str]) -> list[dict]:
        """Pattern-match log lines against known IOC patterns (regex, no external API).

        Returns:
            list of {
                line_number: int,
                line: str,
                technique_id: str,
                severity: str,
                description: str,
            }
        Never raises.
        """
        try:
            findings: list[dict] = []
            compiled_patterns = [
                (re.compile(pattern), tid, severity, desc)
                for pattern, tid, severity, desc in _IOC_PATTERNS
            ]

            for i, line in enumerate(log_lines, start=1):
                for pattern_re, technique_id, severity, description in compiled_patterns:
                    if pattern_re.search(line):
                        findings.append({
                            "line_number": i,
                            "line": line.strip()[:200],  # cap at 200 chars
                            "technique_id": technique_id,
                            "technique_name": self._attack_techniques.get(
                                technique_id, {}
                            ).get("name", technique_id),
                            "severity": severity,
                            "description": description,
                        })

            n_critical = sum(1 for f in findings if f["severity"] == "critical")
            n_high = sum(1 for f in findings if f["severity"] == "high")

            self._get_memory().store(
                event_type="analyze_log_for_threats",
                content=(
                    f"lines={len(log_lines)} findings={len(findings)} "
                    f"critical={n_critical} high={n_high}"
                ),
                tags=["log_analysis", "ioc", "detection"],
                source="threat_detection_engineer",
            )

            if n_critical > 0:
                self.deduct_points(5, "critical_threats_found")
            elif findings:
                self.award_points(10, "threats_detected")
            else:
                self.award_points(15, "clean_log_analysis")

            logger.info(
                f"[VECTOR][threat_detection] analyze_log_for_threats: "
                f"lines={len(log_lines)} findings={len(findings)} critical={n_critical}"
            )
            return findings

        except Exception as e:
            logger.error(f"[VECTOR][threat_detection] analyze_log_for_threats error: {e}")
            self.deduct_points(30, "task_failed")
            return [{"line_number": 0, "line": "", "technique_id": "error",
                     "severity": "error", "description": str(e)}]

    async def generate_detection_report(self) -> dict:
        """LLM-assisted report of coverage gaps and recommendations.

        Returns:
            {
                coverage_summary: dict,
                top_gaps: list[str],
                llm_recommendations: str,
                sigma_rules_generated: int,
                timestamp: str,
            }
        Never raises.
        """
        try:
            # RULE 1 — hydrate before LLM call
            try:
                from core.loop.context_engine import ContextEngine
                ctx = ContextEngine()
                hydration = ctx.session_hydration_prompt({"task": "generate_detection_report"})
            except Exception:
                hydration = "You are VECTOR, an autonomous personal AI security assistant."

            # Common log sources for a personal Windows dev machine
            default_sources = [
                "windows_event", "process_creation", "powershell_log", "auth_log"
            ]
            coverage = self.map_attack_coverage(default_sources)

            gaps_str = "\n".join(f"- {g}" for g in coverage.get("gaps", []))
            uncovered_tactics_str = ", ".join(coverage.get("uncovered_tactics", []))

            from core.prompt_library import get_library as _gl
            _lib = _gl().get_for_agent("threat_detection_engineer") or ""
            _tde_sys = (hydration + "\n\n" + _lib).strip() if _lib else hydration
            messages = [
                {"role": "system", "content": _tde_sys},
                {
                    "role": "user",
                    "content": (
                        "You are ThreatDetectionEngineer for a personal Windows 11 dev machine "
                        "(RTX 5070 Ti, student developer). Provide concise, actionable security "
                        "recommendations based on these detection coverage facts:\n\n"
                        f"Coverage: {coverage['coverage_pct']}%\n"
                        f"Covered tactics: {', '.join(coverage.get('covered_tactics', []))}\n"
                        f"Uncovered tactics: {uncovered_tactics_str}\n"
                        f"Top gaps:\n{gaps_str}\n\n"
                        "Give 3-5 specific, implementable recommendations to improve detection "
                        "coverage. Focus on free/open-source tools only. "
                        "Be concise — 2-3 sentences per recommendation."
                    ),
                },
            ]

            llm_recs = chat(model=self._model, messages=messages, timeout=30.0)

            if not llm_recs:
                llm_recs = (
                    "1. Enable Sysmon with SwiftOnSecurity config for process + registry coverage.\n"
                    "2. Enable PowerShell ScriptBlock logging (Group Policy) to catch encoded commands.\n"
                    "3. Enable Windows Defender audit events to detect security tool disabling.\n"
                    "4. Enable DNS client logging for C2 detection.\n"
                    "5. Review Windows Event log size limits — increase to retain 7+ days."
                )

            result = {
                "coverage_summary": coverage,
                "top_gaps": coverage.get("gaps", []),
                "llm_recommendations": llm_recs,
                "sigma_rules_available": len(self._attack_techniques),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

            self._get_memory().store(
                event_type="generate_detection_report",
                content=f"coverage={coverage['coverage_pct']}% gaps={len(coverage.get('gaps', []))}",
                tags=["detection_report", "security", "mitre"],
                source="threat_detection_engineer",
            )

            self.award_points(30, "detection_report_generated")
            logger.info(
                f"[VECTOR][threat_detection] generate_detection_report: "
                f"coverage={coverage['coverage_pct']}%"
            )
            return result

        except Exception as e:
            logger.error(f"[VECTOR][threat_detection] generate_detection_report error: {e}")
            self.deduct_points(30, "task_failed")
            return {
                "coverage_summary": {},
                "top_gaps": [],
                "llm_recommendations": "",
                "sigma_rules_available": 0,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "error": str(e),
            }

    async def answer_threat_detection_question(self, query: str) -> str:
        """Answer a free-text/unmatched-task_type question grounded in
        this agent's real loaded state, instead of always dumping the raw
        agent-status/capabilities dict regardless of what was actually
        asked (KNOWN_ISSUES bug pattern — 'dumps an unrelated hardcoded
        default')."""
        context = (
            f"{len(self._attack_techniques)} MITRE ATT&CK techniques loaded, "
            f"{len(_IOC_PATTERNS)} IOC patterns loaded. "
            f"Capabilities: sigma_rule, coverage_map, analyze_logs, report."
        )
        prompt = (
            "You are VECTOR's ThreatDetectionEngineer in the security "
            "district — you write Sigma detection rules, map MITRE ATT&CK "
            "coverage, and analyze logs for threat indicators. Answer the "
            "owner's question using this real context; do not invent data "
            f"you don't have:\n\n{context}\n\nQuestion: {query}"
        )
        try:
            response = chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=20.0)
            return (response or "").strip() or context
        except Exception as e:
            logger.warning(f"[VECTOR][threat_detection] answer_threat_detection_question failed: {e}")
            return context

    # ------------------------------------------------------------------
    # run() — multi-task dispatcher
    # ------------------------------------------------------------------

    async def run(self, task: dict) -> dict:
        """Dispatch: sigma_rule | coverage_map | analyze_logs | report | status."""
        try:
            task_type = task.get("type", "report")
            # 2026-09-30 (Phase 3 codebase audit finding): the real governor
            # dispatch shape is {"type": ..., "params": {...}} -- the
            # structured branches below were reading technique_id/sources/
            # log_lines straight off `task` instead of `task["params"]`
            # (only the free-text fallback further down already checked
            # params correctly), so a real dispatch always fell back to the
            # hardcoded defaults, silently ignoring the caller's real
            # arguments. Verified live before fixing: dispatching sigma_rule
            # with params={"technique_id": "T1003.001"} returned the
            # T1059.001 default instead; analyze_logs with a real malicious
            # log line in params found 0 threats. `params.get(k, task.get(k,
            # default))` checks params first, then falls back to the flat
            # shape for backward compat, then the original default.
            params = task.get("params") or {}

            if task_type == "sigma_rule":
                technique_id = params.get("technique_id", task.get("technique_id", task.get("technique", "T1059.001")))
                description = params.get("description", task.get("description", f"Detection rule for {technique_id}"))
                rule = self.generate_sigma_rule(technique_id, description)
                self.award_points(30, "task_done")
                return {"status": "ok", "sigma_rule": rule, "technique_id": technique_id}

            elif task_type == "coverage_map":
                sources = params.get("sources", task.get("sources", task.get("log_sources", [])))
                if not isinstance(sources, list):
                    sources = [str(sources)]
                if not sources:
                    sources = ["windows_event", "process_creation"]
                result = self.map_attack_coverage(sources)
                self.award_points(30, "task_done")
                return {"status": "ok", **result}

            elif task_type == "analyze_logs":
                lines = params.get("log_lines", task.get("log_lines", task.get("lines", [])))
                if isinstance(lines, str):
                    lines = lines.splitlines()
                findings = self.analyze_log_for_threats(lines)
                self.award_points(30, "task_done")
                return {
                    "status": "ok",
                    "findings": findings,
                    "finding_count": len(findings),
                    "critical_count": sum(1 for f in findings if f["severity"] == "critical"),
                }

            elif task_type == "report":
                result = await self.generate_detection_report()
                self.award_points(30, "task_done")
                return {"status": "ok", **result}

            else:
                # KNOWN_ISSUES bug pattern: any unmatched task_type (e.g. a
                # stray conversational question routed here) used to always
                # get this same static agent-status/capabilities dump back,
                # regardless of what was actually asked — never an answer.
                # Real free text now gets answered; a genuinely content-free
                # structured call still gets the identical status dump.
                query = (
                    params.get("query")
                    or task.get("query")
                    or task.get("text")
                    or ""
                ).strip()
                if query:
                    answer = await self.answer_threat_detection_question(query)
                    if answer:
                        self.award_points(15, "threat_detection_question_answered")
                        return {"status": "ok", "response": answer}

                # Default: status
                return {
                    "status": "ok",
                    "agent": self.name,
                    "district": self.district,
                    "hp": self.health_points,
                    "model": self._model,
                    "attack_techniques_loaded": len(self._attack_techniques),
                    "ioc_patterns_loaded": len(_IOC_PATTERNS),
                    "capabilities": ["sigma_rule", "coverage_map", "analyze_logs", "report"],
                }

        except Exception as e:
            logger.error(f"[VECTOR][threat_detection] run error: {e}")
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = ThreatDetectionEngineer()

        # 1. sigma_rule
        result = await agent.run({
            "type": "sigma_rule",
            "technique_id": "T1059.001",
            "description": "Detect encoded PowerShell used for living-off-the-land attacks",
        })
        assert result["status"] == "ok", f"sigma_rule failed: {result}"
        assert "title:" in result["sigma_rule"]
        assert "detection:" in result["sigma_rule"]
        print(f"[OK] sigma_rule: technique={result['technique_id']} lines={len(result['sigma_rule'].splitlines())}")

        # 2. coverage_map
        result2 = await agent.run({
            "type": "coverage_map",
            "sources": ["windows_event", "sysmon", "auth_log"],
        })
        assert result2["status"] == "ok", f"coverage_map failed: {result2}"
        assert "coverage_pct" in result2
        assert isinstance(result2["coverage_pct"], float)
        print(
            f"[OK] coverage_map: coverage={result2['coverage_pct']}% "
            f"covered={len(result2['covered_tactics'])} tactics"
        )

        # 3. analyze_logs
        sample_logs = [
            "2026-05-16 10:01:23 INFO Process started: powershell.exe -enc JABXAG...",
            "2026-05-16 10:02:01 WARN Authentication failure for user admin@host",
            "2026-05-16 10:02:45 INFO cmd.exe /c whoami",
            "2026-05-16 10:03:00 INFO svchost.exe started normally",
            "2026-05-16 10:05:00 CRIT mimikatz detected in memory",
        ]
        result3 = await agent.run({"type": "analyze_logs", "log_lines": sample_logs})
        assert result3["status"] == "ok", f"analyze_logs failed: {result3}"
        assert result3["finding_count"] >= 2, f"Expected >=2 findings, got {result3['finding_count']}"
        print(
            f"[OK] analyze_logs: findings={result3['finding_count']} "
            f"critical={result3['critical_count']}"
        )

        # 4. status
        result4 = await agent.run({"type": "status"})
        assert result4["status"] == "ok"
        print(f"[OK] run: status={result4['status']}")
        print("threat_detection_engineer.py OK")

    asyncio.run(_smoke())
