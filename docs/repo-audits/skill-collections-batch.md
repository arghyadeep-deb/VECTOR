# Skill Collections Batch Audit
> Audited: 2026-06-01

---

## agent-skills-main
**What it is:** addyosmani/agent-skills — 23 engineering SKILL.md files covering the dev lifecycle (api-and-interface-design, browser-testing-with-devtools, ci-cd-and-automation, code-review-and-quality, code-simplification, context-engineering, debugging-and-error-recovery, deprecation-and-migration, documentation-and-adrs, frontend-ui-engineering, git-workflow-and-versioning, idea-refine, incremental-implementation, performance-optimization, planning-and-task-breakdown, security-and-hardening, shipping-and-launch, source-driven-development, spec-driven-development, test-driven-development, using-agent-skills). Also includes JS validation scripts, SDD cache hooks (shell), and setup docs for Cursor/Gemini CLI/Windsurf/OpenCode — none of which are Python.

**VECTOR already has:** All 23 skill folders are present verbatim in `brain/.claude/skills/` (verified: api-and-interface-design, security-and-hardening, using-agent-skills, etc. all confirmed there). Global `~/.claude/skills/` has `test-driven-development` installed from this collection too.

**Verdict: DELETE-NOW**
**Action:** No extraction needed. Pure .md skill collection fully mirrored in brain vault.

---

## awesome-agent-skills-main
**What it is:** VoltAgent/awesome-agent-skills — a curated index/links repo. Contains only 3 files: `README.md` (1400+ skills listed as links), `CONTRIBUTING.md`, `LICENSE`. Zero skill files, zero Python code. It is a bookmark list pointing to other repos.

**VECTOR already has:** Everything this repo points to is either already absorbed or irrelevant.

**Verdict: DELETE-NOW**
**Action:** Nothing to extract. It is a web index with no local content.

---

## awesome-claude-skills-master
**What it is:** Composio/awesome-claude-skills — 27 skill folders as SKILL.md packages. Skills include: artifacts-builder, brand-guidelines, canvas-design, changelog-generator, competitive-ads-extractor, composio-skills, connect, connect-apps, connect-apps-plugin, content-research-writer, developer-growth-analysis, document-skills, domain-name-brainstormer, file-organizer, image-enhancer, internal-comms, invoice-organizer, langsmith-fetch, lead-research-assistant, mcp-builder, meeting-insights-analyzer, raffle-winner-picker, skill-creator, skill-share, slack-gif-creator, tailored-resume-builder, theme-factory, twitter-algorithm-optimizer, video-downloader, webapp-testing. A few folders include shell scripts (bundle-artifact.sh, init-artifact.sh) and one `.tar.gz` (shadcn components for artifacts-builder) — but these are scaffolding helpers for building those specific skill types, not reusable Python logic.

**VECTOR already has:** `mcp-builder` is in brain skills. `skill-creator`, `internal-comms`, `slack-gif-creator`, `theme-factory`, `webapp-testing` are all present in brain/.claude/skills/. The Composio-specific skills (connect, connect-apps, composio-skills, langsmith-fetch) are Composio SaaS integrations — VECTOR uses its own 30+ channel adapters via vectorcode, not Composio. `competitive-ads-extractor`, `lead-research-assistant`, `invoice-organizer` are adjacent to VECTOR's ads/* and agency/* districts but are thin .md wrappers with no Python logic.

**Verdict: DELETE-NOW**
**Action:** No Python/data to extract. All valuable skills (mcp-builder, skill-creator, webapp-testing) already in brain. Composio-specific skills are irrelevant to VECTOR's stack.

---

## awesome-skills-main
**What it is:** A large community-aggregated skill collection with 371 brain skills already loaded. Contains: `skills/` directory with subcategories (workflow, persona, tool, tools — covering 60+ industry verticals and tool integrations), `autoresearch/` folder (Karpathy-style autonomous LLM training loop with `train.py` + `prepare.py` + `analysis.ipynb`), `benchmarks/` (skill evaluation data and reports), `scripts/` (10 Python maintenance scripts: `generate_skills_data.py`, `cleanup_skills.py`, `dedupe_references.py`, `description_linter.py`, `fix_name_folder_mismatch.py`, `tag_skills_kind.py`, etc.), `packages/` (14 industry persona .md files), `optimization_results/` and `reports/` (evaluation artifacts).

**VECTOR already has:**
- The `autoresearch/` Python code (`train.py`, `prepare.py`) is a Karpathy autoresearch loop. VECTOR's `districts/karpathy_lab/autoresearch_runner.py` already implements this pattern — it wraps `train.py` via subprocess, proposes architectural improvements via `vector-reasoning`, tracks `val_bpb`, and logs to episodic memory. The `brain/.claude/skills/autoresearch.md` SKILL.md is also present.
- All 371 brain skills already installed; this repo is either the source or a superset.
- The Python maintenance scripts (`generate_skills_data.py`, `cleanup_skills.py`, etc.) are for managing a public skills catalog website — not useful for VECTOR's private vault.
- `benchmarks/skill_evaluator.py` is an evaluation harness for ranking skills against each other — VECTOR has no need for this (skills are used, not ranked publicly).

**Verdict: DELETE-NOW**
**Action:** `autoresearch/train.py` has a cleaner FlashAttention-3 + MLA implementation than VECTOR's current stub, but `autoresearch_runner.py` already wraps external train.py via subprocess — it can use any train.py. If desired: copy `autoresearch/train.py` → `districts/karpathy_lab/train.py` as the base training script (optional, not blocking).

---

## andrej-karpathy-skills-main
**What it is:** A single-skill repo containing one folder: `skills/karpathy-guidelines/SKILL.md`. The skill encodes Karpathy's 4 LLM coding principles: Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution. Also has `CLAUDE.md` (project-level rules version of the same principles), `CURSOR.md`, `EXAMPLES.md`, and `README.zh.md` (Chinese translation). Zero Python code.

**VECTOR already has:** `brain/.claude/skills/karpathy-guidelines/` is confirmed present. The global `~/.claude/skills/` system-reminder also lists `karpathy` as an available skill. Additionally, `brain/.claude/skills/` contains `karpathy-build-nanogpt.md`, `karpathy-makemore.md`, `karpathy-micrograd.md`, `karpathy-minbpe.md`, `karpathy-nanogpt.md` — full Karpathy curriculum already loaded.

**Verdict: DELETE-NOW**
**Action:** No extraction needed. Fully redundant.

---

## Anthropic-Cybersecurity-Skills-main
**What it is:** Official Anthropic cybersecurity skill collection — 754 SKILL.md files covering the full DFIR/offensive/defensive security spectrum: malware analysis, forensics, MITRE ATT&CK, cloud security, pen testing, OSINT, OT/ICS, threat hunting, incident response, etc. Also includes: `tools/validate-skill.py` (skill metadata validator), `mappings/` (MITRE ATT&CK Navigator layers, NIST CSF, OWASP mappings as JSON), `assets/`, `index.json` (machine-readable skill index).

**VECTOR already has:** 11 cybersecurity skills confirmed in `brain/.claude/skills/`: analyzing-api-gateway-access-logs, analyzing-apt-group-with-mitre-navigator, analyzing-cloud-storage-access-patterns, analyzing-cyber-kill-chain, analyzing-dns-logs-for-exfiltration, analyzing-docker-container-forensics, analyzing-email-headers-for-phishing-investigation, analyzing-ethereum-smart-contract-vulnerabilities, analyzing-indicators-of-compromise, analyzing-kubernetes-audit-logs, analyzing-linux-audit-logs-for-intrusion. That is 11 of 754 — only 1.5% installed.

**VECTOR does NOT have:** The remaining 743 skills covering: memory forensics (Volatility), malware reverse engineering (Ghidra, IDA, YARA), Active Directory attacks, cloud provider security (AWS/Azure/GCP), OT/ICS/SCADA, mobile forensics, network packet analysis, threat intel, red team TTPs, secure coding reviews, ransomware recovery, and 60+ MITRE ATT&CK sub-techniques. The `mappings/` MITRE ATT&CK Navigator JSON files and `index.json` also provide structured threat coverage data.

**Verdict: KEEP**
**Action:** Install remaining 743 cybersecurity skills into `brain/.claude/skills/`. The `mappings/` directory (MITRE ATT&CK layers, NIST CSF, OWASP) has structured JSON data valuable for `districts/security/` threat_scout and malware_hunter agents. The `tools/validate-skill.py` can be reused as a skill quality-check utility. This is the only repo in this batch with substantial uninstalled value.

---

## obsidian-skills-main
**What it is:** kepano/obsidian-skills — 5 Obsidian-specific SKILL.md files: obsidian-markdown (Obsidian Flavored Markdown syntax), obsidian-bases (Obsidian Bases .base files), json-canvas (JSON Canvas .canvas spec), obsidian-cli (Obsidian CLI plugin/theme dev), defuddle (web-to-markdown extraction via Defuddle library). Zero Python code.

**VECTOR already has:** All 5 skills confirmed in `brain/.claude/skills/`: `obsidian-markdown`, `obsidian-bases`, `obsidian-cli`, `json-canvas`, `defuddle`. Full overlap.

**Verdict: DELETE-NOW**
**Action:** No extraction needed. Fully redundant.

---

## Summary

| Repo | Verdict | Action |
|------|---------|--------|
| agent-skills-main | DELETE-NOW | All 23 skills already in brain vault |
| awesome-agent-skills-main | DELETE-NOW | Index-only repo, zero local content |
| awesome-claude-skills-master | DELETE-NOW | All valuable skills already in brain vault |
| awesome-skills-main | DELETE-NOW | All skills in brain; autoresearch/train.py optionally copy to karpathy_lab/ |
| andrej-karpathy-skills-main | DELETE-NOW | karpathy-guidelines + full curriculum already in brain |
| Anthropic-Cybersecurity-Skills-main | KEEP | 743 of 754 skills NOT yet installed; mappings/ has MITRE/NIST/OWASP JSON data |
| obsidian-skills-main | DELETE-NOW | All 5 skills already in brain vault |

**6 of 7 repos: safe to delete immediately.**
**1 repo to keep:** `Anthropic-Cybersecurity-Skills-main` — copy remaining 743 skill folders into `brain/.claude/skills/` and `mappings/` JSON into `districts/security/data/` before deleting the local clone.
