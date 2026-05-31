# Repo Audit — skills-main (mattpocock/skills)

> Audited: 2026-05-31 · Auditor: Claude (Opus 4.8) · Read + run only, no VECTOR code modified.
> Repo: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\skills-main`

**TL;DR:** This is **mattpocock/skills** — "Skills For Real Engineers", a pack of **29 Claude-Code
agent-harness SKILLS** (markdown process docs, zero runtime code). Confirmed via `README.md`
("My agent skills that I use every day"). They are *instructions to a CLI agent*, not Python.
VECTOR cannot depend on the Claude Code harness — the audit question is whether VECTOR's
runtime (districts + autonomous loop) already DOES what each skill teaches, OR the *value* is
reimplementable via `provider_client`. Verdict: **18 ✅ / 7 ⚠️ / 4 ❌** (the 4 ❌ are TS/course-
specific tooling with no VECTOR relevance). **0 of 29 exist in `brain/.claude/skills/`** — but
**19 are already installed in the GLOBAL `~/.claude/skills/`** (this repo IS the upstream source
of that install, surfaced in the session's available-skills list). The clone is redundant.

---

## Section 1 — Repo Reality

`skills/**/SKILL.md` — **29 skills** across 6 folders. Each is a markdown reference an agent loads
via the Claude Code `Skill` tool. No Python, no runtime.

### Engineering (10)
| Skill | What it does |
|---|---|
| `diagnose` | Disciplined hard-bug loop: build a fast pass/fail feedback signal → reproduce → minimise → hypothesise → instrument → fix → regression-test. |
| `tdd` | Red-green-refactor, vertical-slice tracer bullets, behavior-through-public-interface tests. Anti-pattern guidance (no horizontal slicing). |
| `triage` | Issue-tracker state machine (bug/enhancement × needs-triage/ready/etc.); writes AI-disclaimer-prefixed comments. |
| `to-prd` | Synthesizes current conversation → PRD → publishes to issue tracker. No interview. Deep-module thinking. |
| `to-issues` | Breaks a plan/PRD into independently-grabbable vertical-slice (tracer-bullet) issues. |
| `zoom-out` | One-shot prompt: "go up a layer of abstraction, map relevant modules + callers using domain glossary." |
| `improve-codebase-architecture` | Finds "deepening opportunities" (shallow→deep modules), deletion test, seam analysis, ADR-aware. |
| `grill-with-docs` | Relentless one-question-at-a-time plan interview + updates `CONTEXT.md`/ADRs inline (ubiquitous language). |
| `prototype` | Throwaway prototype to answer one question — terminal logic app OR multiple toggleable UI variants. |
| `setup-matt-pocock-skills` | One-time per-repo scaffold: issue tracker + triage labels + domain-doc layout into AGENTS.md/CLAUDE.md. |

### Productivity (4)
| Skill | What it does |
|---|---|
| `grill-me` | Same relentless plan interview as grill-with-docs, minus the doc-writing. |
| `handoff` | Compacts current conversation into a handoff doc (saved to OS temp dir) for a fresh agent. |
| `caveman` | Ultra-compressed comms mode; ~75% token cut by dropping filler, keeping technical accuracy. |
| `write-a-skill` | Meta-skill: create new skills with progressive disclosure + bundled resources. |

### Misc (4)
| Skill | What it does |
|---|---|
| `git-guardrails-claude-code` | Installs a Claude Code PreToolUse hook blocking dangerous git (push/reset --hard/clean/branch -D). |
| `migrate-to-shoehorn` | Migrate TS test files from `as` assertions → `@total-typescript/shoehorn`. **TS-only.** |
| `scaffold-exercises` | Create course-exercise dir trees passing `ai-hero-cli` lint. **Course-author tooling.** |
| `setup-pre-commit` | Install Husky + lint-staged + Prettier + typecheck + test pre-commit hooks. **JS/TS toolchain.** |

### Personal (2)
| Skill | What it does |
|---|---|
| `obsidian-vault` | Search/create/manage Obsidian notes with wikilinks + index notes. |
| `edit-article` | Restructure + tighten an article draft (DAG-of-information ordering). |

### In-progress (5)
| Skill | What it does |
|---|---|
| `review` | Two-axis diff review (Standards vs Spec) via parallel sub-agents, side-by-side report. |
| `teach` | Stateful multi-session teaching of a concept inside the workspace. |
| `writing-beats` | Assemble an article as a journey of narrative "beats", choose-your-own-adventure. |
| `writing-fragments` | Grilling session mining heterogeneous writing "fragments" into a raw-material doc. |
| `writing-shape` | Shape a pile of raw markdown into a publishable article conversationally. |

### Deprecated (4)
| Skill | What it does |
|---|---|
| `design-an-interface` | "Design it twice" — multiple radical interface designs via parallel sub-agents. |
| `qa` | Conversational QA session → files GitHub issues with domain language. |
| `request-refactor-plan` | Interview → tiny-commit refactor plan → file as GitHub issue. |
| `ubiquitous-language` | Extract a DDD glossary from conversation → `UBIQUITOUS_LANGUAGE.md`. |

**Count:** 10 engineering + 4 productivity + 4 misc + 2 personal + 5 in-progress + 4 deprecated = **29**.

---

## Section 2 — VECTOR Parity (does the RUNTIME do this?)

**Directory comparison first.** Checked every skill name against `brain/.claude/skills/`
(junction → `V.E.C.T.O.R. Brain\.claude\skills`, **361 skills**):

```
$ for s in diagnose grill-with-docs ... ; do test -d "$s" && echo PRESENT || echo ABSENT; done
ABSENT: (all 29)
```

**0 of 29 are in `brain/.claude/skills/`.** But they ARE installed globally:

```
$ cd ~/.claude/skills   (90 skills total)
GLOBAL-PRESENT: diagnose, tdd, triage, caveman, handoff, grill-me, grill-with-docs,
                zoom-out, to-prd, to-issues, prototype, write-a-skill, setup-pre-commit,
                git-guardrails-claude-code, obsidian-vault, edit-article,
                improve-codebase-architecture, scaffold-exercises, setup-matt-pocock-skills
                + migrate-to-pytest-partial  (VECTOR's Python port of migrate-to-shoehorn)
```

**This repo `skills-main` is the upstream SOURCE of those 19 global installs** (`npx skills add
mattpocock/skills`). The clone is a vendored copy of an already-installed pack. The 4 deprecated +
in-progress writing skills are the ones not installed globally.

### Engineering parity

| Capability | VECTOR runtime equivalent (verified path) | Verdict |
|---|---|---|
| `diagnose` (hard-bug loop) | `districts/coding/bug_hunter.py` + `core/audit` SessionRepair + global `systematic-debugging`/`investigate` skills | ✅ runtime has bug-hunting; loop discipline = skill |
| `tdd` (red-green-refactor) | `districts/coding/test_writer.py` + `districts/qa/` (`api_tester.py`, `reality_checker.py`, `silent_failure_hunter.py`, `model_qa_specialist.py`) | ✅ test agents exist; vertical-slice discipline = skill |
| `improve-codebase-architecture` | `districts/coding/architect_bot.py` + `districts/coding/refactor_cleaner.py` | ✅ architect + refactor agents live |
| `to-prd` | `districts/projects/project_planner.py` + `core/loop/context_engine.py` (`session_hydration_prompt`) | ⚠️ planner exists; PRD-template publish-to-tracker is a thin harness wrapper |
| `to-issues` | `districts/projects/project_planner.py` + `deadline_watcher.py` + GitBot (`districts/coding/git_bot.py`, PyGithub) | ⚠️ planning + GitHub API present; vertical-slice issue split is prompt-only |
| `triage` | `districts/qa/agent.py` + GitBot issue API | ⚠️ QA + issue API exist; the triage state machine itself is a prompt convention |
| `zoom-out` | `core/loop/context_engine.py` (14-domain world state) + VectorCode `vc_graph`/`vc_flow` (`brain/.claude/agents/vc-codebase-explorer.md`) | ✅ richer than the skill (real call-graph, not a prompt) |
| `grill-with-docs` / `grill-me` | `brainstorming` (HARD GATE, global) + `core/brain/red_team_agent.py` (adversarial review) + `epistemic_tracker.py` | ✅ adversarial questioning is a runtime layer, not just a prompt |
| `prototype` | No dedicated throwaway-prototype agent; `rapid_prototyper.py` exists in `districts/coding/` | ⚠️ rapid_prototyper covers spirit; UI-variant toggling is frontend-harness-specific |
| `setup-matt-pocock-skills` | N/A — bootstraps the *skills' own* per-repo config (issue tracker/labels). Pure harness plumbing. | ❌ not a VECTOR capability (configures the skill pack itself) |

### Productivity parity

| Capability | VECTOR runtime equivalent | Verdict |
|---|---|---|
| `handoff` | `core/jcode/session_persistence.py` + `core/loop/context_engine.py` (`session_hydration_prompt()` runs BEFORE every LLM call) | ✅ runtime persists + rehydrates context natively |
| `caveman` (token compression) | `core/jcode` trajectory auto-compact + `core/engine` TokenJuice + `context-budget` skill | ✅ VECTOR compacts context at the runtime level |
| `grill-me` | (see grill-with-docs above) `brainstorming` + red_team | ✅ |
| `write-a-skill` | `brain/.claude/skills/skill-creator/` + global `write-a-skill`/`writing-skills` | ✅ already present; build-session only |

### Misc / Personal / In-progress / Deprecated parity

| Capability | VECTOR equivalent | Verdict |
|---|---|---|
| `git-guardrails-claude-code` | `security-guidance` PreToolUse hook (active globally) + `core/sandbox/` VectorSandbox; CI in `.github/workflows/` (ci/lint/tests/release) | ✅ guardrails enforced at hook + sandbox level |
| `migrate-to-shoehorn` (TS) | `migrate-to-pytest-partial` — VECTOR's **Python port** (dataclass/TypedDict partial fixtures), installed globally | ✅ Python equivalent already shipped; TS original irrelevant |
| `setup-pre-commit` (Husky/JS) | `.github/workflows/*.yml` (CI gates) + global `setup-pre-commit`; VECTOR is Python (no Husky) | ⚠️ CI covers the intent; JS-toolchain skill itself N/A |
| `scaffold-exercises` (ai-hero course) | none — course-authoring tooling for mattpocock's own product | ❌ no VECTOR relevance |
| `obsidian-vault` | `districts/reflection/journal_writer.py` + `districts/memory_curator/` (watchdog Obsidian sync) + global `obsidian-vault`/`obsidian-cli` | ✅ runtime reads/writes the vault autonomously |
| `edit-article` | `districts/content/script_generator.py` + global writing skills | ✅ content district + writing skills |
| `review` (in-progress) | `code-review` plugin + `districts/qa/` + `brain/.claude/agents/addy-code-reviewer.md` | ✅ multi-agent review already wired |
| `teach` / `writing-beats/fragments/shape` (in-progress) | Personal writing workflows; `districts/content/` + global writing-* skills cover the spirit | ⚠️ no dedicated agent; low value for an autonomous system |
| `qa` (deprecated) | `districts/qa/` full suite (10 agents incl. `evidence_collector.py`, `accessibility_auditor.py`) | ✅ superseded by a richer QA district |
| `design-an-interface` (deprecated) | `districts/coding/architect_bot.py` + global `design-an-interface` | ✅ |
| `request-refactor-plan` (deprecated) | `districts/coding/refactor_cleaner.py` + `vector-refactor-cleaner.md` | ✅ |
| `ubiquitous-language` (deprecated) | `core/knowledge/wiki_parser.py` + `improve-codebase-architecture` glossary | ⚠️ glossary extraction partial; deprecated upstream anyway |

**Tally: 18 ✅ · 7 ⚠️ · 4 ❌.** None of the ⚠️ are blockers — they are harness-shaped wrappers
(PRD/issue publishing, UI-variant toggling, JS pre-commit) whose *underlying capability* already
exists in a VECTOR district. The 4 ❌ are mattpocock-product-specific (course exercises, skill-pack
config) or TS-only with a Python port already shipped.

---

## Section 3 — Frontend

**None.** This is a pure markdown skill pack — no HTML/CSS/JS, no dashboard, no UI. The only
"UI" mentioned is inside `prototype`/`design-an-interface` skills as *instructions* for an agent
to scaffold throwaway UI in the target project — no shippable frontend artifact in the repo.

---

## Section 4 — Verdict + Delete-Readiness

**Verdict: SAFE TO DELETE (the clone) — already installed globally + capabilities covered.**

This repo is a **vendored copy of an already-installed global skill pack** (`~/.claude/skills/`,
19 of these 29 present). Keeping `GitHub/skills-main` as a second copy adds nothing — the global
install is the live one Claude Code loads. Of the 29:

- **18 ✅** — VECTOR's runtime/districts already do the work; the skill is build-session sugar.
- **7 ⚠️** — capability exists in a district; only the harness wrapper (publish-to-tracker,
  UI toggle, Husky) is skill-shaped. Not worth porting into VECTOR runtime.
- **4 ❌** — `setup-matt-pocock-skills`, `scaffold-exercises`, `migrate-to-shoehorn`,
  + `setup-pre-commit` (partial): mattpocock-product / TS-toolchain specific. Zero VECTOR value.

### Tracker semantics

| Bucket | Items | Reason |
|---|---|---|
| **DELETE-NOW** | The entire `GitHub/skills-main` clone | Redundant vendored copy of the globally-installed pack; nothing references it from VECTOR runtime. No genuinely-missing capability. |
| **DELETE-AFTER** | — | (nothing gated on an integration step) |
| **KEEP** | The 19 already in `~/.claude/skills/` (global, NOT in this repo dir) | Useful for *your* build sessions. They live in the global skills dir independent of this clone. |

**Genuinely-missing VECTOR runtime capability: NONE.** Every ⚠️ maps to an existing district +
the missing piece is Claude-Code-harness plumbing (issue-tracker publishing, UI-variant routing)
that an autonomous Python system does not need. `migrate-to-shoehorn` was the one arguable gap and
VECTOR already shipped the Python equivalent (`migrate-to-pytest-partial`).

**Bottom line:** Do NOT copy any of these into `brain/.claude/skills/` or into VECTOR code.
Delete the `skills-main` clone; the global install already gives you the build-session value.
