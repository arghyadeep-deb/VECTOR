---
name: vector-docs-and-writing
description: Load when writing or maintaining VECTOR's documents of record — OPEN_ISSUES, phase_status, handoffs, plans, memory files, skills — or when unsure of the house style. Triggers: "update the docs", "write a plan", "document this", "OPEN_ISSUES", "handoff", "house style", "where does this go".
---

# VECTOR Docs & Writing

Where the documents of record live, their templates, and the house style. Ground
truth 2026-07-07.

## When NOT to use this skill
For authoring a *skill* specifically, follow the format in any existing
`vector-*` skill + the authoring rules below. For the acceptance bar use
`vector-validation-and-qa`.

## The documents of record (one home per fact)
| Doc | Purpose | Rule |
|---|---|---|
| `docs/OPEN_ISSUES.md` | live open problems + status | update status inline; mark DONE with date, don't delete history |
| `.claude/rules/phase_status.md` | historical implementation tracker | append corrections dated; it's a ledger, not live state |
| `plans/*.md` | plans, designs, analyses, audits | one file per effort; end with Provenance + re-verify commands |
| `plans/FABLE5-MASTER-HANDOFF.md` | cross-session roadmap + EXECUTION LOG | append to the log; the canonical "what's left" |
| memory `~/.claude/projects/.../memory/*.md` + `MEMORY.md` | durable facts across sessions | one fact per file; add a one-line pointer to MEMORY.md |
| `.claude/skills/vector-*/SKILL.md` | graduated engineering knowledge | settled facts move memory→skill |

## House style (matches the owner's confirmed preferences)
- Lead with the outcome. Blunt, direct, no fluff. One recommendation, not a survey.
- Prose over bullets for explanation; tables/checklists for enumerable facts.
- Ground-truth only: every command/flag/path verified before it's written.
- Date-stamp volatile facts. End reference docs with a "Provenance and maintenance"
  section carrying one-line re-verify commands.
- Evidence discipline (from the skill-library-builder methodology): a command in a
  runbook was either RUN with its real output quoted, or tagged
  `[UNVERIFIED-CMD: reason]`. Wrong runbooks are worse than none.
- No oversell: unproven things stay labeled open/candidate.
- Commits: descriptive message; NO `Co-Authored-By: Claude` (owner sole attribution).

## Skill authoring contract (for new .claude/skills)
`.claude/skills/<name>/SKILL.md` with YAML frontmatter: `name` + a trigger-rich
`description` (say exactly when to load it, include trigger phrases). Body:
imperative runbook voice; a "When NOT to use this skill" section naming the
sibling to use instead; copy-pasteable verified commands; end with Provenance.
Put executable helpers in the skill's `scripts/` dir (see
`vector-diagnostics-and-tooling/scripts/health_snapshot.py`).

## Where a new fact goes (decision)
- One-off session detail → nowhere (dies with the session, by design).
- Durable fact about the system → memory file + MEMORY.md pointer.
- Settled engineering knowledge a successor needs → graduate into a `vector-*` skill.
- Live open problem → `docs/OPEN_ISSUES.md`. Plan/analysis → `plans/`.

## Provenance and maintenance
2026-07-07. Re-verify doc set: `ls docs/*.md plans/*.md .claude/skills/`.
Style sourced from memory `feedback_communication_style.md` + `.claude/rules/`.
