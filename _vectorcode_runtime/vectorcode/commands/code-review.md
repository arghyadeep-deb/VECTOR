<!-- VECTOR-INGESTED ASSET
  Source: .claude/commands/code-review.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:56+00:00
-->

---
description: Review a VECTOR module or diff for bugs, RULE violations, and code style
argument-hint: File path or module name (e.g. "core/loop/autonomous_loop.py")
allowed-tools: Read, Grep, Glob, Bash(git diff:*)
---

# VECTOR Code Review

Review the specified file or recent diff for correctness, RULE compliance, and VECTOR code style.

Target: $ARGUMENTS

## Review Checklist

### Critical Rules Compliance
- [ ] RULE 1 — `session_hydration_prompt()` called before every LLM call
- [ ] RULE 2 — Every coroutine catches ALL exceptions, never propagates
- [ ] RULE 3 — No direct tool/action calls — always through permission_gateway
- [ ] RULE 7 — `policy.get_score()` BEFORE + `update_from_outcome()` AFTER
- [ ] RULE 8 — Reasoning chains stored if this module makes decisions
- [ ] RULE 9 — HP wired to actual task outcomes, not simulated

### Code Style
- [ ] loguru used everywhere — no `print()` in production code
- [ ] `[VECTOR][module]` prefix on all log messages
- [ ] `sys.path.insert(0, ...)` at top for imports
- [ ] `if __name__ == "__main__":` smoke test present
- [ ] `sys.stdout.reconfigure(encoding="utf-8")` in `__main__`
- [ ] All configurable values from `CONFIG`, not hardcoded
- [ ] No `requests` (use httpx), no `threading` (use asyncio), no `pickle`

### Architecture
- [ ] New agents extend `AgentBase`
- [ ] Lazy imports for circular dependency avoidance (e.g. `_get_memory()` pattern)
- [ ] Fallback chain present (primary → fallback → notify owner)
- [ ] Long sleeps use 1s chunks so `stop()` works

### Bugs
- [ ] Exception handlers don't swallow errors silently (must log)
- [ ] Async functions not called with `.run()` inside other async contexts
- [ ] No blocking I/O in async code (use run_in_executor)

## Output Format

For each issue found:
```
[SEVERITY] Rule/style/bug description
  File: path/to/file.py:line_number
  Fix: what to change
```

If no issues: "No issues found — RULE compliance ✅, style ✅, no bugs found."
