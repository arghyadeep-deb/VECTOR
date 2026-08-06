# Contributing to VECTOR

Rules for all contributors (human and AI agents) working on the VECTOR codebase.

---

## Branch Naming

```
<type>/<short-description>
```

| Type | Use |
|------|-----|
| `feature/` | New district, agent, or functionality |
| `fix/` | Bug fixes |
| `refactor/` | Code restructuring, no behaviour change |
| `docs/` | Documentation only |
| `test/` | Adding or updating tests |
| `chore/` | Build, config, tooling |
| `perf/` | Performance improvements |
| `hotfix/` | Urgent production fixes |

Examples:

```
feature/evaluation-pipeline
fix/retry-logic-timeout
refactor/llm-layer-decoupling
test/district-agents
```

---

## Commit Message Format

VECTOR convention:

```
[T#] module: what changed
```

Or for auto-commits:

```
auto: [module] what changed
```

Examples:

```
[T1.5] episodic.py: FTS5 + 5 tables complete
[T3] decision_engine.py: wired ReasoningBank RULE 8
auto: [governance] council HP gate verification
fix: [permission_gateway] timeout returns reject not exception
```

Rules:

- Reference the task/phase number when applicable
- Describe what, not why (why goes in PR description)
- Under 72 characters for the subject line

---

## PR Checklist

Before opening a PR:

- [ ] Code builds and runs without errors
- [ ] All existing tests pass (`pytest tests/`)
- [ ] New tests written for new functionality
- [ ] No duplicate logic introduced
- [ ] `.claude/rules/*` followed (code_style, libraries, architecture)
- [ ] No `print()` in production code — use `loguru`
- [ ] No hardcoded secrets or credentials
- [ ] `context_engine.session_hydration_prompt()` called before every LLM invocation
- [ ] Permission Gateway wired for any real-world actions
- [ ] ADR created in `docs/adr/` if architecture changed
- [ ] `docs/phase_status.md` updated if applicable
- [ ] PR description explains what changed and why

---

## Code Review Expectations

Every PR requires review before merge.

Reviewers check:

- **Correctness** — does it do what it claims?
- **Architecture** — does it fit existing patterns? (see `.claude/rules/architecture.md`)
- **Libraries** — only approved libraries used? (see `.claude/rules/libraries.md`)
- **Security** — Permission Gateway wired? No secrets exposed?
- **Performance** — measured, not assumed
- **Edge cases** — failure modes handled? Fallback chains in place?
- **Observability** — loguru with `[VECTOR][module]` format?
- **Testing** — `__main__` block present? Tests cover behaviour?
- **AI-specific** — evaluation criteria defined? Prompt changes justified?

---

## Testing Requirements

- All new functionality must have tests
- Bug fixes must include regression tests
- AI features must have evaluation criteria
- Tests must be deterministic — no flaky tests
- Every Python file must have a `if __name__ == "__main__":` block (real test, no mocks)
- Use `pytest tests/` for the full suite
- Use `scripts/smoke_test.py` for quick validation

---

## AI-Specific Rules

For any prompt or AI feature change:

- Document expected behaviour in the ADR
- Define acceptance criteria with metrics
- Measure before and after (latency, tokens, quality)
- Note potential regression risks
- No prompt changes merge without evaluation data

---

## What NOT to Do

- Never bypass the Permission Gateway
- Never call LLM without session hydration
- Never use `requests`, `flask`, `threading`, `pickle`
- Never hardcode API keys or paths (use `core/config.py` CONFIG)
- Never use `print()` in production
- Never load 2 Ollama models simultaneously (KV cache overflow)
- Never use paid Anthropic/OpenAI at runtime (owner decision 2026-07-08)

---

## Questions?

1. Check `.claude/rules/*` first
2. Read `CONTEXT.md` for terminology
3. Search for existing implementations
4. Check `docs/phase_status.md` for current state
5. Ask instead of guessing
