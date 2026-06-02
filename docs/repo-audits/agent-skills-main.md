# agent-skills-main Audit

## 1. Repo Reality

**Source:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\agent-skills-main`
**Total top-level items:** 11 (agents/, docs/, hooks/, references/, scripts/, skills/, .claude/, .gemini/, .opencode/, AGENTS.md, CLAUDE.md, CONTRIBUTING.md, LICENSE, README.md)

### Skill Files (23 skill directories under `skills/`)

| Skill | Phase |
|-------|-------|
| interview-me | Define |
| idea-refine | Define |
| spec-driven-development | Define |
| planning-and-task-breakdown | Plan |
| incremental-implementation | Build |
| test-driven-development | Build |
| context-engineering | Build |
| source-driven-development | Build |
| doubt-driven-development | Build |
| frontend-ui-engineering | Build |
| api-and-interface-design | Build |
| browser-testing-with-devtools | Verify |
| debugging-and-error-recovery | Verify |
| code-review-and-quality | Review |
| code-simplification | Review |
| security-and-hardening | Review |
| performance-optimization | Review |
| git-workflow-and-versioning | Ship |
| ci-cd-and-automation | Ship |
| deprecation-and-migration | Ship |
| documentation-and-adrs | Ship |
| shipping-and-launch | Ship |
| using-agent-skills | Meta |

### Agent Persona Files (`agents/`)
- `code-reviewer.md` — 5-dimension review persona (correctness, readability, architecture, security, performance)
- `security-auditor.md` — security-focused persona
- `test-engineer.md` — testing persona

### Additional Assets
- **Hooks:** `hooks/hooks.json` — SessionStart hook (`session-start.sh`), SDD cache hooks (pre/post), simplify-ignore hooks
- **Commands:** `.claude/commands/` — 7 slash commands: `/spec`, `/plan`, `/build`, `/test`, `/review`, `/code-simplify`, `/ship`
- **References:** `references/` — 5 checklists: accessibility, orchestration-patterns, performance, security, testing-patterns
- **Docs:** setup guides for Claude Code, Cursor, Copilot, Gemini CLI, Windsurf, OpenCode
- **Language:** Pure markdown (SKILL.md files). One shell script (`idea-refine/scripts/idea-refine.sh`). One JS validator (`scripts/validate-skills.js`). No Python beyond what the skills orchestrate.

---

## 2. VECTOR Parity

**Script output (Step 2 from task spec):**
```
brain skills count: 371
agent-skills-main: 11 top-level items
```

### Skills Already in Brain (21/23)
All 21 confirmed present in `brain/.claude/skills/`:
`api-and-interface-design`, `browser-testing-with-devtools`, `ci-cd-and-automation`, `code-review-and-quality`, `code-simplification`, `context-engineering`, `debugging-and-error-recovery`, `deprecation-and-migration`, `documentation-and-adrs`, `frontend-ui-engineering`, `git-workflow-and-versioning`, `idea-refine`, `incremental-implementation`, `performance-optimization`, `planning-and-task-breakdown`, `security-and-hardening`, `shipping-and-launch`, `source-driven-development`, `spec-driven-development`, `test-driven-development`, `using-agent-skills`

### Skills NOT in Brain (2/23)
| Skill | Description |
|-------|-------------|
| `doubt-driven-development` | Adversarial fresh-context reviewer before non-trivial decisions; 5-step CLAIM→EXTRACT→DOUBT→RECONCILE→STOP loop; cross-model escalation support |
| `interview-me` | One-question-at-a-time intent extraction with confidence tracking; produces confirmed Outcome/User/Why-now/Success/Constraint/Out-of-scope restate |

### Agent Personas
| Agent | In Brain |
|-------|----------|
| `code-reviewer.md` | No (brain has `addy-code-reviewer.md` and `obra-code-reviewer.md` — different personas with different focus) |
| `security-auditor.md` | Yes (`security-auditor.md` in brain) |
| `test-engineer.md` | Yes (`test-engineer.md` in brain) |

### Other Assets Not in Brain
- `.claude/commands/` slash commands — brain has its own command set; these 7 (`/spec`, `/plan`, `/build`, `/test`, `/review`, `/code-simplify`, `/ship`) may overlap but not confirmed identical
- `hooks/hooks.json` + shell hooks — VECTOR uses its own hook system via `settings.json`; these hooks are agent-skills-specific lifecycle management
- `references/` checklists — brain does not have equivalents; 5 standalone reference files

---

## 3. Frontend: N/A

Skill collection — no frontend components.

---

## 4. Verdict

**KEEP — DO NOT DELETE.** Two unique skills (`doubt-driven-development` and `interview-me`) are absent from brain and have high VECTOR value. The `code-reviewer.md` persona is also distinct from brain's existing reviewer agents. The `references/` checklists and `.claude/commands/` are minor but not redundant.

**Action:** Copy the 2 missing skills and `code-reviewer.md` agent into brain before deleting. See Gaps below.

---

## 5. Gaps — Copy These to Brain

### Priority 1 — Missing Skills (copy directly)

**`doubt-driven-development/SKILL.md`** → `brain/.claude/skills/doubt-driven-development/SKILL.md`
- Adversarial fresh-context review discipline for non-trivial decisions
- Unique: implements CLAIM→EXTRACT→DOUBT→RECONCILE→STOP loop with 3-cycle bound
- Cross-model escalation via Gemini CLI / Codex CLI (read-only sandbox invocation)
- VECTOR use: directly applicable to decision_engine.py candidate scoring review; also valuable before any RED action in autonomous_loop

**`interview-me/SKILL.md`** → `brain/.claude/skills/interview-me/SKILL.md`
- Structured intent extraction before any plan, spec, or code
- Unique: hypothesis+confidence-number on every turn; "can you predict the next 3 reactions?" stop test
- Distinct from `/grill-me` (stress-tests a plan you already have) — this runs before the plan exists

### Priority 2 — Agent Persona (copy if code-reviewer coverage is wanted)

**`agents/code-reviewer.md`** → `brain/.claude/agents/code-reviewer.md`
- Generic 5-dimension (correctness/readability/architecture/security/performance) reviewer
- Complements `addy-code-reviewer.md` (web quality) and `obra-code-reviewer.md` (superpowers style)
- Worth keeping as a neutral baseline reviewer

### Priority 3 — Reference Checklists (optional, low priority)
`references/orchestration-patterns.md` — multi-agent orchestration anti-patterns; useful alongside dispatching-parallel-agents skill
`references/security-checklist.md` — supplement to security-and-hardening
`references/testing-patterns.md` — supplement to test-driven-development
`references/performance-checklist.md` — supplement to performance-optimization
`references/accessibility-checklist.md` — supplement to frontend-ui-engineering

These can be placed in `brain/.claude/references/` if that directory exists or is created.
