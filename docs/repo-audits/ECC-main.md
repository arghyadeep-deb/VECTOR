# ECC-main Audit

**Repo path:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\ECC-main`
**Audit date:** 2026-06-01
**License:** MIT
**Version:** v2.0.0-rc.1

---

## 1. Repo Reality

ECC ("Everything Claude Code") is **not Elliptic Curve Cryptography**. It is a Claude Code agent harness plugin — a production-grade system of agents, skills, hooks, rules, and scripts designed to make Claude Code more capable and reliable across multiple AI coding harnesses (Claude Code, Cursor, Codex, OpenCode, GitHub Copilot, Zed, Antigravity, etc.).

### What ECC Actually Does

**Scale (verified from filesystem):**
- 63 specialized sub-agents (`.md` files in `agents/`)
- 249 skills (`skills/` directories with `SKILL.md`)
- 79 slash-command shims (`commands/`)
- 115 rules files across 19 language packs (`rules/`)
- 47 hook scripts (`scripts/hooks/*.js`) covering 8 Claude Code hook event types
- 1 Python Tkinter desktop dashboard (`ecc_dashboard.py`)
- 1 alpha Rust control-plane binary (`ecc2/`)

### Concrete Feature List

**A. Agent Library (63 agents)**
Language-specific code reviewers and build-error resolvers: Python, TypeScript, Go, Rust, Java, Kotlin, C++, C#, F#, Swift, Dart, Flutter, HarmonyOS/ArkTS, Django, FastAPI, React. Plus domain agents: planner, architect, code-reviewer, security-reviewer, refactor-cleaner, doc-updater, tdd-guide, e2e-runner, database-reviewer, loop-operator, harness-optimizer, chief-of-staff, mle-reviewer, performance-optimizer, silent-failure-hunter, GAN planner/generator/evaluator, network agents, healthcare reviewer, a11y-architect, homelab-architect, marketing-agent, open-source packaging trio.

**B. Hook Infrastructure (Node.js-based, cross-platform)**
- `PreToolUse`: Bash preflight dispatcher (quality gate, tmux guard, git push reminder, block `--no-verify`), doc-file warning, compact suggestions, observation capture for continuous learning, governance event capture (secrets/policy), config-protection blocker, MCP health check, fact-forcing gate (blocks Edit without investigation)
- `PostToolUse`: Quality gate runner (format/typecheck after edits), design quality check (warns on generic-looking UI), JS/TS edit accumulator, console.log warning, governance capture, session activity tracker, context monitor (warns on context exhaustion/scope creep/cost), ECC metrics bridge
- `PostToolUseFailure`: MCP health tracking and reconnect
- `PreCompact`: State save before compaction
- `SessionStart`: Load previous session summary + package manager detection + instinct injection
- `Stop`: Batch format+typecheck (Biome/Prettier, tsc), console.log scan, session state persistence, pattern extraction (continuous learning), cost tracking, desktop notification
- `SessionEnd`: Session end lifecycle marker

**C. Continuous Learning v2 (instinct-based)**
Observes every tool use via hooks (100% reliable), creates atomic "instincts" with confidence scores (0.3–0.9), project-scoped by git remote URL hash, promotes high-confidence cross-project instincts to global. Commands: `/instinct-status`, `/evolve`, `/instinct-export`, `/instinct-import`, `/promote`, `/projects`.

**D. Autonomous Loop Patterns (skill: `autonomous-loops`)**
Six documented loop architectures: Sequential Pipeline (`claude -p`), NanoClaw REPL, Infinite Agentic Loop (spec-driven parallel), Continuous Claude PR Loop (CI-gate + auto-fix), De-Sloppify cleanup pattern, Ralphinho/RFC-Driven DAG orchestration (multi-agent, dependency DAG, worktree isolation, merge queue with eviction).

**E. Rules Library (115 files)**
Language-agnostic common rules (coding-style, testing, security, git-workflow, patterns, performance, hooks, agents) plus language packs: TypeScript, Python, Go, Swift, PHP, Rust, C++, C#, Java, Kotlin, Dart, Perl, ArkTS, Ruby, React, Angular, web, zh (Chinese).

**F. Skill Library (249 skills)**
Domain skills: backend-patterns, frontend-patterns, api-design, security-review, tdd-workflow, verification-loop, eval-harness, continuous-learning-v2, strategic-compact, cost-aware-llm-pipeline, iterative-retrieval, autonomous-loops, parallel-execution-optimizer, ralphinho-rfc-pipeline. Framework skills: Django, Laravel, Spring Boot, Quarkus, NestJS, React, Next.js, Vue/Nuxt, Vite, SwiftUI, Compose Multiplatform, PyTorch, Perl. Content/operator skills: article-writing, content-engine, market-research, investor-materials, social-publisher, brand-voice, videodb, video-editing, x-api. Niche skills: ClickHouse, Redis, PostgreSQL, MySQL, Prisma, docker-patterns, deployment-patterns, e2e-testing, network diagnostics, Blender motion, GAN harness, iOS Liquid Glass, Apple FoundationModels, Swift concurrency 6.2, MLE workflow, prediction market, EVM/DeFi, scientific literature, WCAG accessibility, and ~160 more.

**G. Desktop Dashboard (`ecc_dashboard.py`)**
Tkinter app: tabbed interface for Agents/Skills/Commands/Rules/Settings with search/filter, dark/light theme toggle, font customization, project logo in header and taskbar.

**H. ECC2 Alpha (Rust, `ecc2/`)**
Rust control-plane binary. Commands: `dashboard`, `start`, `sessions`, `status`, `stop`, `resume`, `daemon`. Alpha — not general release.

**I. Cross-Harness Support**
Cursor (15 hook events, DRY adapter), Codex app+CLI (`.codex/config.toml`, 32 skills), OpenCode (full plugin, 11 event types), GitHub Copilot (instruction + prompt layers), Zed, Antigravity, JoyCode, Qwen CLI, Gemini CLI adapters.

---

## 2. VECTOR Parity

| Feature | VECTOR Equivalent | Verified Output | Status |
|---------|------------------|-----------------|--------|
| **63 language-specific agents** (Python reviewer, Go reviewer, Rust reviewer, etc.) | Brain has 38 agents; project `.claude/agents/` has 30+. Language-specific reviewers for Python/Go/Rust/etc. are absent in both brain and project agents. | `ls brain/.claude/agents` — no `python-reviewer.md`, `go-reviewer.md`, `rust-reviewer.md`, etc. | ❌ Missing (language-specific reviewers/build-resolvers) |
| **Hook: session-start with context injection** | VECTOR's `finish_notification.py` (Stop hook) and `auto_commit.py` exist; SessionStart hook is absent. | `settings.json` hooks — no `SessionStart` key found. | ❌ Missing |
| **Hook: continuous learning v2 (instinct capture)** | `vectorcode/src/reasoning_bank.py` + `ReasoningBank` stores patterns post-decision. Fires through `decision_engine.py`, not hook-based. Only fires when VECTOR processes decisions, not on every Claude Code tool use. | Decision engine logs confirmed; no hook-based observation pipeline. | ⚠️ Partial (VECTOR captures reasoning chains, not Claude Code session patterns) |
| **Hook: strategic compact suggestion** | Not present. | `settings.json` hooks list — no compact suggestion hook. | ❌ Missing |
| **Hook: context exhaustion/scope-creep monitor** | Not present. | `settings.json` hooks — no context monitor. | ❌ Missing |
| **Hook: fact-forcing gate (block Edit without investigation)** | Not present. | `settings.json` hooks — no `gateguard-fact-force`. | ❌ Missing |
| **Hook: governance capture (secrets/policy events)** | `core/security/prompt_injection_scanner.py` + SSRF guard in `provider_client.py`. Not hook-based; fires at API boundary, not on every Claude Code tool use. | Verified in `core/api/routers/commands.py` — scan_text() on API input only. | ⚠️ Partial (API boundary only, not tool-level) |
| **Hook: batch format+typecheck at Stop** | `lint_on_save.py` runs ruff on PostToolUse. No TypeScript batch typecheck (VECTOR is Python-only). | Hook confirmed in `settings.json`. | ✅ Python ruff covered; ❌ TS/JS not applicable |
| **Hook: config-protection blocker** | `file_protection.py` PreToolUse hook. | Confirmed in `settings.json`. | ✅ Real & working |
| **Continuous learning / instinct system** | `vectorcode/src/reasoning_bank.py` (57 entries, Python patterns). Fires per-decision, not per tool-use. No confidence scoring, no project scoping, no evolution pipeline. | `ReasoningBank loads 57 entries live` — confirmed in phase_status.md. | ⚠️ Partial |
| **Autonomous loop patterns documentation** | `brain/.claude/skills/autonomous-loops/` present (confirmed in brain skills list). VECTOR's autonomous loop is `core/loop/autonomous_loop.py` — a real running Python loop, not a `claude -p` scripting pattern. Different concept entirely. | `ls brain/.claude/skills` confirms `autonomous-loops` present. | ✅ Present (different domain — Python loop vs shell scripting patterns) |
| **249 skills library** | Brain has 371 skills (confirmed count). Brain skill list includes `autonomous-loops`, `cost-aware-llm-pipeline`, `agent-harness-construction`, `eval-harness`, etc. | `ls brain/.claude/skills | wc -l` → 371. | ✅ Brain already has more skills total |
| **Rules library (115 files, 19 language packs)** | VECTOR `.claude/rules/` has 11 project-level rules (architecture, code_style, commands, districts, libraries, models, phase_status, testing, tools, memory, brain_index). No global rules dir exists. | `ls .claude/rules` — 11 files, Python-only focus. | ⚠️ Partial (Python rules covered by code_style.md; TypeScript/Go/Rust/Java/Swift/PHP packs absent) |
| **Tkinter dashboard** | VECTOR dashboard is planned (Next.js, not built yet per phase_status.md). No Python Tkinter dashboard. | `phase_status.md`: "Next.js Dashboard ❌ Not built yet" | ❌ Missing |
| **MCP server configs** | `core/mcp_server.py` — 14 real tools + kanban + claims + guidance. Fully custom, deeply VECTOR-integrated. | Confirmed in phase_status.md. | ✅ Real & working (more sophisticated than ECC's MCP configs) |
| **Cross-harness support (Cursor/Codex/OpenCode)** | Not applicable — VECTOR uses only Claude Code + local Ollama. | N/A — VECTOR is single-owner, single-harness. | N/A |
| **AgentShield security scanner** | `core/security/prompt_injection_scanner.py` + `core/audit/` (MerkleAuditChain). VECTOR's is Python, runtime. ECC's is an npm CLI for Claude Code config auditing. | Confirmed present in phase_status.md session 2026-05-29. | ✅ Covered (different scope — runtime vs config audit) |
| **ECC2 Rust control plane** | Not applicable — VECTOR has its own Python autonomous loop and API. | N/A | N/A |
| **Context-save/restore skills** | Brain has `context-restore`, `context-save` confirmed in global skills. | `ls ~/.claude/skills` — both present. | ✅ Present |

---

## 3. Frontend / Panel Spec

### Dashboard (`ecc_dashboard.py`)

ECC ships a working Python Tkinter desktop application. For VECTOR's planned Next.js monitoring dashboard, this is a reference implementation for the "component explorer" panel.

**Panel concept: "Harness Explorer"**
A panel in VECTOR's future dashboard that shows:
- All active agents (name, HP, purpose, last-used timestamp)
- All installed skills (category filter, search)
- All commands (slash-name, description)
- Hook health status (which hooks are active and their last trigger time)

Implementation note: ECC's `ecc_dashboard.py` does filesystem scanning of `agents/*.md` YAML frontmatter, `skills/*/SKILL.md`, and `commands/*.md`. VECTOR's equivalent would query `core/city/agent_registry.py` for live agent data and `core/mcp_server.py` tool list for capability inventory.

---

## 4. Verdict

**SAFE TO DELETE** (with 3 targeted extractions listed in Section 5)

### Reasoning

ECC is a **Claude Code harness plugin** — its primary value is agent/skill/rules content for humans to install into `~/.claude/`. VECTOR is an **autonomous AI operating system** — it runs Python 24/7, uses Ollama locally, and manages its own agents in `core/city/`. These are different domains with minimal overlap.

**Why bulk absorption is wrong:**
1. ECC's 249 skills and 63 agents are SKILL.md/markdown prompt files. VECTOR already has 371 brain skills and 38 brain agents, plus 133 Python agent files across 33 districts. Adding ECC's markdown would bloat Claude's context with non-VECTOR-relevant content (Quarkus patterns, HarmonyOS, Perl, Blender motion, etc.) that VECTOR's Python-first stack will never use.
2. ECC's hook infrastructure is JavaScript/Node.js. VECTOR's hooks are Python. Zero code reuse possible. ECC's `session-start.js` injects context into Claude Code sessions — VECTOR already does this more powerfully via `context_engine.py` and `session_hydration_prompt()`.
3. ECC's rules (TypeScript, Swift, PHP, Java, etc.) are irrelevant to VECTOR's Python-only backend stack.
4. ECC's cross-harness support (Cursor, Codex, OpenCode, Gemini CLI) has no bearing on VECTOR's single-owner, local-first Claude Code + Ollama architecture.
5. ECC2 Rust control plane is alpha and conceptually duplicate of VECTOR's Python autonomous loop.

**The 3 genuine gaps** (Section 5) are extractable as lightweight additions without bulk absorption.

---

## 5. Gaps

### Gap 1 — Language-Specific Code Reviewer Agents (HIGH VALUE, LOW EFFORT)

**What ECC has:** 30+ language/framework-specific reviewer agents: `python-reviewer.md`, `go-reviewer.md`, `rust-reviewer.md`, `typescript-reviewer.md`, `java-reviewer.md`, `fastapi-reviewer.md`, `react-reviewer.md`, `django-reviewer.md`, etc. Each has focused YAML frontmatter (`name`, `description`, `tools`, `model`).

**What VECTOR has:** `addy-code-reviewer.md`, `obra-code-reviewer.md` (generic). `vector-coder.md` (generates code, not reviews it).

**Recommendation:** Copy the following 8 agents verbatim into `brain/.claude/agents/` — they are pure markdown prompt files, MIT-licensed, no code required:
- `python-reviewer.md` — Python/PEP8/type hints/security
- `fastapi-reviewer.md` — FastAPI patterns (VECTOR's API framework)
- `go-reviewer.md` — Go idioms
- `rust-reviewer.md` — Rust safety/ownership
- `typescript-reviewer.md` — TS/JS patterns
- `silent-failure-hunter.md` — Already in brain but check for fresher version
- `tdd-guide.md` — TDD enforcement agent
- `harness-optimizer.md` — Tunes Claude Code config for reliability/cost

**Source:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\ECC-main\agents\`

### Gap 2 — Hook: SessionStart Context Injection + Strategic Compact Suggestion (MEDIUM VALUE, MEDIUM EFFORT)

**What ECC has:** `scripts/hooks/session-start.js` injects the most recent session summary, learned instincts (confidence >= 0.7), and package manager info into Claude's context at session start. `suggest-compact.js` warns at 50+ tool calls to compact before context degrades.

**What VECTOR has:** No SessionStart hook. No compact suggestion hook. VECTOR relies on `context_engine.py` and `session_hydration_prompt()` for context, but these run inside the Python autonomous loop — not in Claude Code's session lifecycle.

**Recommendation:** Port two lightweight Python hooks to complement existing VECTOR hooks:

1. `session_start_hook.py` — On SessionStart, emit the last 5 `reasoning_memory` entries + active SHORT/MID goal summaries to Claude's context. Analogous to how `session_hydration_prompt()` works but fired as a hook.
2. `suggest_compact_hook.py` — On PreToolUse (Edit/Write), count tool invocations in a temp counter file; emit a compact suggestion warning when >= 40 tool calls in session.

Both are ~30-50 line Python scripts following the existing hook pattern in `.claude/hooks/`.

**Source inspiration:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\ECC-main\scripts\hooks\session-start.js`, `suggest-compact.js`

### Gap 3 — Continuous Learning v2: Confidence-Scored Instinct Architecture (LOW VALUE NOW, HIGH VALUE YEAR 2)

**What ECC has:** A complete instinct pipeline: hook-based observation (every tool call) → pattern detection (background Haiku agent) → atomic instinct files with confidence 0.3–0.9 → project-scoped storage → evolution into skills/commands → cross-project promotion. Storage outside `~/.claude/` to avoid sensitive-path guard.

**What VECTOR has:** `vectorcode/src/reasoning_bank.py` (57 entries, fires per decision, no confidence scoring, no project scoping, no hook-based capture). `core/memory/reasoning_memory.py` stores chains post-LLM-call.

**Gap:** VECTOR's reasoning bank fires only when VECTOR makes decisions. It does not observe every Claude Code tool use during build sessions (when the human is using Claude Code to build VECTOR). This means patterns from 10+ months of build sessions are not being captured at the tool-use level.

**Recommendation:** Defer to Year 2 (post v1.0 production). The architecture is sound but requires: (a) a background Haiku agent subscription, (b) dedicated observation storage outside the codebase, (c) a promotion/evolution pipeline. This is a `meta_cognition.py` Gap 8 analog — not blocking anything now. Document as a future enhancement to `core/memory/reasoning_memory.py`.

**Source reference:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\ECC-main\skills\continuous-learning-v2\SKILL.md`

---

## Summary Table

| Component | ECC Count | VECTOR Has | Action |
|-----------|-----------|-----------|--------|
| Agents (language reviewers) | 30+ reviewers | 4 generic | Copy 8 targeted agents |
| Skills (framework/language) | 249 | 371 in brain | No action — brain already richer |
| Hook: SessionStart context | 1 (JS) | 0 | Port as ~30-line Python |
| Hook: compact suggestion | 1 (JS) | 0 | Port as ~30-line Python |
| Hook: continuous learning | Full pipeline (JS+Python) | Partial (decision-only) | Defer Year 2 |
| Rules (language packs) | 115 files, 19 languages | 11 files, Python-only | No action — not VECTOR's stack |
| Dashboard (Tkinter) | Working Python app | Planned (Next.js) | Use as reference for HUD panel spec |
| Cross-harness support | 8 harnesses | Claude Code only | Not applicable |
| MCP configs | Generic GitHub/Supabase | 14 custom VECTOR tools | No action — VECTOR's is better |
| ECC2 Rust control plane | Alpha | N/A | Not applicable |
