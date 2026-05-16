<!-- VECTOR-INGESTED ASSET
  Source: .claude/skills/SKILL.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:55+00:00
-->

---
name: token-aware-workflow
description: Full token reduction playbook for VECTOR VectorCode sessions. Covers mem0 startup, context compression, model routing, cache management, and graphify-first lookups. Use at the start of any expensive session or when context is getting large.
---

# Token-Aware Workflow — VECTOR Playbook

## The 5 levers (use in order)

### 1. Load mem0 instead of re-explaining (saves 200–800 tokens/session)
At the start of every session, run:
```bash
python "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Brain\.claude\hooks\mem0_query.py" "what are we working on"
```
Paste the output into the session. This replaces re-narrating context that mem0 already knows.

### 2. Answer from graphify first, read files second
Before asking VECTOR to read files, try:
```
/graphify query "what does District 7 memory architecture look like"
```
The graph.json already has all concepts extracted — a query costs ~200 tokens vs ~2000 to re-read the wiki files.

### 3. Compress context when token bar hits 60%
Run `/prune` — VECTOR will identify and drop the least-relevant context from working memory.
Then run `/rules-distill` — condenses accumulated rules/learnings into a compact form.

### 4. Route cheap tasks to smaller models
For: simple edits, renaming, formatting, single-file writes → prefix with "use haiku:" or configure vector routing.
For: architecture decisions, complex debugging → use the default Sonnet/Opus.

### 5. Save session before hitting the limit
Run `/context-save` before any context window gets critical. The skill captures:
- Git state + branch
- Decisions made this session
- Remaining work list
Next session starts with `/context-restore` — no re-explanation needed.

## Cache management (claudia.ai chat only)
- The 5-minute prompt cache window: if you stop interacting for 5+ minutes, the cache expires and the next message is uncached (costs more)
- Keep the session active with a short message if you're AFK
- Use the VECTOR Counter extension to see the countdown

## What NOT to do
- ❌ Re-paste the full VECTOR CLAUDE.md at the start of every session — mem0 + VECTOR Brain CLAUDE.md handles this
- ❌ Read 20 files to answer one question — use graphify query first
- ❌ Keep one conversation running for 8+ hours — split at natural breakpoints, use context-save

## Quick reference commands
| What | Command |
|------|---------|
| Load prior memories | `python mem0_query.py "topic"` |
| Save session state | `/context-save` |
| Restore session | `/context-restore` |
| Compress context | `/prune` then `/rules-distill` |
| Query knowledge graph | `/graphify query "question"` |
| Check token budget | `/context-budget` |
