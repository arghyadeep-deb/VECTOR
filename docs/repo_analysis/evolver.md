# evolver-main - VECTOR Absorption Review

**Verdict:** CLEAN-ROOM ONLY. Do not absorb GPL code. Use the Gene/Capsule/audit-trail ideas to harden VECTOR's existing evolution system.

**Priority:** MEDIUM-HIGH for architecture ideas, LOW for direct integration

**Effort:** 1-2 sessions for a clean-room evolution-event schema and prompt-policy layer

**License:** GPL-3.0-or-later in the local checkout. README also warns future releases may become source-available.

**Repo size inspected:** About 407 files, excluding git/build/cache directories.

## What It Is

Evolver is a Node.js CLI/self-evolution engine for AI agents. It scans project memory/logs, selects a Gene or Capsule under a Genome Evolution Protocol, emits a protocol-bound prompt, and writes auditable evolution events.

It supports:

- CLI and loop modes
- host hooks for Cursor, Claude Code, Codex, Kiro, opencode, OpenClaw
- local memory graph/event logs
- strategy presets and signal detection
- prompt governance through Genes/Capsules
- optional network/hub features

## VECTOR Overlap

VECTOR already has a stronger built-in evolution substrate:

- HP-based agent lifecycle
- ghost memory inheritance
- reasoning chains and policy memory
- agent registry and evolution engine tests
- PermissionGateway for real-world actions

So Evolver should not be installed as a second evolution daemon.

## Real Value For VECTOR

Useful clean-room ideas:

- typed `EvolutionEvent` records
- explicit "gene" object for reusable lessons/policies
- audit trail for every self-improvement decision
- review mode before applying prompt/policy mutations
- rollback/blast-radius metadata for agent changes
- memory-derived prompt improvement without arbitrary code edits

## Risks

- GPL license blocks copying code into VECTOR unless VECTOR accepts GPL obligations
- hook installers modify user-level Codex/Claude/Cursor configs
- loop mode can become duplicate background autonomy
- emitted directives can be misinterpreted as executable instructions by host runtimes
- optional hub/network features add external trust surface

## Recommendation For Sonnet

Do not import Evolver code.

Add clean-room structure to VECTOR's existing evolution:

1. Define `EvolutionEvent` and `StrategyGene` schemas in VECTOR style.
2. Store event records in existing SQLite memory/history tables.
3. Require review/approval before a gene changes prompts, policies, tools, or scheduler behavior.
4. Link each gene to evidence: failed task, successful task, test result, or owner feedback.
5. Add rollback metadata for any applied agent-policy change.

## Acceptance Criteria

- No GPL source code, prompts, or assets are copied.
- Existing HP/ghost-memory tests continue passing.
- Every evolution change has evidence, author/source, timestamp, and rollback note.
- No user-level Codex/Claude/Cursor hooks are modified by VECTOR.
- Network/hub features remain out of scope.

