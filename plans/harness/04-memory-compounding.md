# Harness Analysis 04 — Memory & Learning Compounding
> 2026-07-07, Fable 5. Does the harness get smarter across sessions, or just accumulate?

## How memory works now
- **Harness memory:** file-based at `~/.claude/projects/.../memory/` — 36 files +
  `MEMORY.md` index (one line per file). Written on notable facts; recalled via
  the index loaded each session. Feedback/project/user/reference types.
- **VECTOR runtime memory (separate):** 5 SQLCipher tables (episodic FTS5,
  semantic, policy [RL reward], reasoning_chains, agent_history), synced to
  Supabase/Turso/D1.

## Where knowledge goes to die (findings)
1. **Recall depends on the MEMORY.md index being read + the model choosing to
   act on it.** 36 entries is still scannable, but growth is unbounded — at
   100+ entries the index becomes noise and old entries are effectively dead
   (present but never resurfaced). NO decay/promotion today.
2. **Captured-but-not-resurfaced:** rich per-session memory files exist, but
   nothing PROMOTES the most-reused facts to higher visibility or DEMOTES stale
   ones. The wake-word wall, the SQLCipher discipline, cloud-primary policy —
   all captured, but whether they resurface depends on index scanning.
3. **Never-captured:** small hard-won facts (exact commands, gotchas) often live
   only in a session's flow and are lost unless explicitly written. The new
   `vector-*` skills fix a big chunk of this (durable, trigger-loaded).
4. **Two memory systems don't cross-feed:** VECTOR's policy_memory (RL reward)
   learns from action outcomes but the HARNESS memory (what Claude knows) is
   separate — lessons in one don't inform the other.

## Is it getting smarter or accumulating? 
**Mostly accumulating.** New facts are captured well (good discipline), but there's
no decay, no promotion, no reinforcement of what's actually reused. It's a good
journal, not yet a compounding memory.

## Retention / decay / promotion design (concrete)
1. **Promotion:** track which memory files are referenced/loaded across sessions;
   the top-N most-reused get a `priority: high` frontmatter and sort to the top
   of MEMORY.md. (Skills already do this via trigger-rich descriptions — mirror it.)
2. **Decay:** add `last_relevant:` date; entries untouched for >90 days AND
   superseded get archived to `memory/archive/` (kept, not deleted) and dropped
   from the loaded index. Point-in-time facts already carry dates — use them.
3. **Consolidation:** monthly, merge same-topic files (the index already has
   near-duplicate absorption entries) — one home per fact, cross-reference.
4. **Cross-feed:** surface VECTOR's policy_memory wins (what routing/actions
   worked) into a harness memory entry periodically, so Claude learns what
   VECTOR learned.
5. **The skill library is the promotion mechanism for engineering knowledge** —
   settled facts graduate from memory files → durable `vector-*` skills. Keep
   graduating.

## Provenance
2026-07-07. Sources: `~/.claude/projects/.../memory/MEMORY.md`,
`.claude/rules/memory.md`, `core/memory/policy.py`, `core/memory/episodic.py`.
