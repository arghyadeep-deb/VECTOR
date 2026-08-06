# VECTOR Agent Guidelines

> Rules for every coding agent (Claude, Fable, Opus, Sonnet, Haiku) working on this repository.
> For agent *definitions* (VECTOR's AI agents), see `.claude/agents/`.

---

## General

- Always inspect before modifying
- Never assume, never hallucinate APIs
- Search for existing implementations first
- Read `.claude/rules/*` before writing code
- Follow `CLAUDE.md` priorities

---

## Implementation

Prefer:

- Existing abstractions (`core/` modules)
- Dependency injection over globals
- Composition over inheritance
- Reusable utilities over duplication

Never:

- Duplicate logic across districts
- Import `requests`, `flask`, `threading`, `pickle`
- Hardcode paths, API keys, or magic numbers
- Use `print()` — use `loguru`

---

## Debugging

Do not immediately modify code.

1. Reproduce the issue
2. Find root cause
3. Explain root cause
4. Implement smallest safe fix
5. Verify with a test

---

## Mandatory Workflow

Every coding task follows this sequence:

```
1. brainstorming         → before any new district/module/feature
2. writing-plans         → structured plan doc
3. executing-plans       → implement from plan, step by step
4. [security-guidance]   → auto-fires on every file edit
5. [mem0 skill]          → when touching District 7 or memory code
6. [frontend-design]     → when touching dashboard or web UI
7. verification-before-completion → before marking any task done
```

---

## Refactoring

Refactor only when there is measurable benefit:

- Maintainability
- Readability
- Correctness
- Performance (measured, not assumed)

Avoid cosmetic refactors.

---

## Performance

- Do not optimize blindly
- Measure first (benchmarks, profiling)
- Optimize only proven bottlenecks
- Token efficiency matters for LLM calls

---

## AI Systems

Every AI feature considers:

- Evaluation criteria (before implementation)
- Prompt quality and versioning
- Context management (session hydration)
- Retry logic with exponential backoff
- Observability (loguru with structured fields)
- Latency and token cost
- Failure modes and fallback chains

---

## Repository Rules

- Do not rename files without reason
- Do not move folders unnecessarily
- Do not modify unrelated code
- Do not bypass the Permission Gateway
- Do not call LLM without `context_engine.session_hydration_prompt()` first

---

## Testing

Whenever practical:

- Write tests for new functionality
- Update existing tests when behaviour changes
- Verify regressions
- Every file must have a `__main__` block (real test, no mocks)

---

## Documentation

If architecture changes:

- Update `CLAUDE.md`
- Update relevant `.claude/rules/*`
- Create ADR in `docs/adr/`

If workflow changes:

- Update `CONTRIBUTING.md`
- Update `TASKS.md`

---

## Communication

Before large implementations: provide a concise plan.

After implementation, summarize:

- What changed
- Why
- Risks
- Testing performed
- Evaluation results (for AI changes)
