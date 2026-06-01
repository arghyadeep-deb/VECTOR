# Misc Collections Batch Audit
> Audited: 2026-06-01

---

## gsap-skills-main

**What it is:** Official GSAP (GreenSock Animation Platform) AI skills for Claude Code, Cursor, Codex, and 40+ agents. 8 skill folders: `gsap-core`, `gsap-timeline`, `gsap-scrolltrigger`, `gsap-plugins`, `gsap-react`, `gsap-frameworks`, `gsap-performance`, `gsap-utils`. Each folder is a `SKILL.md` teaching agents the correct GSAP API. No Python, no runnable code — pure AI agent instruction files.

**VECTOR parity:** VECTOR has no frontend animation layer. VECTOR's dashboard (`dashboard/src/`) is unbuilt. GSAP is irrelevant to VECTOR's Python backend, autonomous loop, or district agents. When/if a Next.js dashboard is built, these skills would be useful for the *developer* (Arghyadeep) to install as Claude Code skills for that frontend session — but they don't belong in the VECTOR codebase itself. They are already freely available via `npx skills add greensock/gsap-skills` if ever needed.

**Verdict: DELETE-NOW**
**Action:** Nothing to absorb. Repo is a skills distribution package for a JS animation library. No Python gaps, no agent logic, not relevant to VECTOR's Python-first architecture. Delete the local clone.

---

## open-skills-main

**What it is:** A Mac-only MCP server (`server.py`, FastMCP + Playwright + Jupyter WebSocket kernel pool) that runs Claude Skills in an isolated Apple Silicon container sandbox. Ships with 2 trivial public skills: `image-crop-rotate` and `pdf-text-replace`. Requires Docker + Apple Silicon native containers. MIT-adjacent license.

**VECTOR parity:** VECTOR runs on Windows 11 / Legion Pro 5 (Intel + NVIDIA). The entire isolation layer depends on Apple's native container API (`containerized` mode, macOS-only). The MCP server logic (Jupyter kernel pool, WebSocket bridge, skill execution) duplicates what VECTOR already has via `core/sandbox/` (VectorSandbox, absorbed from openfang) and `core/mcp_server.py` (14+ tools). The 2 bundled skills (image crop, PDF text replace) are trivial — VECTOR has `pytesseract`/Pillow for images and `core/browser/pii_scrub.py` for PDF-adjacent processing.

**Verdict: DELETE-NOW**
**Action:** Incompatible platform (macOS/Apple Silicon only). No extractable Python gaps — sandbox and MCP layers are already covered. The 2 skills are trivial. Delete the local clone.

---

## gstack-main

**What it is:** The full gstack source repository — a headless-browser Claude Code skill suite for QA, screenshot testing, site dogfooding, and design review. TypeScript/Bun codebase with 40+ skills (`browse`, `qa`, `ship`, `health`, `investigate`, `design-review`, `pair-agent`, `plan-*`, etc.), E2E eval harness, LLM judge, and diff-based CI. The `SKILL.md` in root is v1.55.0.0.

**VECTOR parity:** gstack is **already installed** at `~/.claude/skills/gstack`. However the installed version is **v1.15.0.0** vs repo **v1.55.0.0** — a 40-version lag. The installed version is missing 40 versions of improvements, new skills, and bug fixes. The gstack source repo is the upstream. VECTOR's `tools.md` and `CLAUDE.md` explicitly mandate using `/browse`, `/qa`, `/ship`, `/health`, `/investigate`, `/design` — all from gstack.

**Verdict: PATCH VECTOR**
**Action:** Upgrade installed gstack from v1.15.0.0 → v1.55.0.0. Run `/gstack-upgrade` or manually copy the skill folders from this repo into `~/.claude/skills/`. Do NOT copy into the VECTOR codebase — gstack lives in the user-global skills directory. Keep the local clone as the upgrade source until `gstack-upgrade` auto-update is wired.

---

## karpathy-main

**What it is:** A Google ADK + LiteLLM multi-agent ML engineer harness named "Karpathy". It is an agentic orchestrator (not the Karpathy course/lectures) that delegates ML tasks (data prep, training, evaluation, deployment) to 12 sub-experts via `delegate_task`. Uses `start.py` to scaffold a `sandbox/` directory, installs Scientific Agent Skills (130+ ML skills), and launches the ADK web UI at `http://localhost:8000`. Requires `OPENROUTER_API_KEY`.

**VECTOR parity:** VECTOR's `districts/karpathy_lab/` has: `progress_tracker.py` (30min/day session tracker), `code_typer.py`, `data_prep.py`, `architecture_builder.py`, `autoresearch_runner.py`. These cover the *Karpathy learning track* (daily coding practice, nanoGPT from scratch, OpenMythos pipeline). The karpathy-main repo is a *different concept* — an ML experiment orchestrator for running arbitrary ML jobs, not a learning/practice tracker. The ADK harness, sub-expert delegation pattern, and Scientific Agent Skills collection are orthogonal to what VECTOR's karpathy_lab does. No Python gaps — VECTOR already has `provider_client.py` (27 providers including OpenRouter), LangGraph orchestration, and the `data_analytics/` district for ML-adjacent tasks. The Google ADK dependency is not part of VECTOR's stack.

**Verdict: DELETE-NOW**
**Action:** The name collision ("karpathy") is misleading. This repo is an ML orchestrator harness for one-off experiments, not a daily practice tracker. VECTOR's karpathy_lab district serves its intended purpose. No Python code worth absorbing — the orchestration patterns are superseded by VECTOR's own multi-agent infrastructure. Delete the local clone.

---

## llm-council-master

**What it is:** A weekend-hack web app by Karpathy (the person) for multi-LLM deliberation via OpenRouter. FastAPI backend (`council.py`, `openrouter.py`, `config.py`) + React/Vite frontend. Implements the same 3-stage pattern: Stage 1 (parallel responses) → Stage 2 (anonymized cross-ranking) → Stage 3 (Chairman synthesis). Uses OpenRouter to call cloud models (GPT, Gemini, Claude, Grok). Explicitly described as "not supported."

**VECTOR parity:** VECTOR's `districts/governance/llm_council.py` already implements the identical 3-stage pattern (Stage 1 `_stage1_collect`, Stage 2 `_stage2_rank` with blind A/B/C labels, Stage 3 `_stage3_synthesize` via Chairman). VECTOR uses local Ollama models (vector-reasoning, vector-r1, devstral, vector-chairman) instead of cloud APIs, has HP-gating (>700 HP), weekly throttle, full EpisodicMemory integration, Obsidian sync, and event subscription. The logic is more complete than llm-council-master.

**Bug found:** VECTOR's `LLMCouncil.__init__` calls `self.subscribe_to("decision_made")` and `self.subscribe_to("security_alert")` but `AgentBase` does not define a `subscribe_to()` method — causing an `AttributeError` at instantiation. This is a VECTOR bug, not something from llm-council-master. The fix is to add a stub `subscribe_to()` in `AgentBase` or remove the calls from `LLMCouncil.__init__` (the actual event subscription is handled by the EventBus elsewhere).

**Verdict: PATCH VECTOR**
**Action:** Fix the `subscribe_to` AttributeError in `core/city/agent_base.py` — add `def subscribe_to(self, event_type: str): pass` as a no-op stub (or wire it properly to the EventBus). The llm-council-master repo itself has no Python logic not already superseded by VECTOR's implementation. The React frontend is the only unique artifact — if a council UI dashboard is ever wanted, it can be referenced then. No code absorption needed now. Delete the local clone after the bug fix is confirmed.

---

## agency-agents-main

**What it is:** A large collection of 150+ AI agent `.md` personality files organized into 20 categories: engineering, marketing, design, finance, sales, product, testing, support, specialized, academic, game-development, spatial-computing, paid-media, project-management, strategy, and more. Each file is a Claude Code agent definition (YAML frontmatter + personality + workflow). MIT license.

**VECTOR parity:** Per `phase_status.md`, the session 2026-05-17 absorbed the following agency-agents categories directly into VECTOR Python agents: `coding/` (minimal_change_engineer, codebase_onboarding_engineer, rapid_prototyper), `security/` (threat_detection_engineer), `finance/` (financial_analyst, fpa_analyst), `agency/` (sales_strategist, proposal_strategist), `governance/` (product_manager), `marketing/` (seo_specialist, growth_hacker, social_media_strategist, content_creator, ai_citation_strategist), `design/` (ui_designer, ux_researcher, image_prompt_engineer). The `.md` source files are also copied verbatim into `districts/marketing/` and `districts/design/`.

**Unabsorbed categories** (not in VECTOR districts):
- `academic/` — 5 agents (anthropologist, geographer, historian, narratologist, psychologist) — no VECTOR district
- `game-development/` — 10 agents (game designer, level designer, Unity/Unreal/Godot/Roblox/Blender specialists) — no VECTOR district
- `spatial-computing/` — 6 agents (VisionOS, XR, macOS Metal) — no VECTOR district, Mac-only
- `paid-media/` — 7 agents (auditor, creative strategist, PPC, programmatic, tracking) — partially covered by `districts/marketing/ads/`
- `project-management/` — 6 agents (project shepherd, Jira steward, studio producer) — partially covered by `districts/projects/`
- `support/` — 6 agents (support responder, infrastructure maintainer, legal compliance checker) — no direct VECTOR equivalents
- `specialized/` — 20+ agents (MCP builder, model QA, chief-of-staff, workflow architect, LSP index engineer, etc.) — some overlap with `districts/qa/` and `districts/chief_of_staff/`
- `testing/` — 8 agents — fully absorbed into `districts/qa/`
- `product/` — 5 agents (product manager absorbed; behavioral nudge, feedback synthesizer, zk steward absorbed into personal_growth)

**Verdict: PATCH VECTOR**
**Action:** Three targeted gaps worth absorbing:
1. `paid-media/` agents (paid-media-auditor, paid-media-ppc-strategist, paid-media-tracking-specialist) — copy `.md` files into `districts/marketing/` as reference agents alongside existing ads Python agents.
2. `support/support-responder.md` and `support/infrastructure-maintainer.md` — add to `districts/ops/` as reference agent specs.
3. `specialized/specialized-mcp-builder.md` — add to `brain/.claude/agents/` as a Claude Code subagent spec.

Skip: academic, game-development, spatial-computing (not relevant to VECTOR's use case — single-owner personal AI system). The remaining unabsorbed `.md` files are personality templates with no Python logic; no new Python agents needed.

---

## Summary Table

| Repo | Verdict | Notes |
|------|---------|-------|
| gsap-skills-main | DELETE-NOW | JS animation skills for Claude agents; no Python, irrelevant to VECTOR backend |
| open-skills-main | DELETE-NOW | macOS/Apple Silicon only; sandbox + MCP already covered by VECTOR |
| gstack-main | PATCH VECTOR | Installed gstack is v1.15 — repo is v1.55; run `/gstack-upgrade` |
| karpathy-main | DELETE-NOW | ML experiment orchestrator (Google ADK), not a learning tracker; no Python gaps |
| llm-council-master | PATCH VECTOR | 3-stage council logic already in VECTOR; fixes `subscribe_to` AttributeError bug in `AgentBase` |
| agency-agents-main | PATCH VECTOR | Core categories already absorbed; 3 targeted gaps: paid-media .md refs, support .md refs, mcp-builder agent |

## Bug Alert

`districts/governance/llm_council.py:53-54` calls `self.subscribe_to("decision_made")` and `self.subscribe_to("security_alert")` but `core/city/agent_base.AgentBase` has no `subscribe_to()` method. Fix: add `def subscribe_to(self, event_type: str): pass` to `AgentBase`, or wire it to the EventBus. This causes `LLMCouncil()` instantiation to raise `AttributeError` — the council cannot be created at runtime.
