# Harness Analysis 01 — Goal Alignment
> 2026-07-07, Fable 5. What is the harness FOR, and what works against it.

## What the harness is ultimately trying to accomplish
Two goals, sometimes in tension:
1. **Build VECTOR** — a local-first autonomous JARVIS that runs the owner's life.
2. **Be a high-standard autonomous coding partner** on that build — do
   multi-step work with minimal check-ins, verify before claiming, honesty over
   reassurance.

## Parts working AGAINST the goal (findings)
1. **Global `CLAUDE.md` mandates 6 "always-active" plugin protocols with HARD
   GATES** (brainstorming/writing-plans/executing before ANY feature;
   verification-before-completion; mem0; gstack; etc.). This is heavy ceremony
   that in practice was NOT followed every session (this project shipped via
   direct execution + verification, not the full gate ritual). **Mis-alignment:**
   the harness *says* one process but the *effective* process is different →
   the model either wastes turns performing ceremony or quietly ignores the
   CLAUDE.md, eroding trust in the file. FIX: rewrite CLAUDE.md to describe the
   process actually used (verify-before-claim, ground-truth, wire-don't-delete,
   act-when-you-can-act) and reserve hard gates for genuinely irreversible work.
2. **Ceremony vs autonomy tension.** The system prompt (harness) rightly pushes
   "act when you can act, don't ask permission for reversible work," but
   CLAUDE.md's brainstorming/writing-plans gate pulls the other way. They
   contradict. FIX: make CLAUDE.md defer to the autonomy directive; gate only
   destructive/outward actions.
3. **Skill sprawl (272 skills).** Most are absorbed (ruflo). Signal-to-noise for
   the model choosing a skill is low. FIX: the new `vector-*` skills are the
   curated, ground-truth set — consider a "load these first for VECTOR" pointer.
4. **No single source of truth for "current state."** State is spread across
   OPEN_ISSUES.md, phase_status.md, 36 memory files, and now the handoff. FIX:
   designate `plans/FABLE5-MASTER-HANDOFF.md` + `MEMORY.md` as the two canonical
   entry points; everything else is detail.

## Concrete edits
- Rewrite `~/.claude/CLAUDE.md` mandatory-protocol section to match effective
  practice; downgrade hard gates to "for irreversible/outward work only."
- Add a top-of-CLAUDE.md pointer: "State: read plans/FABLE5-MASTER-HANDOFF.md +
  memory/MEMORY.md first. VECTOR skills: load vector-* before touching an area."
- Deduplicate skill guidance (the `vector-*` set is the curated one).

## Owner input needed (would sharpen this)
- Is the 6-plugin protocol aspirational (want to follow it) or vestigial (drop it)?
- Primary goal weighting: ship VECTOR fast, or maximize process rigor?
(Interview owner; fold answers in.)

## Provenance
2026-07-07. Source: `~/.claude/CLAUDE.md`, `.claude/rules/*`, effective session
behavior across dozens of sessions.
