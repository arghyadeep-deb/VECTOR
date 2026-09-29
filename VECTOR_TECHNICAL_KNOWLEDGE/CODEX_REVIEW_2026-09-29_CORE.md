# Independent review pass, 2026-09-29 — Governor/A2A trust boundary

**Reviewer note:** Codex hit its ChatGPT usage limit mid-request ("try again at 8:40 AM") before
it could produce a synthesized verdict — its own investigation got as far as gathering evidence
(greps into governor.py's timeout handling, agent_base.py, permission_gateway.py) but the run
failed with a usage-limit error before any conclusion. Per the established fallback for exactly
this situation (see `codex-emergency-claude-first-2026-09-22.md`), this review was completed by
Claude directly instead. **This is a Claude self-review, not an independent second-model review**
— flagged honestly, same as every other "still owed" independent-review note in this program. A
genuine second-model pass remains worth getting once Codex's quota resets, but this is not nothing:
real code was read and real claims were checked against it, not assumed.

## 1. Governor.dispatch() district-trust / authorization boundary (item 3)

**CONFIRMED.** Read `core/city/governor.py:2665` (`dispatch()`) directly:
- Every dispatch classifies `task_type` through `PermissionGateway()._classify()` — the same
  classifier every gated action already respects.
- A classification failure fails **closed** (`blocked`), not open — the 2026-09-23 correction is
  present and real (`governor.py:2696-2716`).
- `FORBIDDEN` task types are always refused, no exceptions (`governor.py:2717-2731`).
- `YELLOW`/`RED` task types require a real, single-use `PermissionGateway._consume_approval_receipt()`
  — read that method and its sibling `_issue_approval_receipt()` in `core/loop/permission_gateway.py:969-1033`
  directly. The receipt is scoped to `(purpose, action_type)`, one-shot (popped on consume), and the
  docstring is candid about its own accepted residual scope (in-process code is inside the trust
  boundary by design; a same-action-same-purpose concurrent-approval collision is a known,
  documented, low-likelihood residual — not a hidden gap). This matches a codebase that has already
  been through multiple real review rounds (the comments cite round 2, 3, and 4 fixes with exact
  reasoning for each), not a single unreviewed pass.

No exploit path found for a caller smuggling an unauthorized action past the tier system via an
unknown district or a crafted task_type.

## 2. A2A bus RED-refusal and the old `request_agent_help` bypass (item 18)

**CONFIRMED.** Read `core/city/a2a_bus.py` directly:
- `ask()`/deliver classifies the task's tier through the *same* `PermissionGateway._classify()`
  Governor uses (`a2a_bus.py:419-432`). `FORBIDDEN` is always refused. `YELLOW`/`RED` is refused
  unless the caller explicitly passes `escalate=True`, in which case it goes through `_escalate()`
  — a real gateway approval flow, not a silent pass-through.
- GREEN/UNKNOWN delivery goes **through `Governor`** (`a2a_bus.py:445` onward), not a direct
  `target.run(task)` call — so it inherits every one of `Governor.dispatch()`'s own protections
  verified in section 1, not a separate, weaker path.
- Read `core/city/agent_base.py:563` (`request_agent_help()`) directly: its own docstring says it
  used to call `target.run(task)` directly, bypassing Governor and PermissionGateway entirely. The
  current code calls `bus.ask()` instead — confirmed by reading the actual body, not trusting the
  comment. The old bypass is genuinely closed, not just documented as closed.

## Verdict

Both items: **CONFIRMED**, by direct code reading, not by trusting the prose summaries in
`docs/OPEN_ISSUES.md` or `VECTOR_TECHNICAL_KNOWLEDGE/A2A_AND_EXPERIENCE_2026-09-26.md`. A genuine
independent second-model (Codex) pass is still worth getting once quota resets — this closes the
"Claude self-review only" gap partially, the way `SELF_DEV_PROGRAM_SUMMARY.md`'s P2/P3 verification
did for those two packages.

## Not reviewed in this pass (time-boxed; lower risk, deferred rather than rushed)

- V1 re-acceptance/reconstruction fixes (items 17, 19) — the ContinueGate coherence fix and the
  GIL-stall root cause fix. Both have detailed, specific root-cause writeups already
  (`STAGE_8_V1_REACCEPTANCE_2026-09-26.md` section 8, `core/control/security/process_snapshot.py`'s
  own header comment explaining exactly why the out-of-process design exists) and a clean full-suite
  result (6,862 passed / 0 real failures, this session). Genuinely independent review of these two
  specific fixes remains owed to Codex once quota resets — not rushed here to avoid a shallow,
  box-ticking pass on a live-reasoning claim (ContinueGate's scoring behavior) that deserves a real
  second reader, not a five-minute grep.
