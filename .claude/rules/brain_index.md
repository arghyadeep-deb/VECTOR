# Brain Index — V.E.C.T.O.R. Brain Vault

Vault path: `brain/` (junction → C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain\)
Read any file below with the Read tool using the `brain/` prefix.

## Always-Loaded (via @import in CLAUDE.md)
- `brain/VECTOR/Architecture.md` — autonomous loop, coroutines, session hydration, memory schema, voice pipeline, council, HP system, deployment
- `brain/VECTOR/Roadmap.md` — 50-day build plan, phase breakdown, Karpathy track, OpenMythos timeline

## VECTOR Planning (read on-demand)
- `brain/VECTOR/README.md` — what VECTOR is, stack table, 20 districts overview, critical rules
- `brain/VECTOR/Decisions/001-local-first-no-cloud-runtime.md` — why Claude API is never called at runtime
- `brain/VECTOR/Decisions/002-darwinian-hp-over-static-agents.md` — why HP must be real, not faked

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
- `brain/GOALS.md` — detailed goal breakdown and current state

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
- `vector-comms.md` — comms District 6, Hermes gateway
- `vector-memory-curator.md` — memory District 7, LightRAG, episodic
- `vector-researcher.md` — research District, OpenCLI, ArXiv
- `vector-security.md` — security District, ThreatScout
- `architect.md`, `code-architect.md`, `code-explorer.md` — architecture + exploration
- `loop-operator.md` — autonomous loop operations
- `planner.md`, `chief-of-staff.md` — planning + comms management
- `addy-code-reviewer.md`, `obra-code-reviewer.md` — code review
- `performance-optimizer.md`, `refactor-cleaner.md`, `security-auditor.md` — quality
- `silent-failure-hunter.md`, `test-engineer.md` — testing + failure detection

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
