# VECTOR Dev Orchestrator — V0 Plan

## Goal

Build a safe autonomous development controller that coordinates Codex and Claude Code for VECTOR repository work.

The controller must:

- alternate implementation ownership between Codex and Claude
- use the other provider for review
- run task-specific verification
- run the existing VECTOR CI gate
- stop on risky or ambiguous changes
- persist task state so work can resume after interruption
- use bounded retries only
- keep VECTOR runtime model routing separate from development model routing

## V0 Scope

V0 will support this lifecycle:

1. accept one development task
2. classify task difficulty and risk
3. select implementer model
4. invoke implementer
5. capture structured result
6. run targeted tests
7. invoke reviewer from the other provider
8. adjudicate review findings
9. allow bounded fix/review rounds
10. run final task tests
11. run `python tools/ci_gate.py`
12. mark task PASS / BLOCKED / NEEDS_HUMAN
13. persist execution history

## Development Model Pool

### Codex / OpenAI

- GPT-5.6 Luna — scouting, search, simple checks
- GPT-5.6 Terra — routine implementation and tests
- GPT-5.6 Sol — serious everyday engineering
- GPT-6 Astra Low — hard investigation/implementation
- GPT-6 Astra Medium — rare difficult escalation
- GPT-6 Astra High — critical escalation only

### Claude

- Claude Haiku 4.5 — scouting and cheap checks
- Claude Sonnet 5 — main implementation/review workhorse
- Claude Opus 5 — hard architecture/debugging/escalation

## Default Routing

Codex escalation:

Luna -> Terra -> Sol -> Astra Low -> Astra Medium -> Astra High

Claude escalation:

Haiku -> Sonnet -> Opus

Use the cheapest model likely to succeed.

Do not escalate solely because a stronger model exists.

## 50/50 Ownership

Task ownership alternates by provider.

Example:

- Task A: Codex implements, Claude reviews
- Task B: Claude implements, Codex reviews
- Task C: Codex implements, Claude reviews
- Task D: Claude implements, Codex reviews

Review authority is evidence-based.

Tests and repository state override model seniority.

## Safety Rules

The orchestrator must never silently approve:

- architecture changes
- security policy changes
- dependency upgrades
- database migrations
- destructive cleanup
- production deployment
- credential access/change
- spending or paid API activation
- merge to protected/main branches

These require human review.

The orchestrator must:

- fail closed on unclear state
- never run infinite model loops
- use bounded review/fix rounds
- preserve repository governance
- never bypass VECTOR Permission Gateway rules for VECTOR runtime actions
- never modify runtime model routing to enable paid Anthropic/OpenAI APIs

## Git Rules

- inspect working tree before every task
- only one model owns a working tree at a time
- use isolated branches/worktrees when concurrent work is introduced
- never overwrite unrelated user changes
- never auto-commit unless policy explicitly allows it
- never auto-merge protected branches

## Verification

Every completed task requires:

1. task-specific tests
2. cross-provider review
3. regression verification where relevant
4. existing repository gate:

   `python tools/ci_gate.py`

5. explicit evidence of completion

"Model says done" is not completion evidence.

## Persistence

Each task must persist:

- task ID
- description
- owner provider
- selected model
- current stage
- retry count
- changed files
- commands executed
- test commands
- test results
- reviewer findings
- approval requirements
- final status

Allowed terminal states:

- PASS
- BLOCKED
- NEEDS_HUMAN
- FAILED

## Retry Policy

Normal maximum:

- 2 review/fix rounds

Hard maximum:

- 3 review/fix rounds

After repeated failure:

- escalate model if justified
- otherwise stop as BLOCKED or NEEDS_HUMAN

Never loop indefinitely.

## V0 Implementation Order

1. data models / task schema
2. persistent state store
3. Codex CLI adapter
4. Claude CLI adapter
5. model router
6. alternating ownership scheduler
7. subprocess/test runner
8. review loop
9. CI gate integration
10. approval gate
11. resume/recovery
12. telemetry
13. end-to-end dry run
14. real VECTOR task validation

## Out of Scope for V0

- production deployment
- automatic merging
- autonomous dependency upgrades
- autonomous destructive cleanup
- VECTOR runtime inference changes
- GUI automation
- distributed multi-machine execution
- unlimited background agents
- self-modifying orchestrator policy

## Success Criterion

V0 is successful when a real bounded VECTOR coding task can complete this sequence:

task
-> implementation
-> tests
-> cross-provider review
-> bounded fix
-> tests
-> VECTOR CI gate
-> persisted PASS result

with no manual intervention unless an approval gate is reached.
