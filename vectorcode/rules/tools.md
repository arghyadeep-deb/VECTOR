<!-- VECTOR-INGESTED ASSET
  Source: .claude/rules/tools.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:56+00:00
-->

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

Skills in `~/vectorcode/skills/`:

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

Skills: `mem0`, `mem0-cli`, `mem0-vercel-ai-sdk` in `~/vectorcode/skills/`.

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

Skills symlinked into `~/vectorcode/skills/`. Repo: `GitHub/garrytan_gstack/repo`.

| Use case | Command |
|----------|---------|
| Test a running VECTOR endpoint | `/browse <url>` |
| Full QA pass on deployment | `/qa` |
| Ship and verify a feature | `/ship` |
| Visual design review of dashboard | `/design` |
| Check endpoint health | `/health` |
| Debug a live issue | `/investigate` |

---

## Not Available
- **claude-mem** (nicholasgasior/claude-mem) — repo does not exist on GitHub. mem0 is the replacement.
