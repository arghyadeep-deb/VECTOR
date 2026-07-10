# Tools — Mandatory Plugin Protocol for VECTOR

All 6 tool groups are globally installed and active. Use them every session.

---

## MANDATORY WORKFLOW FOR EVERY VECTOR CODING TASK

```
1. brainstorming      → BEFORE any new district / module / feature
2. writing-plans      → structured plan doc before implementing
3. executing-plans    → implement from the plan, step by step
4. [security-guidance → auto-fires on every file edit — don't bypass]
5. [mem0 skill        → when touching District 7 or any memory/storage code]
6. [frontend-design   → when touching dashboard or any web UI]
7. verification-before-completion → BEFORE marking any task done
8. [gstack /browse    → verify any deployed endpoint visually]
9. [code-review       → when a district or branch is complete]
```

---

## PLUGIN 1 — SUPERPOWERS (obra/superpowers)

Skills in `~/.claude/skills/`:

| Situation | Skill |
|-----------|-------|
| New district / agent / module / feature | `brainstorming` — HARD GATE |
| Before implementing | `writing-plans` |
| Executing a written plan | `executing-plans` |
| Before marking done | `verification-before-completion` |
| Debugging broken VECTOR code | `systematic-debugging` |
| Writing tests | `test-driven-development` |
| Multiple parallel subagents | `dispatching-parallel-agents` |
| Merging a branch | `finishing-a-development-branch` |
| Security audit of a module | `security-review` |

---

## PLUGIN 7 — MATTPOCOCK ENGINEERING SKILLS (msitarzewski/skills)

17 skills installed in `~/.claude/skills/`. Use these for daily engineering work:

### Engineering
| Situation | Skill |
|-----------|-------|
| Hard bug / performance regression | `/diagnose` — 6-phase debug loop (better than systematic-debugging for complex bugs) |
| Stress-test a plan with domain docs | `/grill-with-docs` — grilling + updates CONTEXT.md + ADRs |
| Rescue a messy codebase | `/improve-codebase-architecture` — deepening analysis, run weekly |
| Throwaway prototype (logic or UI) | `/prototype` — terminal app or UI variants |
| Issue tracker / domain setup | `/setup-matt-pocock-skills` — run once per repo |
| TDD red-green-refactor | `/tdd` — vertical slices, deeper than test-driven-development |
| Break PRD into GitHub issues | `/to-issues` — vertical slice decomposition |
| Turn conversation into PRD | `/to-prd` — synthesizes context into a GitHub issue |
| Triage incoming issues | `/triage` — state machine triage loop |
| Explain unfamiliar code in context | `/zoom-out` — big-picture perspective |

### Productivity
| Situation | Skill |
|-----------|-------|
| Stress-test your own plan | `/grill-me` — relentless one-question-at-a-time interview |
| Compact conversation for next agent | `/handoff` — cross-agent handoff doc |
| Cut token usage 75% | `/caveman` — drops filler, keeps accuracy |
| Create a new Claude Code skill | `/write-a-skill` |

### Misc
| Situation | Skill |
|-----------|-------|
| Block dangerous git in a new repo | `/git-guardrails-claude-code` |
| Set up Husky pre-commit hooks | `/setup-pre-commit` |
| Search/create VECTOR Obsidian notes | `/obsidian-vault` — vault path: V.E.C.T.O.R. Brain\ |

---

## PLUGIN 2 — CODE REVIEW (official plugin)

`/code-review <PR#>` — use when any VECTOR district or feature branch is complete.

5-agent review: CLAUDE.md compliance, bug scan, git history, past PRs, code comments. Only surfaces issues above 80 confidence.

---

## PLUGIN 3 — FRONTEND DESIGN (official plugin)

`/frontend-design` — use for VECTOR dashboard, any web interface, monitoring UI.

---

## PLUGIN 4 — SECURITY GUIDANCE (official plugin)

Auto-wired as PreToolUse hook in `~/.claude/settings.json`. Fires on every Edit/Write.

Catches dangerous patterns: shell injection, unsafe code evaluation, insecure deserialization, XSS, GitHub Actions injection.

Do not disable. Address any warning before continuing.

---

## PLUGIN 5 — MEM0 (mem0ai/mem0)

Skills: `mem0`, `mem0-cli`, `mem0-vercel-ai-sdk` in `~/.claude/skills/`.

VECTOR District 7 (Memory Curator) usage:
```python
from mem0 import Memory   # self-hosted OSS — stays on device
m = Memory()
m.add(messages, user_id="customer_123")           # after every interaction
results = m.search(query, user_id="customer_123") # before routing/responding
```

Critical: Never use `MemoryClient` — it sends data to external cloud. VECTOR Rule 11.

Handles: episodic memory, customer history, agent learned context, sales/inventory interactions.

---

## PLUGIN 6 — GSTACK (garrytan/gstack)

Skills symlinked into `~/.claude/skills/`. Repo: `GitHub/garrytan_gstack/repo`.

| Use case | Command |
|----------|---------|
| Test a running VECTOR endpoint | `/browse <url>` |
| Full QA pass on deployment | `/qa` |
| Ship and verify a feature | `/ship` |
| Visual design review of dashboard | `/design` |
| Check endpoint health | `/health` |
| Debug a live issue | `/investigate` |

---

## PLUGIN 8 — PONYTAIL (DietrichGebert/ponytail) — added 2026-07-09, owner decision

Minimal-code enforcement ("lazy senior developer" decision ladder: needed? → exists in
codebase? → stdlib? → platform-native? → installed? → only then write).

**WIRED INTO VECTOR RUNTIME (not just Claude):** vendored at `ponytail/`;
`core/inference/ponytail_guard.py` injects the ladder into every `coding.*`/`saas.*` LLM
call via `vectorcode_llm.chat()` — all ~25 coding agents build lean, Claude-independent.
Tune behavior by editing `ponytail/skills/ponytail/SKILL.md` (no code change).
Claude-side (this session): `/plugin marketplace add DietrichGebert/ponytail` +
`/plugin install ponytail@ponytail` for `/ponytail-review` and `/ponytail-audit`.

| Situation | Command |
|-----------|---------|
| **Every MODE 2 SaaS build (Wave-1 product code) — MANDATORY, always on** | decision ladder active by default (`full` intensity) |
| Before committing any feature diff | `/ponytail-review` — delete-list for over-engineering |
| Codebase necessity sweep (scheduled: Q3 W2–W3) | `/ponytail-audit` — whole-repo scan |

Rule: ponytail verdicts feed the same gate as code review — address or consciously
override, never ignore. Complements (does not replace) verification-before-completion.

## Not Available
- **claude-mem** (nicholasgasior/claude-mem) — repo does not exist on GitHub. mem0 is the replacement.
