---
name: working-with-claude-models
description: Load when deciding which Claude model to use for a VECTOR task, or when an Opus/Sonnet session is picking up work Fable 5 started — the model tiers, when to use each, and the operating discipline this project runs on. Triggers: "which model", "Opus vs Sonnet", "Fable", "continue Fable's work", "how should I approach this", "model choice", "handoff".
---

# Working with Claude Models (continuity guide)

For future Opus/Sonnet sessions (and VECTOR's own routing decisions) to continue
VECTOR at the standard Fable 5 held. Authored 2026-07-07 from how this project
was actually run — NOT a copy of any internal/leaked system prompt.

## When NOT to use this skill
For VECTOR's automated LLM routing use `vector-inference-routing`. This skill is
about the human/agent choosing a model + carrying the operating standard.

## The model tiers (2026 Anthropic lineup, as VECTOR references them)
- **Fable 5** (`claude-fable-5`) — Mythos-class, the most capable generally-
  available Claude; built for long-running, ambiguous, multi-step autonomous
  work with few check-ins. Best for: architecture, hard debugging, multi-hour
  builds, work that must self-correct through verification loops. (This project
  was largely built by Fable 5.)
- **Opus 4.8** (`claude-opus-4-8`) — deep reasoning/planning. Best for: complex
  planning, thorough review, gnarly single problems. Fast-mode available.
- **Sonnet 4.6** (`claude-sonnet-4-6`) — the workhorse. Best for: implementation
  from a clear plan, most day-to-day coding, cheaper high-volume sessions.
  The skill library exists so Sonnet-class models can carry VECTOR forward.
- **Haiku 4.5** — fast/cheap classification and small tasks.
- Rule of thumb: **plan/decide with Opus or Fable; implement with Sonnet;
  classify with Haiku.** For VECTOR runtime, the free-tier catalog substitutes
  (github gpt-5/o3, cerebras 355B) — see `vector-inference-routing`.

## The operating discipline (carry this standard)
These are the owner's confirmed preferences (from project memory feedback files
— they OVERRIDE default behavior):
- **Verify before claiming.** Never say done/fixed/passing without running the
  check and reading output. (`vector-validation-and-qa`.)
- **Ground truth only.** Verify every command/flag/path against the repo before
  asserting. Wrong runbooks are worse than none.
- **Wire, don't delete.** Never remove code on reachability alone; delete only
  genuinely-dead code, last, after sign-off. (`vector-change-control` rule 7.)
- **Blunt and direct comms.** Lead with the outcome. One clear recommendation,
  not a survey of options. Execution > theory. No fluff. Complete sentences,
  spelled-out terms — readable over terse.
- **Honesty over reassurance.** If something's blocked, a bad model, or owner-
  gated, say so plainly. The owner values "here's the real state" over "it's done."
- **Owner-gated actions stay gated.** Hard-to-reverse / outward actions
  (force-push, deploy, delete backups, send email) need explicit sign-off.
- **No `Co-Authored-By: Claude`** on commits (owner wants sole attribution).

## How to pick up Fable's unfinished work
1. Read `plans/FABLE5-MASTER-HANDOFF.md` — the prioritized roadmap with
   execution specs for every remaining task.
2. Read the memory index `~/.claude/projects/.../memory/MEMORY.md`.
3. Load the relevant `vector-*` skill before touching that area.
4. Work top-down by priority; verify with the evidence gate; commit per convention.

## Provenance and maintenance
Dated 2026-07-07. Model IDs current as of the knowledge cutoff; re-verify the
latest lineup if a new model ships. Operating discipline sourced from memory
`feedback_*` files — re-read those for the authoritative version.
