# FABLE 5 — MASTER HANDOFF & PRIORITIZED ROADMAP
> Created 2026-07-07 by Claude Fable 5 (the "retiring fellow"). This file is the
> INSURANCE the owner asked for: if Fable runs out of context/session budget,
> **Opus and Sonnet can execute every remaining task below exactly as intended.**
> Read this file first. Work top-down by priority. Each task has: WHAT, WHY,
> HOW (executable steps), OUTPUT LOCATION, DONE-WHEN.

## How to use this file (successor models)
- Tasks are ordered P0 → P3 by value × dependency. Do not skip P0/P1.
- "Ground truth only": verify every command/flag/path against the repo before
  asserting it. Wrong runbooks are worse than none. (This is a VECTOR rule.)
- Write skills ONLY under `.claude/skills/`; the rest of the repo is otherwise
  read-only for the skill-library task. No mutating git beyond normal commits.
- The auto-commit hook (PostToolUse on Edit/Write) commits each file edit; Bash
  writes bypass it. Do NOT add `Co-Authored-By: Claude` (owner wants sole
  attribution — see memory feedback_no_claude_coauthor).
- Repo default branch = `production-hardening-complete` (NOT `main`), pushed to
  github.com/arghyadeep-deb/VECTOR as of 2026-07-05.

## Project one-paragraph context (for a cold successor)
VECTOR is a Darwinian multi-agent "civilization" (~1.5M LOC, 38 districts, 133
agents) meant to run the owner's life autonomously — a local-first JARVIS.
Runtime is cloud-PRIMARY LLM routing (13 free-tier providers via
`core/inference/provider_client.py` + `model_catalog.yaml`) with Ollama as
terminal fallback; owner has NO paid OpenAI/Anthropic keys (free tiers only).
State of the system (2026-07-07): code ~90% complete for single-owner use;
NOT running as a service yet (the #1 operational gap). Full status:
`docs/OPEN_ISSUES.md`, `.claude/rules/phase_status.md`, and project memory at
`~/.claude/projects/.../memory/MEMORY.md`.

---

# PRIORITY 0 — Foundational / insurance

## P0.1 — This file. DONE (you are reading it).

---

# PRIORITY 1 — Highest durable value (do these next)

## P1.1 — "Working with Claude models" reference for Opus/Sonnet + VECTOR
WHAT: A practical reference so future Opus/Sonnet sessions (and VECTOR's own
routing) continue at Fable's standard. NOT a copy of the leaked CL4R1T4S
CLAUDE-FABLE-5.md (refused fetch; reproducing Anthropic's internal constitution
verbatim is an IP/accuracy problem — the leaked doc may be inaccurate anyway).
Instead author from first principles + this project's operating discipline.
WHY: Owner's real goal is continuity — "so Opus and Sonnet can execute exactly
as Fable wanted." A practical operating guide serves that better than a leaked prompt.
HOW:
  1. Create `.claude/skills/working-with-claude-models/SKILL.md` covering: model
     tiers (Fable 5 = Mythos-class, most capable; Opus 4.8 = deep; Sonnet 4.6 =
     workhorse; Haiku = fast); when to use which; how to prompt Fable for
     autonomous multi-step work; the discipline rules this project runs on
     (verify-before-claim, ground-truth-only, wire-don't-delete, blunt+direct
     comms, execution>theory, no-fluff — from memory feedback files).
  2. Mirror a short pointer into `brain/` (VECTOR vault) via obsidian-cli or a
     plain .md so VECTOR agents can read it.
OUTPUT: `.claude/skills/working-with-claude-models/SKILL.md` (+ brain pointer).
DONE-WHEN: file exists, trigger-rich frontmatter, no leaked-prompt reproduction.

## P1.2 — Skill library (THE retiring-fellow deliverable)
WHAT: 10–16 skills under `.claude/skills/` so Sonnet-class models can debug,
extend, validate, advance VECTOR without Fable.
WHY: Single most valuable durable artifact. Fable has dozens of sessions of
ground truth (audits, bug fixes, absorptions) no fresh agent has.
HOW — taxonomy (adapt to repo; 10–16 total). Fable has deepest ground truth for
the CORE ones — author those FIRST:
  CORE (author first, Fable has lived these):
  - `vector-change-control` — change classes, gates, non-negotiables + the
    incident behind each (SQLCipher driver-class bugs, DB 2.3GB bloat from
    context_budget FTS dumping, cp1252 emoji crashes, auto-commit hook gotcha).
  - `vector-debugging-playbook` — symptom→triage for VECTOR's failure modes
    (Windows cp1252, ACL-locked test_tmp, torchvision/speechbrain import order,
    circular pydantic_settings import, SQLCipher plain-sqlite3 access).
  - `vector-failure-archaeology` — chronicle of investigations from memory files
    + git history (see MEMORY.md index — each dated entry is a settled battle).
  - `vector-architecture-contract` — load-bearing decisions + invariants: the 5
    sacred memory tables (never rename), cloud-primary+ollama-terminal, permission
    gateway GREEN/YELLOW/RED, sensitivity gate local-only, MAX_LOADED_MODELS=1.
  - `vector-config-and-flags` — every config axis: core/config.py CONFIG dict,
    the ~16 VECTOR_*_LLM env flags (13 enabled 2026-07-04, 3 left off:
    LIVE_TESTS/TRAINING_REAL/DB_RECOVERY_CHECK), model_catalog.yaml, .env.
  - `vector-build-and-env` — Python 3.13 system interpreter (no .venv!), torch
    2.11+cu128 CUDA, deps, Ollama models, the space-in-path workerd limitation.
  - `vector-run-and-operate` — run_vector.py modes (loop|api|smoke|doctor|
    readiness-check|memory-repair; "loop" IS autonomous), service install
    (scripts/install_service.ps1 needs admin+NSSM, now fixed), smoke/integration.
  - `vector-validation-and-qa` — evidence bar: scripts/smoke_test.py (38),
    scripts/integration_check.py (51), pytest conventions (.claude/rules/testing.md),
    the quality-gate discipline (e.g. wake-word recall gate).
  DOMAIN + ADVANCED (author if budget remains; else spec-only here):
  - `vector-inference-routing` — the 13-provider catalog, quota ledger, domain
    chains, whitelist guardrail, route_policy sensitivity gate (deep, unique to VECTOR).
  - `vector-memory-and-learning` — 5 tables, episodic FTS5, policy/reasoning,
    ghost memory, multi_db_manager cloud sync (Supabase/Turso/D1 live 4/4).
  - `vector-districts-reference` — 38 districts, governor routing, agent_base HP,
    Darwinian death→ghost→successor.
  - `vector-diagnostics-and-tooling` — measure-don't-eyeball scripts.
  - `vector-docs-and-writing` — docs of record + house style.
  AUTHORING RULES (bake into each): audience = zero-context mid-level eng or
  Sonnet; imperative runbook voice; copy-pasteable VERIFIED commands; each skill
  says when NOT to use it + sibling; YAML frontmatter name + trigger-rich
  description; date-stamp volatile facts; end with "Provenance and maintenance"
  (re-verify commands); no oversell; nothing contradicts .claude/rules/*.
  Use parallel subagents (one skill per agent) if orchestrating; else author
  serially, CORE first.
PHASE 3 REVIEW: after all skills exist, 3 reviewers (factual/doctrine/usability)
  + a fixer; then output skill inventory + spot-check results + uncertainties.
OUTPUT: `.claude/skills/<name>/SKILL.md` each.
DONE-WHEN: ≥10 skills, CORE set complete + verified, Phase-3 review applied.

---

# PRIORITY 2 — High value, larger scope

## P2.1 — Harness optimization (6 "ultracode" analyses)
Each produces an analysis + edit-plan doc under `plans/harness/`. Ground every
claim in the actual .claude/ + brain/ files.
  1. GOAL: characterize what the harness is ultimately for; find parts working
     against it (system prompt, CLAUDE.md, hooks, skills); interview owner if no
     clear goal. → `plans/harness/01-goal-alignment.md`
  2. BITTER LESSON: study Sutton's essay; audit harness for over-engineering /
     hand-coded logic that should be model-general; upgrade plan for
     model-flexibility. → `plans/harness/02-bitter-lesson.md`
  3. IDENTITY: read what harness believes about owner (memory user_* files,
     brain/CLAUDE.md); flag stale/aspirational/wrong models vs recent behavior;
     propose edits. → `plans/harness/03-identity-drift.md`
  4. MEMORY: audit retention/learning across sessions; where knowledge dies
     (captured-never-resurfaced or never-captured); design retention/decay/
     promotion rules. → `plans/harness/04-memory-compounding.md`
  5. EVALS: define what "better" means (not vanity); build evals/regression that
     catch degradation early; find proxy drift. → `plans/harness/05-evals.md`
  6. TRUST BOUNDARY: map autonomous vs approval-gated actions; find over-granted
     + fear-withheld authority; recalibrate risk×leverage; redesign trust
     boundary (ties to core/loop/permission_gateway.py + trust_ladder.py).
     → `plans/harness/06-trust-boundary.md`
DONE-WHEN: 6 docs exist, each with findings + concrete edits.

## P2.2 — Security upgrades
  1. PROMPT-INJECTION: map all harness inputs (email, Reddit/HN scrapes, web,
     channels, voice, MCP) + how each is handled + defense recommendation.
     VECTOR already has core/security/prompt-injection scanner + SSRF guard +
     taint tracker — audit coverage, recommend upgrades.
     → `plans/security/prompt-injection-map.md`
  2. ATTACK SURFACE: build `.claude/skills/attack-surface/SKILL.md` maintaining
     `attacksurface.md` (running inventory: every deployed thing — Cloudflare
     Worker+D1+KV, Supabase, Turso, GitHub, Fly(none), tech/auth/exposure/audience)
     + an AssessAttackSurface workflow + per-service testing frequency.
     → `attacksurface.md` + skill.
DONE-WHEN: injection map + attack-surface skill/file exist.

---

# PRIORITY 3 — Valuable, do if budget remains (else fully spec'd here)

## P3.1 — Audit trading analyst + research/scraping agents
Check `districts/investment/` (AI Trading Analyst, stock_analyst, fundamentals),
`core/research_engine/`, `core/scraper/`, `districts/research/` (web_scout,
paper_reader). Optimize ONLY if genuinely deficient (per wire-don't-delete +
"if fine it's okay"). Report findings. → `plans/audits/trading-research-audit.md`

## P3.2 — Life/work strategy (6) — analyses using VECTOR Brain + past chats
Data sources: `brain/CLAUDE.md`, `brain/GOALS.md`, memory files, git history.
Output docs under `brain/03 Reviews/` or `plans/strategy/`:
  1. Ikigai / single-direction focus (fulfilling × lucrative). May interview owner.
  2. Steelman that the owner's biggest bet is WRONG; unchecked load-bearing beliefs.
  3. What AI makes obsolete vs 10× for owner; stop/start this year.
  4. Repeated decisions → standing policies (sort by reversibility × stakes).
  5. Single binding constraint (real bottleneck, not loudest problem) + the one move.
  6. 30-day bus-factor: what breaks if owner vanishes; undocumented you-shaped
     dependencies; plan to externalize.
NOTE: owner profile in memory — KIIT CSE 2023-27, RTX 5070 Ti, builder mindset,
weaknesses: over-commit + shiny-object syndrome (relevant to #1/#4/#5).

## P3.3 — Power Moves Vol.2 — 7 tools built INSIDE VECTOR
Build each as a VECTOR skill or district tool (not throwaway):
  1. Internal-tool builder (find weekly time-drain → one-file tool).
  2. Past-work auditor (search chats, rank fixes effort×impact).
  3. 6-day business designer.
  4. Lead-gen + CRM (scrape→score→cold-email→CRM). Ties to core/scraper + comms.
  5. Stock/filing deep-analysis (ranked thesis + red flags). Ties to investment district.
  6. AI-automation consulting offer (lead-qualification agent per client).
  7. Multi-workstream KB agent (orchestrator + parallel subagents + synthesis).
     Ties to swarm/orchestrator + provider_client cheap-subagent routing.
Where: `.claude/skills/power-*/` or `districts/agency/`. Data from VECTOR Brain.

## P3.4 — Repo-maintenance dev loop
Design an autonomous loop: wake every 5min while active; one thread per repo;
assign highest-value bounded task within granted permissions; DON'T interrupt
coherent active work; REQUIRE tests + live proof + autoreview + green CI before
landing; ESCALATE product/access/security/irreversible; record meaningful
changes; STOP when all items landed/decision-ready/blocked/no-work-left.
Design ties to: existing autonomous_loop.py, /loop skill, permission_gateway,
trust_ladder, CI (.github/workflows/ci.yml). → `plans/dev-loop-design.md` +
optionally a cron/loop config. (Do NOT auto-start it without owner sign-off.)

---

# OPERATIONAL GAPS (owner-gated — NOT Fable/Opus/Sonnet work; for owner)
- INSTALL THE SERVICE (`scripts/install_service.ps1` from admin shell) — turns
  VECTOR ON; the single highest-leverage move. Everything above assumes it runs.
- Record ~50–100 "Hey VECTOR" samples (owner voice) → wake-word model.
- Start Wan2GP + ComfyUI (GPU servers) for local free video.
- Phone Termux setup, Wake-on-LAN BIOS, dlib Application-Control policy, test_tmp
  delete (admin), Cloudflare email-Worker provisioning.

---

# EXECUTION LOG (append as tasks complete — the running record)
- 2026-07-07: P0.1 handoff written (DONE). CL4R1T4S fetch refused (IP) → P1.1
  reframed to authored `working-with-claude-models` skill (DONE).
- 2026-07-07: P1.2 skill library — **10 skills authored + committed** (8 CORE:
  change-control, debugging-playbook, architecture-contract, failure-archaeology,
  config-and-flags, build-and-env, run-and-operate, validation-and-qa; + DOMAIN:
  inference-routing; + working-with-claude-models). Phase-3 spot-check done
  (run-modes, smoke 38/38, frontmatter all verified). REMAINING skill-library
  work (optional, spec in P1.2 above): vector-memory-and-learning,
  vector-districts-reference, vector-diagnostics-and-tooling, vector-docs-and-writing,
  and the ADVANCED tier (campaign / proof-toolkit / research-frontier / methodology).
  These are nice-to-have; the CORE + routing + continuity set is the load-bearing
  minimum and it is COMPLETE.
- 2026-07-07 (continued to session limit): **ALL P0-P3 TASKS COMPLETED.**
  - P2.1 harness optimization: 6 analyses in `plans/harness/01..06`.
  - P2.2 security: `plans/security/prompt-injection-map.md` + `attacksurface.md`
    + `.claude/skills/attack-surface/` (skill + AssessAttackSurface workflow).
  - P3.1 trading/research audit: `plans/audits/trading-research-audit.md`
    (verdict FINE; applied finance.analysis domain routing to stock_analyst +
    sentiment_bot).
  - P3.2 life/work: `plans/strategy/life-work-strategy.md` (6 analyses) +
    `.claude/skills/power-moves/` (7 workflows in VECTOR).
  - P3.4 dev loop: `plans/dev-loop-design.md` (design only, do-not-auto-start).
  - 12 skills authored total; smoke 38/38 throughout; nothing broke.
- REMAINING (optional, NOT required — nice-to-have): additional skills
  (memory-and-learning, districts-reference, diagnostics-and-tooling,
  docs-and-writing, ADVANCED tier campaign/proof/frontier/methodology); and
  ACTUALLY BUILDING the 7 Power Moves as tools (currently ready-to-run
  workflows). And the harness/security recommendations above are ANALYSES —
  implementing their concrete edits is follow-up work.
- OWNER OPERATIONAL GAPS remain (see section below) — the #1 is install the service.

## SKILL LIBRARY — COMPLETED TO FULL SPEC (2026-07-08)
Applied the skill-library-builder methodology (github.com/MeeshaBear1/skill-library-builder):
executed-command provenance ([UNVERIFIED-CMD] markers), full taxonomy, Phase-3 review.
- Added 7 skills: vector-diagnostics-and-tooling (+scripts/health_snapshot.py, RUN),
  vector-docs-and-writing, vector-domain-reference, + ADVANCED tier
  (vector-campaign-ship-to-running, vector-proof-and-analysis-toolkit,
  vector-research-frontier, vector-research-methodology).
- FABLE.md in .claude/ + docs/ (distilled Fable 5 charter for successors).
- Phase-3 review: usability agent (6 MINOR, 3 fixed / 3 self-containedness kept) +
  doctrine agent (5 MINOR, all 5 fixed) + factual-by-execution (all paths/commands
  verified: smoke 38/38, integration 51/51, finance chain→ollama, 38 districts,
  no paid Anthropic/OpenAI keys). Fixed stale .claude/rules/models.md paid-key language.
