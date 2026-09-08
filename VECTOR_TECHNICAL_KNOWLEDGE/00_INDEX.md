# VECTOR Technical Knowledge Base — Index

**Repository:** VECTOR (Virtual Entity for Cognitive Tasks & Operational Reasoning)  
**Scale:** ~1.6 million lines of code, ~7,000 Python files  
**Audit Date:** 2026-08-12  
**Status:** Comprehensive technical reconnaissance

---

## Purpose

This knowledge base provides a complete, code-grounded technical understanding of VECTOR's architecture, implementation, runtime behavior, capabilities, limitations, and development state. Every claim is backed by actual code evidence.

**Critical Principle:** Current code is the primary source of truth. Documentation, TODOs, and previous audits may be outdated.

---

## Knowledge Base Structure

### Level 1 — System Level
- `01_GLOBAL_SYSTEM_MAP.md` — What VECTOR is and how major systems connect
- `02_REPOSITORY_INVENTORY.md` — Complete directory structure and purpose
- `03_VECTOR_VS_REPOSITORY.md` — What is VECTOR vs vendored/third-party

### Level 2 — Subsystem Level
- `04_RUNTIME_AND_BOOT.md` — Startup sequence, initialization, entry points
- `05_AUTONOMOUS_LOOP.md` — Core autonomous loop architecture
- `06_CONTEXT_ENGINE.md` — World state, context assembly
- `07_GOALS_AND_PLANNING.md` — Goal hierarchy, planning systems
- `08_DECISION_ENGINE.md` — Candidate generation, scoring, selection
- `09_GOVERNOR_AND_PERMISSIONS.md` — Routing, governance, permission gates
- `10_AGENT_ARCHITECTURE.md` — Agent base, lifecycle, registry
- `11_VECTOR_CITY.md` — Districts, governance, council
- `12_HP_AND_EVOLUTION.md` — HP system, agent evolution
- `13_MEMORY_ARCHITECTURE.md` — All memory systems
- `14_REFLECTION.md` — Reflection, consolidation, learning
- `15_MODELS_AND_INFERENCE.md` — All model integrations
- `16_TOOL_SYSTEM.md` — All tools and capabilities
- `17_COMMUNICATIONS.md` — All communication adapters
- `18_PHONE_AND_DEVICE.md` — Phone/ADB/device control
- `19_CODING_SYSTEM.md` — Coding autonomy
- `20_RESEARCH_INTELLIGENCE.md` — Research capabilities
- `21_FINANCE_SYSTEM.md` — Financial/investment functionality
- `22_FRONTEND.md` — UI, dashboards
- `23_BACKEND_API.md` — FastAPI, endpoints
- `24_DATABASES.md` — All storage systems
- `25_EVENTS_AND_SCHEDULERS.md` — Event bus, cron, background tasks
- `26_TESTING_AND_EVALS.md` — All tests, evals, benchmarks
- `27_OBSERVABILITY.md` — Logs, metrics, monitoring
- `28_SECURITY.md` — Security review, vulnerabilities
- `29_CONFIGURATION.md` — Config, env vars, feature flags
- `30_DEPLOYMENT.md` — Deployment, infrastructure
- `31_EXTERNAL_INTEGRATIONS.md` — All external services

### Level 3 — Implementation Level
- `32_ALL_DISTRICTS.md` — Every district with agents, capabilities
- `33_ALL_AGENTS.md` — Every agent indexed
- `34_CAPABILITY_MATRIX.md` — What VECTOR can actually do
- `35_REACHABILITY_MATRIX.md` — What is actually wired vs dead code
- `36_RUNTIME_SCENARIOS.md` — 15+ end-to-end traces
- `37_KNOWN_ISSUES.md` — All bugs, TODOs, technical debt
- `38_DOCUMENTATION_VS_CODE.md` — Discrepancies

### Assessment
- `39_AUTONOMY_ASSESSSSMENT.md` — Evidence-based autonomy matrix
- `40_CRITICAL_FINDINGS.md` — Top findings, risks, gaps
- `41_DEVELOPMENT_ROADMAP.md` — Prioritized roadmap
- `42_FINAL_ARCHITECTURE.md` — Final system map

---

## How to Use This Knowledge Base

### For Understanding VECTOR
1. Start with `01_GLOBAL_SYSTEM_MAP.md` — understand the big picture
2. Read `39_AUTONOMY_ASSESSMENT.md` — what is genuinely autonomous
3. Read `40_CRITICAL_FINDINGS.md` — what works, what doesn't
4. Read `37_REAL_CURRENT_CAPABILITIES.md` — what VECTOR can do TODAY

### For Development
1. Read relevant subsystem document (e.g., `13_MEMORY_ARCHITECTURE.md`)
2. Check `34_CAPABILITY_MATRIX.md` — current implementation status
3. Check `35_REACHABILITY_MATRIX.md` — what is actually wired
4. Check `37_KNOWN_ISSUES.md` — what needs fixing

### For Debugging
1. Check `27_OBSERVABILITY.md` — how to diagnose issues
2. Check `28_SECURITY.md` — security concerns
3. Check `30_DEPLOYMENT.md` — deployment issues
4. Trace through `36_RUNTIME_SCENARIOS.md` — understand execution paths

### For Auditing
1. Check `38_DOCUMENTATION_VS_CODE.md` — discrepancies
2. Check `35_REACHABILITY_MATRIX.md` — dead code
3. Check `28_SECURITY.md` — vulnerabilities
4. Check `40_CRITICAL_FINDINGS.md` — risks

---

## Cross-Reference System

Every document uses this format for cross-references:

```markdown
See: `10_AGENT_ARCHITECTURE.md`
```

File references use exact paths:

```markdown
File: `core/loop/autonomous_loop.py:123-145`
```

---

## Status Legend

| Status | Meaning |
|--------|---------|
| ✅ IMPLEMENTED | Fully implemented and wired |
| ⚠️ PARTIAL | Partially implemented, some gaps |
| 🔧 STUB | Stub exists, not functional |
| ❌ BROKEN | Implemented but broken |
| 💀 DEAD | Code exists but never called |
| 🧪 EXPERIMENTAL | Experimental, not production |
| 📦 VENDORED | Third-party code |
| ❓ UNVERIFIED | Cannot verify from code |
| 🔒 CONFIG-DEPENDENT | Requires specific config |

---

## Key Files (Quick Reference)

### Entry Points
- `run_vector.py` — Main launcher (loop/api/smoke/doctor modes)
- `core/api/app.py` — FastAPI application
- `core/loop/autonomous_loop.py` — Autonomous loop

### Core Systems
- `core/loop/context_engine.py` — Context/world state
- `core/brain/goal_system.py` — Goals
- `core/loop/decision_engine.py` — Decision making
- `core/city/governor.py` — Routing/governance
- `core/loop/permission_gateway.py` — Permission gates
- `core/city/agent_base.py` — Agent base class
- `core/city/agent_registry.py` — Agent registry

### Memory
- `core/memory/episodic.py` — Episodic memory (SQLite)
- `core/memory/policy.py` — Policy memory
- `core/memory/reasoning_memory.py` — Reasoning chains
- `core/memory/obsidian_sync.py` — Obsidian integration

### Models
- `core/inference/provider_client.py` — Model routing
- `core/inference/ollama_safe.py` — Ollama integration
- `core/inference/llm_providers.py` — 27 providers

### Districts
- `districts/` — All 33+ districts
- `config/agent_manifest.yaml` — Agent definitions

---

## Maintenance

This knowledge base should be updated whenever:
- Major architecture changes
- New subsystems added
- Critical bugs found
- Capabilities change
- Documentation discrepancies discovered

**Last Updated:** 2026-08-12  
**Next Review:** 2026-08-19 (weekly)

---

## Contact

**Questions:**
- Arghyadeep Deb (owner)
- VECTOR Governance District (maintainer)

**Issues:**
- File at: `districts/governance/issue_tracker.py`
- Or: GitHub issues

---

**REPORT COMPLETE**

**Knowledge Base Location:**
`C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\VECTOR_TECHNICAL_KNOWLEDGE\`
