# awesome-skills-main Audit

## 1. Repo Reality

**Source:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\awesome-skills-main`

| Metric | Count |
|--------|-------|
| Total SKILL.md files | 960 |
| Python files | 41 (CI/QA scripts, autoresearch pipeline, benchmark evaluator — not domain logic) |
| Other notable files | `CATALOG.md`, `taxonomy.yml`, `EXECUTIVE-SUMMARY.md`, `autoresearch/` pipeline |

**Skill breakdown by category:**

| Category | Skills |
|----------|--------|
| `skills/persona/` | 827 (role-play personas: farmer, construction-worker, aerospace, etc.) |
| `skills/tool/` | 116 (tool-specific expert skills across 21 subcategories) |
| `skills/workflow/` | 8 (engineering + meta workflows) |
| `skills/tools/` | 3 (engineering-simulation: abaqus, comsol, labview, openfoam) |

**Tool subcategories (116 skills):**
ai-ml (11), analytics (6), cad (5), cicd (3), cloud (5), cn-cloud (4, Chinese cloud), container (4), data-platform (6), database (7), design (6), engineering (2), engineering-simulation (4), enterprise (4), game-engine (3), iac (3), media (1 — ffmpeg), observability (6), productivity (7), scientific (3), security (6).

**Workflow skills (8):**
- `engineering/`: architecture-review, debug-diagnose, issue-triage, tdd-workflow, to-prd, zoom-out
- `meta/`: caveman, write-skill

No domain logic Python worth absorbing — the 41 Python files are skill catalog maintenance scripts (validator, linter, deduplicator, taxonomy checker, benchmark runner).

## 2. VECTOR Parity

**Already installed in `~/.claude/skills`:**

| Skill | Status |
|-------|--------|
| `to-prd` | ✅ INSTALLED |
| `zoom-out` | ✅ INSTALLED |
| `caveman` | ✅ INSTALLED |

**Not installed — `workflow/engineering`:**

| Skill | Value for VECTOR |
|-------|-----------------|
| `architecture-review` | ❌ Useful — structured ADR-style architecture review workflow |
| `debug-diagnose` | ❌ Overlaps with `/diagnose` (msitarzewski) — lower priority |
| `issue-triage` | ❌ Overlaps with `/triage` — lower priority |
| `tdd-workflow` | ❌ Overlaps with `tdd` (msitarzewski) + `test-driven-development` — skip |
| `write-skill` | ❌ Overlaps with `write-a-skill` — skip |

**Not installed — `tool/` (116 skills, 0 installed):**

High-value for VECTOR (all ❌ NOT installed):
- `langchain-expert` — VECTOR uses LangChain/LangGraph heavily
- `cuda-expert` — RTX 5070 Ti, AirLLM, custom model training
- `github-actions-expert` — VECTOR CI/CD via `.github/workflows/`
- `cloudflare-expert` — VECTOR has Cloudflare Workers + D1 + R2 + KV in Phase 3
- `terraform-expert` / `ansible-expert` — IaC for Fly.io + cloud infra
- `docker-expert` / `kubernetes-expert` — containerized cloud brain
- `grafana-expert` / `opentelemetry-expert` — VECTOR monitoring (ops/ district)
- `kafka-expert` — event bus at scale
- `fastapi-expert` (if present) — VECTOR primary API framework

**Persona skills (827):** All role-play personas for non-VECTOR use cases (farmer, factory-worker, etc.). Zero relevance to VECTOR autonomous agent system. Do not install.

**Parity score:** 3/8 workflow skills installed (37%). 0/116 tool skills installed. Core VECTOR tooling (`langchain-expert`, `cuda-expert`, `cloudflare-expert`) missing.

## 3. Frontend

N/A — no frontend code in this repo.

## 4. Verdict

**Install selectively. Do NOT bulk-install.** The 827 persona skills are dead weight for VECTOR. The 116 tool skills are reference docs (expert system prompts) that activate on-demand — the ones matching VECTOR's stack are genuinely useful.

**Overall:** ❌ Not installed (partially relevant — selective install needed)

## 5. Gaps — What to Install

**Priority 1 — Install now (direct VECTOR stack match):**
```bash
# From awesome-skills-main/skills/tool/
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/ai-ml/langchain-expert" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/ai-ml/cuda-expert" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/cicd/github-actions-expert" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/cloud/cloudflare-expert" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/iac/terraform-expert" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/container/docker-expert" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/observability/grafana-expert" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/observability/opentelemetry-expert" "C:/Users/Arghyadeep/.claude/skills/"
```

**Priority 2 — Install for Phase 3 (cloud deployment):**
```bash
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/cloud/aws-cloud-expert" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/iac/ansible-expert" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/container/kubernetes-expert" "C:/Users/Arghyadeep/.claude/skills/"
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/tool/data-platform/kafka-expert" "C:/Users/Arghyadeep/.claude/skills/"
```

**Priority 3 — Install for workflow gaps:**
```bash
cp -r "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/awesome-skills-main/skills/workflow/engineering/architecture-review" "C:/Users/Arghyadeep/.claude/skills/"
```

**Skip entirely:** All 827 `persona/` skills, `debug-diagnose` (covered by `/diagnose`), `tdd-workflow` (covered by `tdd`), `write-skill` (covered by `write-a-skill`), `issue-triage` (covered by `/triage`), `cn-cloud/` (Chinese cloud providers not in VECTOR stack), `cad/`, `game-engine/`.
