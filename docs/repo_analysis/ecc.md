# ECC-main - VECTOR Absorption Review

**Verdict:** VET / SELECTIVE CLEAN-ROOM IDEAS ONLY. Do not bulk-install the harness pack into VECTOR.

**Priority:** HIGH for security/skill governance ideas, MEDIUM for workflow ideas

**Effort:** 1-2 sessions for selected safety checks and skill inventory patterns

**License:** MIT

**Repo size inspected:** About 2793 files, excluding git/build/cache directories.

## What It Is

ECC is a large cross-harness agent operating-system pack. It ships skills, agents, hooks, rules, MCP configs, installers, dashboards, command shims, and security workflows across Codex, Claude Code, Cursor, OpenCode, Gemini, Zed, GitHub Copilot, and other harnesses.

The local checkout includes:

- many skill packs
- installer scripts and plugin manifests
- hooks and cross-harness adapters
- state/session/worktree tooling
- AgentShield/security scanning references
- dashboards and readiness/status tools
- extensive test coverage around packaging and harness behavior

## VECTOR Overlap

VECTOR already has:

- `.agents/skills`
- MCP tooling
- PermissionGateway
- autonomous scheduler/agents
- repo-analysis and skill-absorption workflow
- planned SkillSpector security gate
- device/Cloudflare/Termux plans

ECC overlaps heavily with VECTOR's harness/skill layer. Installing it directly would create duplicate rules, duplicate skills, duplicate hooks, and unclear authority.

## Real Value For VECTOR

Useful clean-room ideas:

- skill inventory and health checks
- cross-harness compatibility matrix
- hook safety/audit conventions
- supply-chain IOC scanning
- command registry validation
- session/status snapshot format
- selective install planning
- AgentShield-style security scan entrypoint

## Risks

- extremely large skill/hook surface for prompt injection and tool confusion
- installing hooks can mutate user-level harness configs
- duplicate skills may conflict with VECTOR's own agent instructions
- command shims can obscure which tool is authoritative
- too much harness machinery can distract from VECTOR's JARVIS runtime

## Recommendation For Sonnet

Do not bulk absorb ECC.

Use ECC as a checklist/reference while implementing VECTOR-native governance:

1. Strengthen SkillSpector first.
2. Add a skill inventory report for VECTOR's local `.agents/skills`.
3. Add hook/config audit checks for Codex/Claude/Cursor surfaces.
4. Add command registry validation if VECTOR starts shipping many commands.
5. Keep all imported skill ideas quarantined and reviewed before activation.

## Acceptance Criteria

- No ECC hooks are installed automatically.
- No bulk skill copy is performed.
- SkillSpector remains the gate before new skill activation.
- Any adopted rule is reimplemented in VECTOR's own style and tests.
- Owner can see which skills/hooks are active and why.

