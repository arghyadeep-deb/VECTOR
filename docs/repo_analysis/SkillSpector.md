# SkillSpector — Absorption Analysis

**Verdict:** IMPLEMENT (security gap)

---

## What it is

NVIDIA SkillSpector v2.2.3 (Apache-2.0, `LICENSE` line 1; `pyproject.toml:10`) — a static + optional-LLM security scanner that answers "Is this skill safe to install?" *before* an agent loads it. It is the missing front-door VECTOR does not have.

**Scanner pipeline** (`src/skillspector/graph.py:33-55`): a LangGraph `StateGraph` (langgraph>=1.0.10, `pyproject.toml:40`) with a fan-out/fan-in topology:
`resolve_input → build_context → [N analyzer nodes in parallel] → meta_analyzer → report → END`.

- **Inputs** (`input_handler.py:55-69`): Git repo URL, raw file URL, zip, single `SKILL.md`, or local directory — all normalized to a scannable dir.
- **Stage 1 (static, `--no-llm`)**: `run_static_patterns` (`static_runner.py:105-142`) iterates components, infers file type (17 extensions, `static_runner.py:30-47`), skips files >1 MB (`MAX_FILE_BYTES = 1_000_000`) and eval-dataset prose, runs each pattern module's `analyze(content, path, file_type)`, normalizes everything to a `Finding`.
- **Stage 2 (LLM, optional)**: semantic analyzers + `meta_analyzer` for context/intent + false-positive filtering. README claims ~87% precision (`README.md:464`). Anti-jailbreak guard baked into the prompt (`mcp_tool_poisoning.py:712-715`).
- **Outputs**: terminal / JSON / Markdown / **SARIF** (CI/IDE), with a 0-100 risk score (CRITICAL +50, HIGH +25, MED +10, LOW +5, executable ×1.3) → SAFE / CAUTION / DO NOT INSTALL (`README.md:336-351`).
- **Python API** (`README.md:498-515`): `from skillspector import graph; graph.invoke({"input_path":..., "use_llm":False})` — directly callable as a library, no CLI needed.

**16 categories / 64 patterns**: prompt injection (P1-P5), data exfiltration (E1-E4), privilege escalation (PE1-PE3), supply chain incl. live OSV.dev CVE lookup (SC1-SC6), excessive agency (EA1-EA4), output handling (OH1-OH3), system-prompt leakage (P6-P8), memory poisoning (MP1-MP3), tool misuse (TM1-TM3), rogue agent (RA1-RA2), trigger abuse (TR1-TR3), **behavioral AST** (AST1-AST8, `behavioral_ast.py` real `ast` parse), **static taint tracking** (TT1-TT5), **YARA** (YR1-YR4, 4 bundled `.yar` rule files: malware/webshells/cryptominers/hacktools), **MCP least-privilege** (LP1-LP4), **MCP tool poisoning** (TP1-TP4). Grounded in research (Liu et al. 2026, 42,447 skills: 26.1% vulnerable, 5.2% likely-malicious — `README.md:489-494`).

---

## VECTOR already has

| Capability | VECTOR module | Coverage |
|---|---|---|
| Prompt-injection / exfil regex scanner | `core/security/prompt_injection.py` (243 LOC, 14 patterns: 9 injection + 5 exfil) | Scans *runtime text* (user msgs, tool output, channel msgs) at the API boundary. Overlaps SkillSpector P1-P5 + E1-E4 thematically. |
| Taint tracking | `core/security/taint_tracker.py` (306 LOC) | **Runtime data-provenance labels** — `TaintedValue` objects you manually tag (USER_INPUT/SECRET/PII…) and check at sinks (shell/net/llm). NOT static source-code flow analysis. |
| SSRF guard | `core/security/ssrf_guard.py` | Blocks outbound requests to internal IPs. |
| Secrets / safe-eval / MCP audit | `core/security/secrets_manager.py`, `safe_eval.py`, `mcp_security.py`, `mcp_audit.db` | Secret storage, AST-safe eval, MCP call auditing. |
| Skill **execution** sandbox | `core/sandbox/skill_sandbox.py` + `vector_sandbox.py` | Classifies a skill by category → PermissionGateway GREEN/YELLOW/RED → runs in isolated subprocess. **Gates execution, not loading.** |
| Malware detection | `core/control/security/malware_detector.py` | 3-layer: VirusTotal hash + MIME heuristic + LightGBM. **No YARA.** |
| Security district | `districts/security/` (threat_scout, malware_hunter, node_guard, siem_pipeline, detection_rules) | Host/process/network threat ops — runtime, not artifact-vetting. |

**The critical hole:** `vectorcode/src/skills/loader.py` scans skill directories and `format_skill_for_injection()` injects skill content straight into the prompt (`loader.py:345,377`) with **zero security scan** — `grep` for `scan/inject/vet/yara/sandbox/trust` in the loader returns only the injection formatter. VECTOR absorbs external skills/repos with implicit trust (the audit found vendored jailbreak/red-team scripts in `vectorcode/src`), and nothing inspects a skill's *source* before it is trusted, loaded, or injected.

---

## Overlap vs genuinely new

**Overlaps (do NOT re-absorb):**
- P1-P5 / E1-E4 prompt-injection & exfiltration regex → already covered by `prompt_injection.py`'s 14 patterns (same `ignore previous instructions`, `you are now`, secret-URL-exfil, `[INST]` control tokens — compare `prompt_injection.py:83-128` with SkillSpector P1-P5/E1-E4). Same technique, same intent.
- AST dangerous-call detection (AST1-AST8: exec/eval/subprocess/os.system) → `core/security/safe_eval.py` already does AST-safe evaluation, and `malware_detector` covers binaries.

**Genuinely NEW (the absorption target — gaps only):**
1. **YARA engine + 4 curated rule sets** (`static_yara.py` + `yara_rules/*.yar`, `yara-python>=4.5.0`). VECTOR has **no YARA anywhere** — malware_detector is VT+MIME+LightGBM. Real malware/webshell/cryptominer/hacktool signature matching is net-new.
2. **MCP tool poisoning** (`mcp_tool_poisoning.py`, TP1-TP4): hidden instructions in manifest metadata (HTML/markdown comments, zero-width chars, base64, data URIs), **Unicode homoglyph / RTL-override / mixed-script deception** in tool names, parameter-description injection, LLM description-vs-behavior mismatch. VECTOR's text scanner does not parse MCP manifests, and has no homoglyph/zero-width/RTL detection at all.
3. **MCP least-privilege** (`mcp_least_privilege.py`, LP1-LP4): cross-checks declared permissions against capabilities actually present in code (under/over/wildcard declaration). VECTOR has no permission-vs-code reconciliation.
4. **Static source→sink taint flow** (`behavioral_taint_tracking.py`, TT1-TT5): AST-level credential-exfil / file-read-to-network / input-to-exec chains. Fundamentally different from VECTOR's runtime `TaintedValue` labels — SkillSpector finds the flow in *unexecuted source*, which is exactly what pre-load vetting needs.
5. **Live OSV.dev CVE lookup** (SC4) for dependency vulns — VECTOR has none.
6. **The skill-specific 64-pattern corpus + risk scoring + SARIF + the LangGraph scan pipeline itself** — a packaged "scan an artifact, get a verdict" workflow VECTOR lacks entirely.

---

## Why it matters for VECTOR

VECTOR's entire growth model is *continuous absorption of external skills/repos with implicit trust* — and the audit already proved this is unvetted (jailbreak scripts vendored into `vectorcode/src`). Per the research SkillSpector is built on, ~1 in 4 marketplace skills is vulnerable and ~1 in 20 is likely-malicious. VECTOR's existing defenses are all **post-load / runtime**: the sandbox gates *execution*, prompt_injection scans *messages*, the security district watches *the host*. None of them inspect a skill's source *before* it is loaded into the registry and injected into prompts. A poisoned `SKILL.md` (zero-width instruction, homoglyph tool name, base64 exfil payload) sails straight past every current control and into the model context. SkillSpector is the one missing layer: a **pre-trust gate** that reads the artifact and produces a SAFE/CAUTION/DO-NOT-INSTALL verdict before VECTOR ever trusts it.

---

## Integration plan

Apply the absorption rule (gaps only, reimplement in Python, reuse existing security seams):

- **New module:** `core/security/skill_scanner.py` (+ `core/security/yara_rules/`). Reimplement only the NEW analyzers in VECTOR style (loguru, `CONFIG`, `__main__` self-test): YARA engine, MCP tool-poisoning (TP1-TP4), MCP least-privilege (LP1-LP4), static taint-flow (TT1-TT5), OSV.dev SC4. **Do not** re-port P1-P5/E1-E4 — delegate those to the existing `scan_text()` so there is one prompt-injection corpus.
- **Reuse seams:** call `core.security.prompt_injection.scan_text()` for the injection/exfil category; route the optional LLM stage through `core/inference/provider_client.py` (Ollama-first, VECTOR Rule 11) instead of SkillSpector's OpenAI/Anthropic/NVIDIA providers; emit findings onto `core/event_bus`; persist verdicts like `mcp_audit.db`. VECTOR already uses langgraph, so the StateGraph pipeline ports cleanly if you want the fan-out topology.
- **Wire as two gates:**
  1. **Pre-skill-load gate** in `vectorcode/src/skills/loader.py` — scan every `SKILL.md` + scripts on directory scan; quarantine (skip load + skip `format_skill_for_injection`) anything scoring HIGH/CRITICAL; log to the security district.
  2. **Pre-absorption gate** in the repo-absorption workflow — run a scan on any new repo/skill before it enters `vectorcode/src` (closes the vendored-jailbreak-script hole; retroactively scan existing `vectorcode/src` skills).
- **District home:** `districts/security/` gets a `skill_spector.py` agent wrapping the scanner (fits alongside `malware_hunter`/`threat_scout`), exposed as an MCP tool (`skill_scan`) so VECTOR's own agents can vet a skill on demand.
- **Effort:** ~MEDIUM (1-2 focused sessions). The new analyzers are self-contained regex/AST/YARA modules; the main work is the loader/absorption wiring, the provider-client + scan_text delegation, and porting/curating the 4 YARA rule files. `yara-python` is the one new runtime dependency (`yara-python>=4.5.0`).

---

## Recommendation

**IMPLEMENT — priority HIGH.** SkillSpector fills VECTOR's single largest structural security gap: a system whose core behavior is *absorbing external skills/repos with implicit trust* currently has **no pre-load artifact-vetting layer** — every existing defense (sandbox, prompt_injection scanner, security district) is runtime/post-trust, and the skill loader injects content with zero scanning. The overlap with VECTOR's prompt_injection/taint is shallow (same intent, different stage: runtime text vs. static source), while the genuinely-new surface — YARA signature matching (VECTOR has none), MCP tool-poisoning + Unicode-deception detection, permission-vs-code least-privilege reconciliation, static source→sink taint flow, and live OSV.dev CVE lookup — is substantial, Apache-2.0 (clean to absorb), pure-Python, and directly targets the documented unvetted-absorption risk (vendored jailbreak scripts). Absorb gaps only into `core/security/skill_scanner.py`, reuse `scan_text()` + `provider_client` + event_bus seams, and wire it as a quarantine gate in both `skills/loader.py` and the repo-absorption workflow. This is the highest-leverage security absorption available to VECTOR right now.
