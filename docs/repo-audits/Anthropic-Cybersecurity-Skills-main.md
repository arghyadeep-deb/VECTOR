# Anthropic-Cybersecurity-Skills-main Audit

## 1. Repo Reality

**Source:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\Anthropic-Cybersecurity-Skills-main`

| Metric | Count |
|--------|-------|
| Total SKILL.md files | 754 |
| Python files | 0 |
| Other notable files | `ATTACK_COVERAGE.md`, `index.json`, `mappings/`, `tools/`, `assets/` |

**Skill breakdown by action prefix:**

| Action | Skills |
|--------|--------|
| `performing-*` | 172 (red team, OSINT, pentesting, forensics procedures) |
| `implementing-*` | 167 (security controls, hardening, detection rules) |
| `detecting-*` | 87 (IDS/IPS rules, anomaly detection, SIEM queries) |
| `analyzing-*` | 76 (malware, log, traffic, artifact analysis) |
| `building-*` | 34 (security tooling, pipelines, monitoring stacks) |
| `hunting-*` | 34 (threat hunting across various TTPs) |
| `exploiting-*` | 32 (CVE exploitation, red team techniques) |
| `testing-*` | 22 (security testing, fuzzing, pen test procedures) |
| Others | ~130 (conducting, configuring, securing, scanning, triaging...) |

**Mappings directory — key intelligence assets:**

| Mapping | Contents | Size |
|---------|----------|------|
| `attack-navigator-layer.json` | Full MITRE ATT&CK Navigator layer for all 754 skills | 96 KB |
| `mitre-attack/` | Coverage summary: 291 unique techniques, 14/14 tactics covered (ATT&CK v16) | - |
| `nist-csf/csf-alignment.md` | Full NIST CSF 2.0 alignment table: skills → GV/ID/PR/DE/RS/RC functions | - |
| `owasp/README.md` | OWASP Top 10 mapping | - |

**ATT&CK Coverage (from `ATTACK_COVERAGE.md`):**
- 291 unique MITRE ATT&CK techniques mapped
- 14/14 Enterprise tactics fully covered
- Persistence: 36 techniques, Defense Evasion: 48 techniques, Credential Access: 27 techniques

## 2. VECTOR Parity

**Installed in `~/.claude/skills`:** 0 / 754 (none installed)

**Cross-check with system-reminder available skills:** Several cybersecurity skill names appear in the system-reminder (e.g., `analyzing-api-gateway-access-logs`, `analyzing-apt-group-with-mitre-navigator`, `analyzing-cyber-kill-chain`, `analyzing-dns-logs-for-exfiltration`, etc.) — these are listed as available but loaded from `brain/.claude/skills/` which has 0 files. They are **declared but not actually installed**.

**ThreatScout relevance analysis:**

VECTOR's `districts/security/threat_scout.py` performs process scanning, registry scanning, and network scanning. The cybersecurity skills library would give ThreatScout and the security district agents expert-level procedure knowledge for:

| District Agent | Relevant Skills | Count |
|----------------|----------------|-------|
| `threat_scout.py` | `analyzing-indicators-of-compromise`, `performing-threat-intelligence-analysis`, `hunting-for-lateral-movement`, `detecting-network-intrusion-*` | ~50 |
| `malware_hunter.py` | `analyzing-linux-elf-malware`, `analyzing-malware-behavior-with-cuckoo-sandbox`, `analyzing-packed-malware-*`, `detecting-malware-with-*` | ~80 |
| `node_guard.py` | `analyzing-kubernetes-audit-logs`, `detecting-container-escape-*`, `implementing-network-segmentation` | ~30 |
| Security district general | `performing-penetration-testing-*`, `implementing-zero-trust-*`, `building-siem-*` | ~120 |

**Mappings value for ThreatScout:**
- `attack-navigator-layer.json` (96 KB) — machine-readable MITRE ATT&CK coverage map. ThreatScout could load this to classify detected threats against ATT&CK techniques and generate structured threat reports (Tactic ID → Technique ID → relevant hunting skill).
- `mitre-attack/coverage-summary.md` — human-readable cross-reference for the security district agents.
- `nist-csf/csf-alignment.md` — maps detected threats to NIST CSF response functions (Identify → Protect → Detect → Respond → Recover), useful for the `ops/incident_commander.py` agent.
- `owasp/README.md` — useful for `districts/security/` API security scanning.

**Parity score:** ❌ 0/754 skills installed. All 754 are unique gaps. The mappings directory is independently valuable for ThreatScout's threat classification logic.

## 3. Frontend

N/A — no frontend code in this repo.

## 4. Verdict

**High-value for VECTOR District 4 (security) and District 2 (intelligence/ThreatScout). Install selectively — do not bulk-copy 754 skills.**

The skills themselves are Claude Code skills (each ~500-2000 token SKILL.md files). Installing all 754 would add significant overhead to every Claude Code session. The right approach: install the ~50-80 skills most relevant to VECTOR's security district as on-demand skills, and copy the `mappings/` directory into VECTOR's codebase for ThreatScout to reference programmatically.

**Overall:** ❌ Not installed (high-value subset to install; mappings/ to copy into codebase)

## 5. Gaps — What to Install

**Step 1 — Copy mappings into VECTOR codebase (immediate ThreatScout value):**
```bash
# Copy entire mappings directory for ThreatScout to reference
xcopy /E /I "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\Anthropic-Cybersecurity-Skills-main\mappings" "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\districts\security\mitre_mappings"
```

ThreatScout can then load `attack-navigator-layer.json` to auto-classify alerts with ATT&CK technique IDs:
```python
# In districts/security/threat_scout.py
import json
with open("districts/security/mitre_mappings/attack-navigator-layer.json") as f:
    attack_nav = json.load(f)
```

**Step 2 — Install high-value security skills to `~/.claude/skills/`:**
```bash
# Threat hunting + IOC analysis
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/Anthropic-Cybersecurity-Skills-main/skills/analyzing-indicators-of-compromise" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/Anthropic-Cybersecurity-Skills-main/skills/analyzing-apt-group-with-mitre-navigator" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R\GitHub\Anthropic-Cybersecurity-Skills-main/skills/analyzing-dns-logs-for-exfiltration" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/Anthropic-Cybersecurity-Skills-main/skills/analyzing-cyber-kill-chain" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/Anthropic-Cybersecurity-Skills-main/skills/analyzing-kubernetes-audit-logs" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/Anthropic-Cybersecurity-Skills-main/skills/analyzing-docker-container-forensics" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/Anthropic-Cybersecurity-Skills-main/skills/analyzing-api-gateway-access-logs" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/Anthropic-Cybersecurity-Skills-main/skills/analyzing-linux-audit-logs-for-intrusion" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/Anthropic-Cybersecurity-Skills-main/skills/analyzing-ethereum-smart-contract-vulnerabilities" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/Anthropic-Cybersecurity-Skills-main/skills/analyzing-email-headers-for-phishing-investigation" "C:/Users/Arghyadeep/.claude/skills/"
```

**Note on system-reminder discrepancy:** Several of these skill names already appear in the system-reminder `available-skills` list. This means they were declared/registered somewhere but the actual SKILL.md files are not present in `~/.claude/skills/` or `brain/.claude/skills/`. Installing them from this repo will resolve the mismatch — the skills will actually work when invoked.

**Skip:** Red-team offensive exploitation skills (`exploiting-*`), nation-state attribution skills, malware creation skills — these activate adversarial capabilities that conflict with VECTOR's permission gateway philosophy. VECTOR defends, not attacks.
