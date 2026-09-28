# Brain Index — V.E.C.T.O.R. Brain Vault

Vault path: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain\` (sibling of the repo, i.e. `../V.E.C.T.O.R. Brain/`; this is what `VECTOR_VAULT_PATH` in `.env` points to). There is no `brain/` junction inside the repo, so the `brain/` prefix used below means that folder — read files there by their full path.

## Always-Loaded (via @import in CLAUDE.md)
- `brain/VECTOR/Architecture.md` — autonomous loop, coroutines, session hydration, memory schema, voice pipeline, council, HP system, deployment
- `brain/VECTOR/Roadmap.md` — 50-day build plan, phase breakdown, Karpathy track, OpenMythos timeline

## VECTOR Planning (read on-demand)
- `brain/VECTOR/README.md` — what VECTOR is, stack table, 20 districts overview, critical rules
- `brain/VECTOR/Decisions/001-local-first-no-cloud-runtime.md` — why Claude API is never called at runtime
- `brain/VECTOR/Decisions/002-darwinian-hp-over-static-agents.md` — why HP must be real, not faked
- `brain/VECTOR/Decisions/003-one-hud-and-vector-env.md` — one HUD (`frontend/VECTOR.html`), hardened mode is `VECTOR_ENV=vector` (2026-09-25)
- `brain/VECTOR/Decisions/004-fail-closed-permission-tiers.md` — fail-closed tiers, tier additions flagged for review, `web_extract` (2026-09-26)
- `brain/wiki/concepts/v1-acceptance-status.md` — living V1 acceptance status (read before claiming V1 done)

## District Specs (read when building that district)
- `brain/VECTOR/Districts/01-governance.md` — Mayor's Office + LLM Council (T7)
- `brain/VECTOR/Districts/02-education.md` — Skills, Languages, Interview Prep, Learning, Karpathy Lab
- `brain/VECTOR/Districts/03-builder.md` — Coding, Projects, Startups, Investment, Agency
- `brain/VECTOR/Districts/04-security.md` — ThreatScout, MalwareHunter, NodeGuard, Privacy Guardian
- `brain/VECTOR/Districts/05-communications.md` — vectorcode channels, WhatsApp, Telegram, Discord, Signal (Hermes replaced by vectorcode)
- `brain/VECTOR/Districts/06-life.md` — Finance, Health, Relationships, Time/Calendar, Reflection
- `brain/VECTOR/Districts/07-intelligence.md` — Research, Memory Curator, Pattern Detective, News

## Owner Context
- `brain/CLAUDE.md` — full user profile (goals, working style, project overview, weekly update)
- `brain/GOALS.md` — detailed goal breakdown and current state (governed by the Equation)

## Blueprint (Brain vault `Blueprint/` — the governing strategy folder; index only, content lives in the Brain)
- `brain/Blueprint/(C) Doctrine.md` — **runtime-wired**: its "## Hydration Line" is injected into every LLM call via `core/brain/blueprint_doctrine.py` → `context_engine.session_hydration_prompt()`. Claude-independent.
- `brain/Blueprint/(C) The Equation — Top 100 Wealth Pattern.md` — W = Σ O×R×M, graduation gate (₹1L+/month × 3mo, ≤5 hrs/week owner time, churn <10%), one-product-at-a-time sequencing. Wired into `core/brain/goal_system.py` (g_first_revenue, g_equation_portfolio) and `districts/startups/idea_validator.py` (11-dimension scoring + revenue-velocity hard gate)
- `brain/Blueprint/(C) Industries — Four Waves.md` — the four industry waves 2026–2038 (content ops → SMB agentic back-office → verticals → platform + holding co)
- `brain/Blueprint/(C) Year-by-Year Math — 2026-2038.md` — age 23→35, three bands per year (downside/average/plan) with crisis windows applied + January re-forecast protocol
- `brain/Blueprint/(C) Risk & Cycles — Downturn Playbook.md` — 40-year crisis frequency analysis, projected problem windows, NORMAL/CORRECTION/CRISIS regime rules. `Regime` is machine-read by `core/brain/blueprint_doctrine.get_regime()`; idea_validator defers new starts outside NORMAL
- `brain/Blueprint/(C) Income Streams — Codebase Money Map.md` — all 7 income streams (salary, services, audience, digital products, companies, investments, secondaries) mapped to districts + stream×regime matrix
- `brain/Blueprint/(C) The Real Blueprint — Wealth by 35.md` — 12-year multi-company plan (phases, wedge product, 90-day plan)
- `brain/Blueprint/Specs/` — **Final Claude Month specs (read `00 README` first)**: 01 Reflect integrity (mostly done 2026-07-08), 02 free-tier inference maximization (60 call sites need `domain=`), 03 regime sentinel, 04 Wave-1 revenue pipeline (THE MONEY SPEC), 05 runway/finance wiring, 06 Claude exit & self-sufficiency
- `brain/Blueprint/(C) Rolling Plan Protocol.md` — the year→quarter→month→week→day rolling planning system (goal_system horizons LONG/MID/SHORT map to quarter/week/day; chief_of_staff briefs = day layer)
- `brain/Blueprint/Planning/2026-Q3.md` — **the active quarter plan — read before any build work**; quarter objectives, month plans, current week day-wise

## Vault Structure (full)
```
brain/
├── CLAUDE.md            — user profile + how to work with Arghyadeep
├── GOALS.md             — goals, progress, master plan
├── VECTOR/              — all VECTOR architecture + planning
│   ├── README.md
│   ├── Architecture.md
│   ├── Roadmap.md
│   ├── Decisions/
│   └── Districts/
├── 00 Notes/            — research, learning, ideas
├── 01 Journals/         — daily/weekly reflections
├── 02 Projects/         — active projects (FlowSync, AI Interviewer, etc.)
├── 03 Reviews/          — weekly reviews, retrospectives
├── 04 Skills/           — reusable skill notes
├── graphify-out/        — knowledge graph (graph.json + GRAPH_REPORT.md)
│   └── GRAPH_REPORT.md  — high-connectivity nodes for broad vault questions
└── wiki/                — structured wiki entries
```

## Claude Code Agents (live in brain — read on-demand, never copied)
All agents are at `brain/.claude/agents/`. Read before using as a subagent context.
- `vector-coder.md` — coding District 4, GitBot, code review
- `vector-comms.md` — comms District 6, vectorcode channels gateway (30+ platforms)
- `vector-memory-curator.md` — memory District 7, LightRAG, episodic
- `vector-researcher.md` — research District, OpenCLI, ArXiv
- `vector-security.md` — security District, ThreatScout
- `architect.md`, `code-architect.md`, `code-explorer.md` — architecture + exploration
- `loop-operator.md` — autonomous loop operations
- `planner.md`, `chief-of-staff.md` — planning + comms management
- `addy-code-reviewer.md`, `obra-code-reviewer.md` — code review
- `performance-optimizer.md`, `refactor-cleaner.md`, `security-auditor.md` — quality
- `silent-failure-hunter.md`, `test-engineer.md` — testing + failure detection
- `vc-codebase-explorer.md` — deep codebase exploration via VectorCode Intelligence (vc_search, vc_impact, vc_flow, vc_graph)
- `ads-audit-google.md`, `ads-audit-meta.md`, `ads-audit-creative.md` — paid ads platform auditors
- `ads-audit-tracking.md`, `ads-audit-budget.md`, `ads-audit-compliance.md` — ads audit specialists
- `ads-copy-writer.md`, `ads-creative-strategist.md` — ad copy and creative direction
- `ads-format-adapter.md`, `ads-visual-designer.md` — asset format validation and visual creation

## Claude Code Skills — VectorCode Intelligence (live in brain — read on-demand)
Brain skills at `brain/.claude/skills/`. VectorCode code intelligence skills:
- `vc-explore/` — semantic code search (vc_search), dependency graph queries (vc_graph_query), impact analysis (vc_impact), call flow (vc_flow), symbol lookup (vc_symbol)
- `vc-manage/` — codebase indexing (vc_index), incremental updates (vc_update), file watching (vc_watch), health checks (vc_health), project listing (vc_projects)

## Claude Code Skills — Paid Ads (live in brain — read on-demand)
Brain skills at `brain/.claude/skills/`. Ads skills:
- `ads/` — main orchestrator, routes all /ads commands (audit, landing, creative, math, plan, etc.)
- `ads-audit/` — multi-platform audit orchestrator, spawns 6 parallel agents
- `ads-google/` — Google Ads deep analysis (80 checks, GAQL, Smart Bidding)
- `ads-meta/` — Meta/Facebook Ads analysis (50 checks, Pixel, CAPI, Andromeda)
- `ads-youtube/`, `ads-linkedin/`, `ads-tiktok/`, `ads-microsoft/`, `ads-apple/` — per-platform
- `ads-creative/` — cross-platform creative quality audit
- `ads-landing/` — landing page analysis (Core Web Vitals, conversion signals)
- `ads-budget/` — budget allocation and bidding strategy
- `ads-plan/` — strategic planning (11 industry templates: SaaS, E-commerce, B2B, etc.)
- `ads-competitor/` — competitor ad research
- `ads-math/` — PPC financial calculator (CPA, ROAS, break-even, LTV:CAC)
- `ads-test/` — A/B test design (hypothesis, sample size, statistical significance)
- `ads-dna/` — brand DNA extraction from websites
- `ads-create/` — campaign concept and brief generation
- `ads-generate/` — AI image generation (Gemini→OpenAI→Stability→Replicate fallback)
- `ads-photoshoot/` — product photography in 5 styles

## Claude Code Commands (live in brain — read on-demand)
Brain commands at `brain/.claude/commands/`. Key ones:
- `loop-start.md`, `loop-status.md` — autonomous loop management
- `district.md` — scaffold a new district
- `karpathy.md` — 30min daily Karpathy session tracker
- `quality-gate.md`, `verify.md`, `checkpoint.md` — quality checks
- `orchestrate.md`, `multi-plan.md`, `multi-execute.md` — multi-agent workflows
- `save-session.md`, `resume-session.md` — session persistence
- `evolve.md`, `rules-distill.md` — VECTOR self-improvement

## Knowledge Graph
For broad questions about the vault's concepts and relationships, read `brain/graphify-out/GRAPH_REPORT.md` first — it maps the highest-connectivity nodes.
